# DataClarity - AI Pipeline Specification (v2)

Source of truth for everything the AI does. Product behavior: `docs/SPECS.md`.
Data schemas between stages: `docs/CONTRACTS.md`.

## 1. Design Principles

1. **Bounded input.** The AI never sees a full file. Stage 1 sends the truncated
   profile (max 60 columns, 10 top values each) plus max 30 stratified sample
   rows. Schema inference sends 25 columns, because an answer for more does
   not fit in 3000 output tokens; the stage marks the rest "not inferred"
   (confidence 0) for the user to map. Every value sent (top values, sample
   values, sample-row cells) is cut to 100 characters, so the size is bounded
   as well as the count; column names are never cut (1C doubt review,
   decided by Thach). Stages 3 and 4 send only computed JSON contracts, never
   raw rows.
2. **Whitelisted output.** Cleaning actions must exist in the catalog (section 6).
   Anything else fails validation and is rejected whole.
3. **No AI arithmetic.** The AI never produces a number that appears in the
   report. Every figure comes from a tested pandas function; the AI may only
   quote figures present in its input.
4. **Human in the loop (stage 1).** The executed plan is the user's final plan.
5. **Degradable.** With the AI unavailable, profiling, manual plan building, and
   all of stages 2-5's computed numbers still work; only narrative text is lost.

## 2. Where AI is used (4 calls maximum per run)

| # | Stage | Step | Prompt file | Model | Input | Output contract |
|---|---|---|---|---|---|---|
| 1 | ingest | schema inference | `prompts/schema_inference.md` | `claude-sonnet-5` | profile + sample rows | `schema_inference.json` |
| 2 | ingest | cleaning plan | `prompts/cleaning_plan.md` | `claude-sonnet-5` | profile + schema inference | `plan_proposed.json` |
| 3 | diagnose | narration | `prompts/root_cause.md` | `claude-sonnet-5` | the engine's own steps 1-7 output | `diagnosis.ai_findings` |
| 4 | predict | strategy | `prompts/strategy.md` | `claude-sonnet-5` | metrics + diagnosis + forecast | `forecast.recommendations` |

Shared retry budget: 1 per run. Max tokens 3000 per call. JSON only; the
client strips markdown fences defensively. No sampling parameters:
`claude-sonnet-5` rejects `temperature` with a 400 (1C, 2026-09-19; this line
said "Temperature 0" before). Thinking is disabled (`thinking: {type:
"disabled"}`, accepted by Sonnet 5, which otherwise thinks by default), so the
3000 tokens and the 30 s timeout hold for the JSON answer itself. The SDK's
own retries are off (`max_retries=0`): every retry is the client's, counted
against the run budget.

`claude-haiku-4-5` is reserved for future cheap bulk tasks (e.g. suggesting
category labels row-group by row-group); not used in v1.

## 3. AI client (`shared/ai_client.py`)

Single entry point: `call_structured(prompt_name, variables, response_model,
model, max_tokens, retry_budget, validate=None)` returning the validated
`response_model` plus the model that answered. The caller passes the API key
(`AIClient.from_api_key`), the model id and the run's `RetryBudget`, because
`shared/` may not read the backend's settings (SPECS SEC-4). `validate` is the
stage's own check; a `ValueError` from it uses the retry like a schema error.

Responsibilities, in order:
1. Load the prompt template from `prompts/` and substitute `{placeholders}`
2. Call the Anthropic API (timeout 30 s)
3. Strip fences, parse JSON, validate with the Pydantic `response_model`. An
   answer holding a lone UTF-16 surrogate escape (valid JSON that no encoder can
   write) is an invalid answer: echoing it in the retry or storing it in a
   contract file would raise where no degraded path catches it. The rejection
   message repeats none of the text.
4. On failure: append the validation errors to the prompt and retry ONCE (if the
   run's retry budget is unused)
5. On second failure: raise `AIUnavailable`, which callers translate into the
   degraded path
6. Log model, token counts, latency, and outcome - never log the sample data

`AIUnavailable.reason` is a fixed code: `timeout`, `network`, `auth`,
`rate_limited`, `api_error`, `invalid_response` (invalid twice, or once with
the budget spent), `truncated` (`stop_reason` `max_tokens`) or `refused`.
Truncated and refused answers are not retried: the same input would fail the
same way. API failures do not spend the retry. The reason is logged and
carried by the exception only, never written to a contract file (1C, Thach).
Structured outputs (`output_config.format`) are a candidate later
improvement, to be verified with a real call first.

The client contains zero business rules. Stage-specific validation (catalog
whitelist, legality, column coverage) lives in the stage packages.

## 4. Prompt rules (all four templates)

- Header: role + "Respond with JSON only, matching the schema exactly. No
  markdown fences, no commentary."
- The full output schema and every enum is embedded in the template
- Explicit prohibitions: no invented numbers; every claim cites a figure present
  in the input; no actions outside the catalog; express uncertainty by lowering
  confidence rather than guessing
- Templates are versioned with the repo; changing one requires re-running the
  golden-path test

## 5. Enums (shared by steps 1 and 2)

- `semantic_type`: numeric_continuous | numeric_discrete | categorical_nominal |
  categorical_ordinal | datetime | identifier | boolean | text
- `canonical_field`: product_name | sku | category | transaction_date |
  quantity | unit_price | transaction_type | supplier | customer | note | ignore.
  `transaction_type` is the stock movement direction only, `in` or `out`
  (`docs/SPECS.md` section 9) - never a payment method, a sales channel, or an
  order/shipping status. `prompts/schema_inference.md`'s "CANONICAL FIELD NOTES"
  spells this out for the model with a negative example (a "Payment Method"
  column), because the field's own name is a false friend for those (2026-09-22,
  a real Kaggle file mapped one there; nothing downstream caught it since the
  value is syntactically a valid string either way)
- issue `code`: missing_values | invalid_dates | mixed_date_formats |
  negative_values | zero_values | inconsistent_case | trailing_whitespace |
  near_duplicate_labels | outliers_iqr | mixed_types | constant_column |
  all_null_column | duplicate_rows | duplicate_business_key |
  non_numeric_in_numeric
- `severity`: low | medium | high

## 6. Transform Catalog (`stages/ingest/transforms.py`)

Signature: `apply(df, column | None, params) -> (df, ChangeLogEntry)`.
ChangeLogEntry: `{action, column, cells_affected, rows_affected, params, detail}`.

| Action | Applies to | Params | Behavior |
|---|---|---|---|
| impute_median | numeric | - | fill NaN with median |
| impute_mean | numeric | - | fill NaN with mean |
| impute_mode | categorical/text/boolean | - | fill NaN with mode |
| impute_constant | categorical/text/boolean | value | fill NaN with an explicit value |
| drop_rows_missing | any | - | drop rows null, or holding only spaces, in this column (1F) |
| drop_column | any | - | remove the column |
| parse_datetime | datetime | format?, dayfirst? | parse to ISO 8601; unparseable -> NaT, flagged; a UTC offset is dropped and the date and time kept as written (1F) |
| cast_type | any | target | safe cast; failures flagged, never silently coerced |
| trim_whitespace | text/categorical/identifier | - | strip surrounding whitespace |
| normalize_case | text/categorical/identifier | mode: title/lower/upper | consistent casing |
| standardize_categories | categorical | mapping {from: to} | merge near-duplicate labels |
| fix_negative | numeric | strategy: flag/abs/drop | default flag |
| remove_exact_duplicates | dataset | - | drop fully identical rows |
| flag_duplicate_keys | dataset | keys[] | mark, never drop |
| clip_outliers_iqr | numeric | k=1.5 | clip outside [Q1-k*IQR, Q3+k*IQR]; opt-in |
| flag_only | any | note | record only, change nothing |

**Legality matrix** (implemented as data, table-driven tests). The "Applies to"
column above is the matrix; the entries below spell out the parts that were
read two ways before (1D):
- impute_median / impute_mean: numeric semantic types only; never identifier
- impute_mode / impute_constant: categorical, text, boolean - never numeric,
  datetime or identifier. An invented id joins rows that are not the same thing
- parse_datetime: datetime only
- trim_whitespace / normalize_case: categorical, text and identifier. They
  standardize how a value is written and invent nothing, so a padded or
  mis-cased SKU can be cleaned like any other string. The rationale of a plan
  that normalizes the case of an identifier should say so, because a
  case-sensitive source system may keep "ab-1" and "AB-1" apart
- Required canonical fields (product_name, transaction_date, quantity): the
  four imputation actions are ILLEGAL there, because a filled-in value would be
  counted in the report as if it had been measured. Missing values in those
  columns are handled by drop_rows_missing or flag_only instead. The rule is
  about imputation only: every other action the column's semantic type allows
  stays legal, so transaction_date is still parsed and product_name is still
  trimmed

- flag_duplicate_keys: in the AI's proposal `keys` must be the business key, defined
  in section 11 (the count reported for `duplicate_business_key` and the rows this
  flags then describe the same thing); a plan the user edited may use any columns of
  the file (section 12)

**Fixed execution order** (not AI-controlled, because order changes results):
drop_column -> remove_exact_duplicates -> trim_whitespace -> normalize_case ->
parse_datetime / cast_type -> drop_rows_missing -> imputation ->
standardize_categories -> fix_negative / clip_outliers_iqr -> flags.
`drop_rows_missing` runs before the imputations (decided by Thach in 1F), so a
median, mean or mode is taken over the rows that stay and the result does not
depend on the order of the columns in the plan. Inside a group the plan's own
order is kept (dataset actions first, then columns as listed).

## 7. Diagnostic engine (stage 3)

Eight steps. **Steps 1-7 are deterministic pandas; only step 8 calls the AI.**
The AI narrates conclusions the engine has already reached: it may not choose,
add, remove or re-rank hypotheses, and may not upgrade a verdict. Output shape:
`docs/CONTRACTS.md` section 7. Rationale for the two design rules that shape
everything below: `docs/adr/0004-shapley-attribution.md` (order-independent
attribution) and `docs/adr/0005-pre-registered-hypothesis-catalog.md` (a fixed
catalog the AI cannot pick from), plus
`docs/adr/0006-level-signals-are-descriptive.md` for which step-4 rows are
allowed to mean anything (only year-over-year ones). Full derivation, worked numbers and sources:
`docs/DIAGNOSE_DESIGN.md`.

| Step | Question | Block |
|---|---|---|
| 1 Frame | What is compared with what? | `frame` |
| 2 Trust gate | Can the data be trusted? | `trust` |
| 3 Calendar | How much of the change is calendar only? | `calendar` |
| 4 Signal vs noise | Is the change unusual? | `signals` |
| 5 Metric tree | Which lever moved? | `tree` |
| 6 Localization | Where did it happen? | `localization` |
| 7 Hypotheses | Which fixed hypotheses hold? | `hypotheses`, `not_testable`, `headline` |
| 8 Narration | How is it said in words? | `ai_findings` |

If step 2 returns `blocked`, steps 3-6 are skipped, their blocks are `null`, and
the headline reports the data problem (rule 1).

### 7.1 Inputs and degradation

Reads `metrics.json`, `cleaned.csv` and `cleaning_report.json` from the run
directory. Stage 3 must not import `stages/analyze`: the shared transaction
parsing (`ParsedTransactions`, `parse_transactions`, `require_column`,
`pct_change`, `is_blank`) moves to `shared/` first, so both stages compute
revenue, orders and "revenue-counted rows" from one definition. Every figure
stage 3 recomputes that also exists in `metrics.json` must match it exactly; a
dedicated test enforces this, because two stages disagreeing on a definition
would make the report contradict itself.

| Field | Missing consequence |
|---|---|
| `transaction_date`, `quantity` | stage cannot run (already enforced upstream) |
| `unit_price` | ANALYSIS_FAILED already at stage 2, so stage 3 is never reached |
| `category` | category localization skipped; `mix_rate` is `null`; P2 uses product-level mix only |
| `customer` | lever falls back to `orders*aov`; `tree.customers` is `null`; C1-C4 become `not_testable` |
| `transaction_type` | all rows treated as `out` (the 2A rule) |
| country | no canonical field exists; X6, never evaluated |

### 7.2 Step 1: Frame

Comparison pair is `metrics.json`'s own `period` (latest complete month vs the
month before, per 2A). The year-ago pair is those two months one year earlier,
when both exist - both or neither, since a one-sided year-ago comparison gives
T2 nothing to divide by. History window: all complete months strictly before
`current`, capped at the `HISTORY_MAX_MONTHS` most recent.

**"Complete month" here is stricter than 2A's** (3B's decision, flagged for
veto): a month counts only if the file covers it from its first day to its
last. 2A asks only whether a month has *elapsed* by `data_end`, which is right
for choosing a comparison period - a shop whose first sale is on the 15th did
not have half a March, it opened mid-March. A monthly baseline is a different
question: a first month holding 16 days of data is a low point that never
happened, and feeding it to an XmR chart widens the limits or fakes a signal.
So `frame.history_months` can be smaller than the gap between `data_start` and
`current`, and `history_start`/`history_end` are `null` when the window is
empty.

### 7.3 Step 2: Trust gate

Three checks, each `ok | caution | blocked | inconclusive`.

- **D1 coverage.** `zero_days` = calendar days in a period with no
  revenue-counted rows. The expectation is learned **per weekday** from the
  history window - `zero_rate_d` = share of history dates of weekday `d` with
  no rows - so `expected_zero_days(m) = sum_d count_d(m) * zero_rate_d` and
  `excess_zero_days(m) = max(0, zero_days(m) - expected_zero_days(m))`.
  A per-weekday rate rather than one scalar (Thach, 3B) because closing is a
  weekday habit, not a daily probability: one scalar leaves a residue that
  moves with month shape (measured worst case 0.86 days for one closed
  weekday, 1.43 for two, 1.71 for three - bounded under `D1_CAUTION_DAYS`, so
  it never raised a false caution, but it also partly absorbs a real Tuesday
  gap in a shop that never trades Sundays, which the per-weekday rate exposes).
  `caution` at `D1_CAUTION_DAYS` or `D1_CAUTION_SHARE`; `blocked` at
  `D1_BLOCK_SHARE`. Estimated gap = `excess_zero_days x mean revenue per active
  day in prev`. `inconclusive` when there is no history to learn from.
- **D2 uniform price-level shift.** Products sold in both periods with at least
  `D2_MIN_ROWS` rows each. Per product, `median unit_price(cur) / median
  unit_price(prev)`.
  - **Cluster rule**, at `D2_MIN_PRODUCTS` comparable products or more: if
    `D2_CLUSTER_SHARE` of ratios sit within `D2_CLUSTER_WIDTH` of their common
    median and that median is outside `D2_NEUTRAL_BAND`, return `caution`.
  - **Small-catalogue rule** (Thach, 3B), between `D2_SMALL_MIN_PRODUCTS` and
    `D2_MIN_PRODUCTS - 1` comparable products: `caution` only when
    `D2_SMALL_CLUSTER_SHARE` of ratios are at least `D2_SMALL_RATIO_HIGH` or at
    most `D2_SMALL_RATIO_LOW`. Returning `inconclusive` for every small shop
    left a real hole: a cents-as-units error then flows into the product lens
    and P1 is reported as "like-for-like prices +9,900%", supported and
    possibly the headline - a step-4 signal does not prevent that. An
    order-of-magnitude jump is a unit-error signature; ordinary repricing is
    not, so a tight cluster among a handful of products still does not qualify.
  - Below `D2_SMALL_MIN_PRODUCTS`, `inconclusive`: with one or two products
    there is no "uniform" to speak of.
  - **Never `blocked`**, under either rule: the engine cannot tell a unit or
    currency error from a deliberate repricing, and must not claim to.
- **D3 flagged-row concentration.** Share of rows carrying any `__flag_*`
  column, per period. `caution` when the current share is `D3_RATIO` times the
  previous and at least `D3_MIN_SHARE`.

Verdict: `blocked` if any check blocks, else `caution` if any cautions **or is
`inconclusive`**, else `trusted`. An inconclusive check is not evidence that
the data is fine (Thach, 3B): reporting "trusted" on a run where two of three
checks never executed claims a verification that did not happen. Caution never
changes the headline (7.8), so the cost is one honest badge on thin files.
D1 also learns only from history months that hold rows - an empty month is
itself a gap, and letting it set the expectation lets missing data hide missing
data. Stated limitation, carried in `trust.limitations`: rows removed by
`drop_rows_missing` in stage 1 are not in `cleaned.csv`, so they cannot be
assigned to a period. Fixing that needs dropped-row counts per month in
`cleaning_report.json` - a stage 1 contract change, in the Backlog, not Phase 3.

### 7.4 Step 3: Calendar adjustment

Needs `CALENDAR_MIN_WEEKS` of history, measured as calendar days in the history
window (`CALENDAR_MIN_WEEKS * 7`), else `method = "day_count"`. In practice the
fallback is rare: two complete months of history already clear it, so a file
needs barely any history to earn weekday weights - unlike the XmR baselines in
7.5, which need `XMR_MIN_BASELINE_POINTS` whole months and therefore go
`insufficient_history` on files that still get real weekday weights. A six-month
file is the common case of exactly that split. Weekday
weight `w_d` = **median** revenue per calendar date of weekday `d` across the
history window, **including zero-revenue dates** so regular closing days are
reflected.

An earlier draft said to exclude dates inside a D1 excess gap. That is not
definable: D1 measures excess *against* the history window's own pattern, so
within history there is nothing to call excess by construction. A first attempt
argued the mean was safe anyway, because a hole drags every weekday down by the
same factor and the ratio below cancels it; 3B's doubt-review disproved that
with numbers. Any run of days whose length is not a multiple of seven hits
weekdays unevenly, and the cancellation needs `count_d(cur) == count_d(prev)` -
exactly the case where this step has nothing to say. A shop whose POS was down
on Saturdays for three history months had 12.6% of its month's movement
invented as real decline. The **median** gets what the exclusion was reaching
for without needing to identify the gap: a minority of ruined dates does not
move it at all.

`E(m) = sum_d count_d(m) * w_d`;
`calendar_effect = revenue_prev * (E(cur)/E(prev) - 1)`;
`calendar_adjusted_change = change_abs - calendar_effect`.

### 7.5 Step 4: Signal vs noise

Series: revenue, orders, active customers, frequency, AOV, units per order,
price per unit, return rate. XmR limits from the series' own history separate
routine variation from a real move, so a point-to-point comparison cannot raise
a false alarm on its own.

- **Mode, decided per series.** Year-over-year % change when the file has at
  least `YOY_MODE_MIN_MONTHS` complete months **and** that series' YoY values
  actually yield `XMR_MIN_BASELINE_POINTS` usable baseline points; otherwise
  level. The month count alone is not enough (3B): one zero or missing month in
  the file's first year leaves a YoY point undefined, and at the threshold that
  is the difference between eight baseline points and seven - so adding a month
  of history could turn a correctly detected collapse into "we cannot say".
  Deciding per series also keeps `mode` honest per row rather than labelling
  every series `yoy` while only some have limits.
- **Baseline.** Points before `current` in the history window; fewer than
  `XMR_MIN_BASELINE_POINTS` gives `insufficient_history` for that series.
- **Limits.** `center = mean(baseline)`, `mR = |x_t - x_(t-1)|` over
  consecutive baseline points,
  `limits = center +/- XMR_MEDIAN_FACTOR * median(mR)`, falling back to
  `XMR_FACTOR * mean(mR)` when the median moving range is zero. Which one ran
  is recorded on every signal as `limits_method`, so a later change of
  estimator is visible in the file rather than silently changing what every
  verdict means.

  The median form is the default because one anomalous month contributes two
  large moving ranges: the average absorbs them and the median does not. On
  3B's finding 3a - a near-zero month producing a huge year-over-year point -
  the average-based limits were about 650 units wide and the series could
  never signal; the median gives about 17.

  The fallback is load-bearing, not a formality. The median moving range is
  exactly zero whenever half the consecutive pairs are identical, which is
  ordinary for flat, rounded and small-integer series, and zero-width limits
  report a 0.2% move as a special cause. Session 3D2 shipped that and measured
  it before reverting. Where the fallback triggers, the result is bit-for-bit
  what the average alone produced.
- **T3 is the one exception, and the asymmetry is deliberate** (Thach, 3D4).
  "The change is routine variation" is `supported` only when **no rule-1
  signal fires AND no rule-2 signal fires**. Rule 1 decides what step 7 *acts*
  on; T3 is not an action, it is the claim that nothing happened, and that
  claim must not be made while a rule-2 signal sits in the output unexplained.
  So a rule-2 signal can **prevent** "routine" but can never **become** a
  headline cause. Read the two rules together rather than as a contradiction:
  the bar for asserting that nothing happened is higher than the bar for
  acting.

  **Superseded (ADR-0006).** Session 3D4 hung T3 on `mode_fallback` instead:
  that flag meant a series would have charted year over year but fell back to
  a level chart, and T3 could not call such a month routine. The flag was
  doing the work `mode` now does, and less reliably - a series can be in level
  mode for reasons the flag never sees. T3 reads `is_verdict` and nothing
  else. The paragraphs below are the live rule.

  When every series reports `insufficient_history`, T3 is **`inconclusive`,
  never `supported`**. "We could not tell" and "nothing happened" are
  different sentences, and scenario S11 exists to hold that line: a six-month
  file has no baseline to call anything routine by.

  **And T3 is `inconclusive`, never `supported`, whenever `revenue` has no
  year-over-year VERDICT** - at any file length, whether because the series is
  `insufficient_history` or because it is charted in level mode (ADR-0006).
  The conditions above are all about signals that DID fire; none of them
  notices a series that was never judged, and reading "no verdict fired" as
  "nothing happened" is the S11 failure in a new shape. T3 is the claim that
  the REVENUE change was routine, and a revenue series with no verdict cannot
  support it.

  **T3's evidence lists every series that had no year-over-year verdict**, so
  a month reported as routine shows which parts of it were not judged rather
  than implying all of them were.
- **A level-mode row is DESCRIPTIVE, never a verdict**
  (`docs/adr/0006-level-signals-are-descriptive.md`). It is computed, carries
  its limits and its rule, and is written to `diagnosis.json` for a reader to
  look at. Step 7 does not read it as a judgement about the month.
  `contracts.diagnosis.is_verdict` is the single definition.

  An XmR chart assumes a stable process, and a seasonal retail series is not
  stable in level terms. The level chart centres on the average of every
  month, so for any month with a season that centre is in the wrong place, and
  the failure runs both ways: a December that halves still lands above it and
  reads `within` or `above`, while an ordinary December fires `above` for
  being ordinary. Year-over-year is what makes the series stable, and when it
  is unavailable the missing information is exactly what a level chart would
  need to stand in for it.

  Sessions 3D3, 3D4 and 3D5 each tried to gate the level chart instead. The
  last of them could not run on a 24-month file at all - `HISTORY_MAX_MONTHS`
  is 24, so the window holds one prior occurrence of the current calendar
  month and that occurrence is the comparator whose failure caused the
  fallback. The ADR records all four attempts and why the policy moved rather
  than the arithmetic.

  **The one consumer allowed to read a level row is the masked-shift alert**
  (7.6), because its other half divides by the change in revenue and so fires
  on every flat month by itself. It records which kind of row it rested on in
  `lever.masked_shift_basis`, and 3F phrases a `level` basis as possibly
  seasonal.

  **Stage 5 must not render a level-mode `within` as "within normal
  variation"** - see CONTRACTS section 7 and the 3F narration rules in 7.9.
  That responsibility moved here from the deleted gate; it is a rule, not a
  preference.
- **Step 7 acts on rule 1 only.** Rule 2 measures a run against a centre
  computed from the same points, so one anomalous month re-fires it every
  month until it leaves the window (3B). Re-baselining was attempted in
  session 3D2 and the method did not work, so **rule-2 signals stay in the
  output and a reader can see them, but T3 and the masked-shift alert are
  decided on rule 1** (Thach, 3D2). This is a contract, not a session
  convention: step 7 may not promote a rule-2-only signal to a verdict, and
  the `rule` number every signal carries is what makes the distinction
  machine-readable.
- **Rules, deliberately only two.** Rule 1: the current point is outside the
  limits by more than the margin below. Rule 2: the current point and the
  `XMR_RUN_LENGTH - 1` months immediately before it are all on the same side of
  the centre line (consecutive months, not the non-null points that remain
  after gaps are dropped - a gap breaks the run). More rules would make the
  engine cry wolf.
- **Minimum spread** (3D3). When the estimators measure no variation, the
  limits take a floor **in the units the series carries**: percentage POINTS
  in year-over-year mode (`XMR_MIN_SPREAD_YOY_POINTS`), one percentage point
  for a rate series in level mode (`XMR_MIN_SPREAD_RATE`), otherwise a share
  of the centre (`XMR_MIN_SPREAD_SHARE`). Zero-width limits call every
  conceivable move a special cause, and that is not a rare shape - a flat
  shop, and both trends and both seasonal patterns in year-over-year mode, all
  produce it.

  The floor's SIZE is load-bearing in both directions, because it may widen a
  measured chart. Too small and an unchanging decline fires every month; too
  large and it deletes real signals - at 2% of the centre it silenced a 2%
  drop on a shop whose ordinary variation is 0.2%, a ten-sigma event. The
  constants are tuned against
  `tests/stages/diagnose/test_spread_floor_cases.py`, which lists the moves
  that must FIRE beside the ones that must stay quiet; change one and run it.

  A money series with neither measured variation nor a level to take a share
  of - every baseline month netting exactly zero - has no scale at all and
  reports `insufficient_history` rather than a floor picked out of the air.
  `limits_method` says `minimum_spread` whenever the floor was used, so a
  floored chart is never mistaken for a measured one.
- **Mode selection** needs a year-ago value for the **current** month as well
  as enough usable history points; without one the series falls back to level
  mode (3D3). Otherwise a shop shut that month last year reports
  `insufficient_history` on an 80% collapse that the level chart catches
  instantly. Modes therefore differ per series within one run, so
  `center`/`lower`/`upper`/`value_cur` are money on one row and percentage
  points on the next: read `mode` before comparing two signals.
- **Year-over-year base guard** (3D4, 3D6). A year-over-year point divides by
  the same month a year earlier, and that month is used as a base only if it
  is (1) **positive** - revenue is signed, and two negatives divide to a
  confident positive, so a doubled loss read as growth; (2) **more than
  floating-point residue** next to the series' largest month - a cancelled
  month nets 1.4e-17, not 0.0; and (3) **at least `YOY_MIN_BASE_SHARE` of the
  series' typical magnitude**, the median of `|value|` over the history
  window's TRADING (non-zero) months (3D6). A refused base leaves that point
  undefined. A refused CURRENT comparator sends the series to level mode with
  `mode_fallback = unusable_year_ago_base`, the path an unusable base already
  took. Refused BASELINE bases remove points, and enough of them take the
  series below `XMR_MIN_BASELINE_POINTS`, which also means level mode - but
  with `mode_fallback = null`, exactly as 3D4's sign test already did.
  Level mode is descriptive and never a verdict (ADR-0006). That second
  path is a labelling gap for 3D7: the row looks like a shop with too little
  history.

  The third condition exists because the first two admit 12.50 on a shop
  turning over 50,000, which divides to +399,900%. Since ADR-0006 that is an
  actionable rule-1 verdict on a month where nothing happened, and it fired
  the masked-shift alert with `basis = yoy`, which headline rule 4 states
  without its hedge. The same base inside the baseline drags the mean centre
  tens of thousands of points, so every ordinary month fires. Typical is a
  median so one freak month cannot move it, over the history window so a
  shop is judged against its recent self, a magnitude so a series that nets
  negative in most months still has a size, and over trading months because
  a month without rows is charted as 0.0 - a stall open four months a year
  otherwise had a typical level of zero and no guard at all.

  **The share is a policy, not a measurement**, for the reason 3D5's width
  constant was: a base at fraction f is refused iff f is below it, so a sweep
  of bases scored against it is circular - and the exclusion side has no edge
  at all, since a comparator at half its normal level already fires an
  actionable +100% on an ordinary month. **Base effects are what year-over-
  year is; this guard removes only the end of the range where the figure has
  stopped being a growth rate.** What was measured is the ceiling, from bases
  that are small and real: a recovery after a slump of exactly half the
  window sits at 4.76% of its median and is lost from 0.035 at 20% monthly
  noise. The value inside the band is chosen by the asymmetry (Thach, 3D6):
  refusing a usable current comparator only removes a verdict, keeping an
  unusable one fabricates one, so where the evidence cannot separate two
  values the one that refuses more wins. **That asymmetry holds for the
  current comparator only.** Refusing a BASELINE base moves the centre in
  either direction and can create a verdict. The guard applies there only
  because a base under 3% drags the centre by thousands of points, which is
  the reproduction; it is not safe, and on ordinary months of two-regime
  shops it gave 23 fabrications against 21 without it.

  **What the guard does not fix** (two doubt-review cycles, each case run to
  the headline; PROJECT_PLAN 3D9, which blocks 3E): a baseline base at 3.5%
  to 25% of normal still drags the mean centre into an actionable verdict on
  an ordinary month; a shop off-season for more than half the year at a low
  non-zero level has its typical month set by the off-season, so a 12.50
  in-season comparator is still actionable; and a slump deeper than about
  1.5% of normal loses its real recovery verdict. The first two FABRICATE,
  the third suppresses. `test_yoy_small_base.py` pins each as a known limit.
  Full reasoning and figures in `thresholds.py`.

  **T2 divides by the same kind of base** (`revenue_prev * (LY_cur/LY_prev -
  1)`, 7.8) and must apply all three conditions when 3E builds it.
- **Margin.** A point counts as outside a limit only if it clears it by
  `max(XMR_REL_TOLERANCE * |centre|, the series' absolute floor)`. A baseline
  that never varied gives zero-width limits, and without a margin a rounding
  cent - or the 4.4e-16 a month of cancelling sales and returns leaves behind -
  reads as statistically outside them. The relative term cannot protect a
  series centred on zero, which `return_rate` usually is, so the floor does
  that: `XMR_ABS_FLOOR_RATE` for rate series, `XMR_ABS_FLOOR_DEFAULT` for money
  and counts.
- **Known limits, and who owns them now.** The outlier half is fixed above.
  The re-firing half is not: the centre is still the mean of a baseline that
  contains the run rule 2 tests. Session 3D2 attempted step-change detection
  and re-baselining, and the method failed on multi-month seasons, on a
  business that steps twice, and in year-over-year mode - it is in the Backlog
  with the failure written down. Step 7 therefore acts on rule 1 only, as
  above.

  The defects that made rule 1 itself unreliable were fixed in session 3D3;
  see **Minimum spread** and **Mode selection** below.

A YoY point at month `m` needs month `m-12` to exist, but that lag month is
only an input to the calculation - it is not itself a baseline point and may
sit outside the history window. This is why `YOY_MODE_MIN_MONTHS` is derived,
not chosen: see 7.10.

### 7.6 Step 5: Metric tree

Every decomposition reconciles to its own total exactly (relative tolerance
1e-9, enforced by tests).

- **Shapley.** For `F = x_1 * ... * x_n`, factor `i`'s contribution is its
  average marginal effect over all `n!` orderings. With `n <= 3` all orderings
  are enumerated. Contributions sum exactly to `F(cur) - F(prev)`, and unlike
  sequential substitution the answer does not depend on an order someone picked
  (`docs/adr/0004-shapley-attribution.md`).
- **Lever level 1.** `revenue = customers * frequency * AOV`, or `orders * AOV`
  when `customer` is unmapped. Two cases the formula cannot express (Thach,
  3C). A period with **zero orders** leaves AOV as 0/0, so the level is `null`
  with a recorded reason: substituting a zero would report "AOV contributed
  +50" for a shop's opening month, which is arithmetic, not a diagnosis. A
  period with **zero identified customers but orders present** - every row that
  month carrying a blank customer - is not that case: it takes the same
  two-factor fallback as an unmapped column, which is still exact and still
  informative, and the C-family hypotheses become `not_testable`.
- **Lever level 2.** `AOV = units_per_order * price_per_unit`, converted into
  revenue units proportionally (`phi_AOV * phi_k / delta_AOV`), which stays
  exact because the level-2 contributions sum to `delta_AOV`. `null` when net
  units are not positive in both periods, and `null` when AOV did not move,
  since the conversion divides by that change.
- **Masked-shift alert.** `gross_to_net = sum(|phi_i|) / |delta_revenue|` over
  level 1. Alert when it reaches `MASKED_GROSS_TO_NET` and at least one
  component has a step-4 signal. This is the case a naive "did revenue move?"
  report misses entirely: a flat total hiding large offsetting movements.
  When level 1 is `null` the ratio and the alert are **both `null`, never
  `false`** (Thach, 3C): `false` asserts a check that did run, and a missing
  tree must not be read downstream as "no masked shift". When revenue did not
  move at all, the ratio alone is `null` - it has no denominator, and infinity
  is not representable in JSON - while the alert is still decided on whether a
  component carries a signal.
- **"Did not move" is a relative test, never `== 0`.** Both guards above
  compare against `RECONCILE_REL_TOLERANCE * scale`. An exact comparison lets
  float residue through: one file produced a revenue residue of -5.6e-17 that
  became a gross-to-net ratio of 4.5e15, enough to fire the masked-shift alert
  and headline rule 4 on a month where nothing moved (3C doubt-review).
- **Customer bridge (additive, exact).** Classify every customer active in
  `prev` or `cur` as new, resurrected, retained or **lapsed** - never
  "churned": in retail, not buying this month is not leaving forever.
  **Every term is stored signed, and the identity is the plain sum:**
  `delta_revenue = new + resurrected + expansion + contraction + lapsed +
  unattributed`, where `contraction` and `lapsed` are normally negative and
  `unattributed` is the change from rows with a blank customer. An earlier
  draft of this section wrote them as positive magnitudes subtracted from the
  total, which contradicted CONTRACTS section 7's example and the file the
  stage actually writes; anyone implementing the prose against the real JSON
  would have negated those two terms twice (Thach, 3C). Signed terms also make
  the whole of `diagnosis.json` follow **one** rule - components sum to the
  change - shared with the Shapley contributions and the PVM effects.
  One dependent formula moved with it: **C2's contribution is
  `lapsed(t) - lapsed(t-1)`, with no outer negation.** That negation existed
  only because `lapsed` used to be a positive magnitude; against a signed term
  it flips the sign, so a month in which more customers lapsed would be
  reported as a positive contribution - in a hypothesis that can take the
  headline. C1 and C3 are unaffected: `new` and `resurrected` carry the same
  sign under either convention. The **lapse window is one period**, matching 2A's periods: a
  customer active in `prev` and not in `cur` is lapsed *this period*. A
  three-month definition was considered and rejected because it breaks the
  identity above - a customer who bought two months ago would be neither lapsed
  nor retained, leaving their `prev` revenue unaccounted for. The same bridge is
  computed for the previous transition when history allows, so C1-C3 can compare
  flows. If `cur` falls in the first `LEFT_CENSOR_MONTHS` months of the file,
  "new" is unreliable and C1/C3 return `inconclusive`.
  Customers are keyed on a **normalised identity** - stripped and case-folded
  by `shared.transactions.customer_identity`, the same treatment product keys
  have had since 2C (Thach, 3C2). Both stages use it, which is what keeps
  their `active_customers` figures equal. Keyed raw, one customer written two
  ways is two people, and if the spellings fall either side of the period
  boundary the bridge reports one lapsing and one arriving - "we lost everyone
  and gained a whole new base" on a flat month. The error direction decides
  it: that fabrication comes from ordinary data entry, while a wrong merge
  needs two real ids differing only by case or whitespace. No further
  normalisation (no leading-zero or punctuation rules), which would start
  merging ids a POS really does distinguish.
  A customer is **active if they have at least one revenue-counted row**,
  whatever the sign of their net revenue (Thach, 3C). A returns-only customer
  is classified like any other and their term carries the sign the arithmetic
  gives; nothing is clamped, because a clamp replaces a measurement with an
  invented number and breaks the identity. This also keeps "active" identical
  to stage 2's `active_customers`, so the two stages cannot disagree about who
  was active. `evidence` records how many customers classified as new have a
  first-ever row that is a refund - a left-censoring hint, since they are
  returning something the file never recorded them buying - and whether either
  side of the transition holds no rows at all.
  The previous transition is computed only when **both** its months contain
  revenue-counted rows, not merely when they are complete by the calendar: an
  empty month produced an all-zero bridge that was then offered to C1-C3 as a
  real comparison of flows (3B finding 2, again).
- **Returns lens.** `delta_net = delta_gross - delta_returns`.
- **Product lens (PVM, exact).** Partition products into L (in both periods), N
  (new) and X (discontinued). `delta_gross = delta_gross_L + gross_N(cur) -
  gross_X(prev)`; for L, three-player Shapley over volume, mix and price.
  Rows whose `product_name` cell is empty form **one visible bucket**, not a
  silent omission: `groupby` drops null keys by default, so those rows left the
  lens while remaining in the gross total it reconciles against, and on the
  reproduction gross sales had fallen 49 while the lens reported a rise of 1 -
  a direction flip in the figures the headline is chosen from (3C doubt-review).
- **Reconciliation is checked at runtime, not only in tests.** Every lens is
  asserted against its own total at `RECONCILE_REL_TOLERANCE` before the tree
  is returned, and a failure raises rather than writing a report built on a
  decomposition that does not add up. A violation is always a code bug: these
  lenses are exact in real arithmetic.

### 7.7 Step 6: Localization

Fixed dimensions: category (if mapped), product, and customer type from the
bridge. RFM segment localization is excluded - per-customer segments live in
stage 2; segment movement is covered by hypothesis C4 from `metrics.json`'s
aggregate counts. Members below `MEMBER_MIN_REVENUE_SHARE` of `prev` revenue
and under `MEMBER_MIN_ORDERS` orders in both periods collapse into "Other"; at
most `MEMBERS_PER_DIMENSION` named members per dimension, ranked by `|delta|`;
new and removed members listed separately.

**Mix vs rate.** For whichever of AOV or price per unit moved more in relative
terms, two-player Shapley on `sum_c(share_c * value_c)` splits the move into a
mix effect and a rate effect. This is the Simpson's-paradox guard: every
category's price can rise while the overall average falls, and only this split
says so.

**Breadth.** `declining_base_share` (share of `prev` revenue held by members
moving the same way as the total) and `top_member_share`. `broad` at
`BREADTH_BROAD`, `concentrated` at `BREADTH_CONCENTRATED`, else `mixed`; broad
is tested first, because when both hold, "this is happening across the
business" redirects attention better than "one member leads it". Broad points
at calendar, seasonality or a general price move; concentrated points at one
product or category. Measured over the **product** dimension (the finest, and
the only one always present) and over every member, not the named few - over
the top five every change looks concentrated, since those are chosen for being
the largest movers. A total that did not move has no direction, so a flat
month is `mixed` with both shares 0.0 rather than counting every member that
fell (3D doubt-review).

**Blank keys are visible buckets, never omissions** (Thach, 3D). A row whose
category or product name is blank joins a bucket under a reserved label -
`(uncategorised)`, `(no product name)`, `(no customer)` - which is ranked and
filtered like any other member, carries `is_data_gap`, and is excluded from
the new/removed lists. Dropping such rows would leave the dimension
reconciling to a subtotal while the report talks about the whole change. The
flag, not the label, identifies the bucket: a real category spelled
`(uncategorised)` stays separate. D3's evidence carries the uncategorised
share of each period's revenue, since how much of the shop is uncategorised is
a data-completeness fact rather than a business one.

**When nothing clears the bar**, the top movers are named anyway and
`size_filter_waived` records it as a structured field, so step 7 can discount
a `concentrated` verdict over members that are all small. A dimension whose
members all fit in the named slots skips the filter without setting that flag:
`customer_type` has four fixed members and the bar is a share of *previous*
revenue, which `new` has none of by definition.

### 7.8 Step 7: Hypothesis evaluation

The catalog is fixed in advance and identical for every run. Every id is
evaluated and reported, including the ones that come out `ruled_out` -
`docs/adr/0005-pre-registered-hypothesis-catalog.md` explains why choosing
hypotheses after seeing the data is the failure mode this prevents.

| Id | Lens | Statement | Contribution or test | Requires |
|---|---|---|---|---|
| D1 | data | Days of data are missing | minus the estimated revenue gap | none |
| D2 | data | Prices shifted uniformly (possible unit or currency issue) | directional: supported when D2 cautions | comparable products |
| D3 | data | Flagged rows concentrated in the current period | directional: supported when D3 cautions | none |
| T1 | time | The calendar explains the change | `calendar_effect` | none (day-count fallback) |
| T2 | time | Seasonality explains the change | `revenue_prev * (LY_cur/LY_prev - 1)` | year-ago pair |
| T3 | time | The change is routine variation | directional: no rule-1 AND no rule-2 **year-over-year** signal on any series, and no masked alert; `inconclusive` whenever `revenue` has no year-over-year verdict, at any file length - `contracts.diagnosis.is_verdict` decides (ADR-0006). Evidence lists every series without a verdict | baseline points for revenue |
| C1 | customers | Fewer new customers | `new_rev(t) - new_rev(t-1)` | customer, previous transition, no left-censoring |
| C2 | customers | More customers lapsed | `lapsed(t) - lapsed(t-1)` | customer, previous transition |
| C3 | customers | Fewer customers came back | `resurrected_rev(t) - resurrected_rev(t-1)` | customer, previous transition, no left-censoring |
| C4 | customers | Customers migrated to weaker segments | directional: change in (At-risk + Hibernating) share minus change in (Champions + Loyal) share, from `metrics.json` | customer |
| B1 | lever | Customers buy less often | level-1 frequency contribution | customer |
| B2 | lever | Baskets got smaller | level-2 units-per-order contribution | net units > 0 |
| P1 | product | Like-for-like prices changed | PVM price effect | products in L |
| P2 | product | Sales mix shifted towards cheaper (or pricier) products | PVM mix effect | products in L |
| P3 | returns | Returns changed | `-delta_returns` | none |
| R1 | localization | The change is concentrated in one product or category | directional: breadth `concentrated` and top member moving with the total | none |
| R2 | product | Products were launched or discontinued | `gross_N(cur) - gross_X(prev)` | none |
| R3 | product | A top product may have run out of stock | active-day rate at least `R3_MIN_ACTIVE_DAY_RATE` in `prev`, then `R3_MIN_ZERO_RUN_DAYS` consecutive zero days in `cur` while the store traded | none |

C4 compares two named segment groups. Stage 2's catalog has six segments: the
2B doubt-review added **"Needs Attention"** for the four of twenty-five R x F
combinations the five named rules leave uncovered. It and "New" count towards
neither group by design - C4 asks whether customers moved from strong to weak,
not whether every segment is accounted for.

R3's wording is fixed: **"consistent with a stockout, verify on the shelf"**,
never "caused by". Point-of-sale data cannot confirm a stockout; published
POS-only detectors catch roughly 63% of stockouts with about 15% false alerts.
This is a different signal from stage 2's `products.velocity` projection - see
`docs/CONTRACTS.md` section 7.

**Verdicts.** `share = contribution / D`, signed, where `D` is the absolute
total of that hypothesis's own lens (or the sum of absolute contributions when
the masked-shift alert is on). A hypothesis can only be `supported` if its
contribution has the same sign as the change it claims to explain.

| Verdict | Rule |
|---|---|
| supported | same sign and `share >= SUPPORTED_MIN_SHARE` |
| partial | same sign and `PARTIAL_MIN_SHARE <= share < SUPPORTED_MIN_SHARE` |
| ruled_out | opposite sign, or below `PARTIAL_MIN_SHARE`, with sufficient data |
| inconclusive | data insufficient (history, left-censoring, too few products) |
| not_testable | no data exists for this cause |

**Headline (code, not AI).** First match wins:

1. Trust `blocked` - state the data problem.
2. D1 supported with `share >= HEADLINE_CONTEXT_MIN_SHARE` - most of the change
   is consistent with missing days, with the estimated gap.
3. T3 supported and no masked-shift alert - within normal variation.
4. Masked-shift alert - the total looks stable but components shifted strongly,
   naming the two largest opposing contributions. **The wording depends on
   `tree.lever.masked_shift_basis`** (ADR-0006): on `yoy` it is stated as a
   finding; on `level` it is stated as a movement that may be seasonal,
   because the rows establishing that the movement was unusual are level-mode
   rows and a seasonal shoulder month has flat revenue and a shifting mix.
   This belongs here and not only in 7.9: the headline is written by code and
   is still produced in degraded mode, where no narration validator runs.
5. Calendar or seasonality explains at least `HEADLINE_CONTEXT_MIN_SHARE` -
   state that.
6. Otherwise the `supported` hypothesis with the largest absolute share, naming
   its lens.
7. Nothing supported - no single tested cause explains most of the change,
   followed by the `partial` ones.

Trust `caution` never changes the headline and is always shown beside it.

**Not testable with this schema** (always listed, never evaluated): X1
marketing and promotions, X2 competitor actions, X3 weather and macro events,
X4 traffic and conversion, X5 margin, X6 country or region (no canonical field,
the 2D finding), X7 sales channel or payment method. Saying what could not be
tested is part of the answer, not an omission.

### 7.9 Step 8: AI narration (the only AI call in stage 3)

- Input: the complete deterministic output of steps 1-7 as JSON. Never raw rows.
- Output: a plain-language summary, an explanation of the headline, a short
  paragraph per `supported` or `partial` hypothesis, and one sentence naming
  what could not be tested.
- **The AI may not choose, add, remove or re-rank hypotheses, and may not
  upgrade a verdict** - an `inconclusive` item may never be described as a
  cause. This is the ADR-0002 line applied to stage 3: the engine decides what
  is true, the AI only says it in words.
- Validator (code): every number in the AI's text must match a number in the
  evidence within `AI_NUMBER_TOLERANCE` (exact for counts), every hypothesis id
  referenced must exist, and the not-testable sentence must be present. Failure
  spends the run's single shared retry, then degraded mode.
- **The number match is on magnitude, not on sign** (Thach, 3C; build this in
  3F). Bridge terms are stored signed, so `lapsed` is `-219000.0` in the
  evidence while the natural English for it is "lost 219,000" - a sign-aware
  comparison would reject the correct sentence and spend the retry, then
  degrade a run whose narration was right. The direction is already fixed by
  the deterministic blocks; the AI is being checked for inventing *figures*,
  not for choosing a preposition.
- **The validator rejects any sentence that calls a `level`-mode series
  normal, or calls it certainly unusual** (ADR-0006; build this in 3F). A
  level chart is centred on the average of every month, so it is in the wrong
  place for any month with a season and its row is descriptive, not a verdict.
  The banned shapes are both directions: "revenue was within normal
  variation" and "revenue was unusually low" are equally unsupported when the
  row's `mode` is `level`. Permitted wording describes the chart and says what
  was not available - "revenue was 25,000 against a monthly average of 52,000;
  there was no comparable month last year, so this month was not judged
  against its own season."
- **The same applies to a masked-shift alert whose `lever.masked_shift_basis`
  is `level`.** The alert may be stated - components did move, and the total
  did hide it - but not as certainly unusual, because a seasonal shoulder
  month has flat revenue and a shifting mix. Phrase it as possibly seasonal.
  A `yoy` basis carries no such hedge.
- Degraded mode: `ai_findings` and `model_used` are `null`, and the
  deterministic headline, hypothesis table and every computed block are still
  written and shown. Stage 3 never fails because of the AI.
- Model: `MODEL_REASONING` (`docs/adr/0003-model-selection-policy.md`).

### 7.10 Thresholds (`stages/diagnose/thresholds.py`)

Documented constants inside the stage package, not `.env` settings: stages
cannot read backend `Settings` (SEC-4), and this project's "no defaults in
`.env`" rule would otherwise add a mandatory variable per threshold. All values
are heuristics until calibrated against real data.

| Constant | Default | Used in |
|---|---|---|
| `SUPPORTED_MIN_SHARE` / `PARTIAL_MIN_SHARE` | 0.20 / 0.05 | 7.8 |
| `HEADLINE_CONTEXT_MIN_SHARE` | 0.50 | 7.8 rules 2 and 5 |
| `MASKED_GROSS_TO_NET` | 3.0 | 7.6 |
| `XMR_FACTOR` | 2.66 | 7.5, the fallback estimator (3 / d2) |
| `XMR_MEDIAN_FACTOR` | 3.145 | 7.5, the default estimator (3 / d4) |
| `XMR_MIN_BASELINE_POINTS` | 8 | 7.5 |
| `XMR_RUN_LENGTH` | 8 | 7.5 rule 2 |
| `XMR_REL_TOLERANCE` | 1e-9 | 7.5 margin, residue only (3D3) |
| `XMR_RESIDUE_FLOOR` | 1e-6 | 7.5 margin (3D3) |
| `XMR_MIN_SPREAD_SHARE` | 0.01 | 7.5 minimum spread, level (3D3) |
| `XMR_MIN_SPREAD_RATE` | 0.01 | 7.5 minimum spread, rate series (3D3) |
| `XMR_MIN_SPREAD_YOY_POINTS` | 2.0 | 7.5 minimum spread, yoy (3D3) |
| `YOY_LAG_MONTHS` | 12 | 7.2, 7.5, and `YOY_MODE_MIN_MONTHS` |
| `YOY_MIN_BASE_SHARE` | 0.03 | 7.5 year-over-year base guard, a policy (3D6) |
| `YOY_MODE_MIN_MONTHS` | **derived**, see below | 7.5 |
| `HISTORY_MAX_MONTHS` | 24 | 7.2 |
| `CALENDAR_MIN_WEEKS` | 8 | 7.4 |
| `D1_CAUTION_DAYS` / `D1_CAUTION_SHARE` | 3 / 0.10 | 7.3 |
| `D1_BLOCK_SHARE` | 0.50 | 7.3 |
| `D2_MIN_PRODUCTS` / `D2_MIN_ROWS` | 20 / 3 | 7.3 |
| `D2_CLUSTER_SHARE` / `D2_CLUSTER_WIDTH` | 0.80 / 0.02 | 7.3 |
| `D2_NEUTRAL_BAND` | 0.90 to 1.10 | 7.3 |
| `D2_SMALL_MIN_PRODUCTS` / `D2_SMALL_CLUSTER_SHARE` | 3 / 0.80 | 7.3 (3B) |
| `D2_SMALL_RATIO_HIGH` / `D2_SMALL_RATIO_LOW` | 5.0 / 0.2 | 7.3 (3B) |
| `D3_RATIO` / `D3_MIN_SHARE` | 2.0 / 0.02 | 7.3 |
| `MEMBER_MIN_REVENUE_SHARE` / `MEMBER_MIN_ORDERS` | 0.02 / 30 | 7.7 |
| `MEMBERS_PER_DIMENSION` | 5 | 7.7 |
| `BREADTH_BROAD` / `BREADTH_CONCENTRATED` | 0.70 / 0.50 | 7.7 |
| `C4_SUPPORT_POINTS` / `C4_RULE_OUT_POINTS` | 5.0 / 1.0 | 7.8 |
| `LEFT_CENSOR_MONTHS` | 3 | 7.6 |
| `R3_MIN_ACTIVE_DAY_RATE` / `R3_MIN_ZERO_RUN_DAYS` | 0.50 / 7 | 7.8 |
| `AI_NUMBER_TOLERANCE` | 0.005 | 7.9 |

`YOY_MODE_MIN_MONTHS` is **written as an expression, not a number**:

```python
YOY_MODE_MIN_MONTHS = 12 + XMR_MIN_BASELINE_POINTS + 1  # = 21
```

Derivation (index complete months 1..N, with `current` = month N): a YoY point
at month `m` needs month `m-12`, so YoY-capable baseline months run 13..N-1,
giving `N - 13` points. Requiring `XMR_MIN_BASELINE_POINTS` of them gives
`N >= 12 + XMR_MIN_BASELINE_POINTS + 1`. Tying the two constants together in
code stops them drifting apart: raising the baseline requirement must raise the
months needed to earn YoY mode. A flat 25 was rejected for being arbitrary and
for excluding the recommended demo dataset, which has exactly 24 complete
months (2009-12 to 2011-11, since 2011-12 is partial) and would never have
reached YoY mode - the mode it was chosen to demonstrate.

Note the interaction with `HISTORY_MAX_MONTHS = 24`: the window caps how many
*baseline points* are used, while `YOY_MODE_MIN_MONTHS` counts how many months
must *exist* in the file. A file with 24 complete months yields 11 YoY baseline
points, comfortably above the minimum.

### 7.11 Validation: planted-cause scenarios

A fixed-seed generator builds a synthetic store (26 complete months, ~400
customers, 6 categories x 10 products, retail weekday weights, a small share of
returns). Twelve scenarios each plant exactly one cause - S0 nothing, S1
calendar, S2 like-for-like price cut, S3 mix shift, S4 lapsed customers, S5
missing days, S6 masked shift, S7 stockout, S8 discontinued products, S9
seasonality, S10 a x100 price error, S11 the same build truncated to its last
6 complete months. S11 plants no cause and still must not produce headline
rule 3: with every signal `insufficient_history` and T3 `inconclusive`, "within
normal variation" would assert a verdict the data cannot support. It is the
matched pair to S0, which plants nothing over 26 months and *is* expected to
produce rule 3. Tests fail unless each scenario produces
its expected headline or verdict, S0 produces zero `supported` hypotheses, and
the whole suite produces at most one `supported` hypothesis not implied by its
planted cause. The suite's headline accuracy, decoy count and false-alarm count
are printed by the tests and quoted in the README: that is the evidence the
engine works.

## 8. Strategy step (stage 4)

Input: `metrics.json` + `diagnosis.json` + the computed `forecast` block.
Required output: 3 to 5 ranked recommendations, each with insight, cause, action,
expected_impact (arithmetic shown from input numbers), how_to_measure,
confidence; plus a `do_not_do` list.

Mapping logic the prompt enforces:
- Decline driven by frequency, not customer count -> fix the purchase cycle
  (replenishment reminders, bundles), not acquisition spend
- At-risk segment growing -> win-back sized by that segment's historical spend
- Champions -> loyalty and early access, never discounts
- Revenue concentrated in few products (Pareto) -> focus budget there; bundle
  weak products with strong ones
- Stockout risk from the forecast -> reorder recommendation with units

## 9. Failure handling

1. Invalid JSON or schema violation -> one retry with the validation errors
   appended (shared budget)
2. Second failure -> `AIUnavailable`:
   - stage 1: degraded mode, user builds the plan manually from the catalog
   - stage 3: every deterministic block (`frame` through `headline`, section 7)
     is still produced and shown, including the code-written headline sentence;
     only `ai_findings` and `model_used` are `null`
   - stage 4: the computed `forecast` block still produced and shown; narrative
     sections marked "unavailable" in the report
3. Timeout or network error -> same as 2; the run keeps its state so a retry is
   possible
4. `domain_confidence < 0.5` -> NOT_INVENTORY path (SPECS section 10)
5. Every AI request is logged with token counts for cost review

## 10. Testing requirements

- transforms: one test per action plus edge cases (empty df, single row,
  all-null column, non-numeric in numeric column)
- legality matrix: table-driven tests over every (semantic_type, action) pair
- ai_client: mocked valid, invalid-then-valid, twice-invalid, timeout; a guard
  fixture asserts no real HTTP call escapes the mock in the whole suite
- decomposition: contributions sum to the total change (tolerance 0.5%)
- golden path: a messy fixture CSV runs through all five stages with mocked AI
  and matches a checked-in expected `cleaned.csv`, `metrics.json` and
  `report.json`

## 11. Stage 1 answer checks (1C, 1E)

Both stage-1 AI steps check the answer in the stage, never in the client, and
the run's single retry is spent on a structural problem only.

**Issue counts (schema inference).** The AI decides which issues are worth
reporting and how severe they are; pandas decides every number (CLAUDE.md 3.2).
After `ai_schema.check_answer` accepts an answer, `issue_recount.recount_issues`
rewrites it:
- The figures `profile.json` holds (`missing_values` count and pct,
  `all_null_column`, `duplicate_rows`) must match the profile (a pct within
  0.1, the rounding the AI may copy it with). A mismatch is an AI error: it uses
  the retry.
- Every other count is recomputed from `raw.csv` (`issue_counts.py`) and
  overwrites the AI's. A difference does NOT use the retry: the AI has no figure
  to copy for these codes, so an estimate from at most 30 sample rows is
  expected to be off. (An impossible count, more than the file's rows or cells,
  is still rejected by `check_answer` before this step.)
- A count of 0 removes the issue, whatever its source. An issue at a level its
  code cannot describe (`duplicate_rows` under a column, `negative_values` on
  the dataset) and a code repeated for one column are dropped: they have no
  source for their number.
- `near_duplicate_labels` is reported only for text and categorical columns
  (decided by Thach in 1F). It ignores punctuation, which is right for "Coca-Cola" and
  "coca cola" and wrong for a number: "-2" and "2" are not one label, and the 1E run on
  real data counted exactly that in a quantity column. An identifier, a date and a boolean
  are outside it by the same decision. In a text column "A+" and "A-" still count as
  near-duplicates; that was accepted.
- `pct` is not filled in for computed codes: only a percentage the profile holds
  is legal (CONTRACTS section 3), so a replaced count cannot contradict a stale
  percentage. The `detail` sentence of both dataset issues is rewritten from the
  figures (the AI's can quote another number than the one beside it); only its
  severity is kept. The AI's other free text (`examples`, `domain_reasoning`) is
  not checked for numbers.
- The counts describe `raw.csv` as uploaded, before any cleaning. The two date
  codes decide "is this a date column?" on the first 500 cells before converting
  the whole column, so a text column costs milliseconds; a column that only
  turns into dates after 500 rows is treated as text.

**Business key.** The columns that identify one transaction: the column mapped
to `sku` (the `product_name` column when there is none), the `transaction_date`
column, and the `transaction_type` column when there is one. Without an identity
column and a date there is no key: the count is 0 and `flag_duplicate_keys` is
not proposable. Including the type keeps a stock-in and a stock-out of the same
product on the same day from being reported as one collision. Rows with a
missing part of the key count as sharing it, exactly as `flag_duplicate_keys`
marks them (decided by Thach in 1E).

**Cleaning plan (`ai_plan.check_plan`).** The AI receives the bounded profile
(25 columns) and the schema result trimmed to what a plan needs (no `examples`,
no `domain_reasoning`, `detail` cut to 100 characters), plus, from the catalog,
each column's `legal_actions`, the `dataset_legal_actions` and the
`business_key`, so the whitelist is given, not inferred. The answer is rejected
whole, and every problem is reported in the one retry message, when:
- a column is missing, unknown or listed twice (a tidied name still resolves);
- an action or alternative is outside the catalog or not legal for the column
  (`transform_catalog.illegality_reason`, including the required-field rule);
  a dataset action is not a dataset-scope action, or is listed twice;
- an action's params fail `transform_params.params_problem`: unknown or missing
  params, a value the transform would refuse, an `impute_constant` value that is
  empty or a word profiling reads as missing ("N/A", "NULL": it would turn back
  into a gap), a `parse_datetime` format that is empty, malformed or has no year
  (`ISO8601` is accepted; leave `format` out to parse each cell on its own);
- more than 2 different alternatives (repeats and the chosen action are tidied
  away, not rejected), or an empty rationale;
- `flag_duplicate_keys` uses keys other than the business key, a key column the
  same plan drops (`drop_column` runs first), or is proposed (as the action or
  as an alternative) for a file that has no business key. Each of these is
  reported whatever else is wrong with the params.
An omitted or null `params`, `alternatives`, `rationale` or list of actions
defaults instead of failing the schema, so an unrelated illegal action is still
reported in the same retry.
Types and canonical fields in the plan are copied from `schema_inference.json`,
never from the answer. A column beyond the first 25 gets `flag_only` with a note.
Nothing the AI chose is echoed raw into the retry prompt (strings are escaped
and shortened; a list of column names shows the first few and a count; the
message is capped at 3500 characters with a count of the problems it left out,
dataset problems first). A broadly wrong answer (every column with several
mistakes) therefore reports its first problems and how many are left, which is
the accepted limit of a single retry. A degraded run writes no `plan_proposed.json`
and removes an earlier one; `plan_final.json` is never touched.

**Not checked at plan time** (they depend on the data, so 1F's preview and the
execution report show them): a `format` with a year that does not match the
cells (every date is flagged), `standardize_categories` keys absent from the
data, a `cast_type` to integer on values beyond int64 (flagged, not raised),
`dayfirst` (pandas applies it to every ambiguous cell, ISO-written ones included,
so it is right only for a column written day-first throughout), and
a plan that drops a column the data needs elsewhere (checked at execution, section 12).
An alternative carries a name only: its params are supplied when the user picks it.

## 12. Previewing and executing a plan (1F)

**The plan the user submits is checked again** (`plan_validation.validate_final_plan`),
by the preview and by the execution, against the file itself. Nothing the client
sends is trusted, and a plan that was valid when the AI proposed it is not assumed
to still be. What differs from the AI's answer (section 11): the plan's own
`semantic_type` and `canonical_field` decide what is legal (the user may have
changed either); `flag_duplicate_keys` may use any columns of the file, not only the
business key; `alternatives` are not checked, since they are never executed; names
must match the file exactly. The whitelist and the legality matrix are the shared
`illegality_reason` and `params_problem`. Rejected: an action outside the catalog or
illegal for its column, bad params, a column missing, unknown or planned twice, a
canonical field mapped by more than one column, a dataset action that is not
dataset scope or is listed twice, `flag_duplicate_keys` on a column that is not in
the file or that the plan drops. All of them are reported together
(`InvalidPlanError.problems`, INVALID_PLAN, 422). Executing also requires
`product_name`, `transaction_date` and `quantity` to be mapped and kept: a plan that
drops a column mapped to one of them is rejected (decided by Thach in 1F). The
preview does not require it, because it refreshes while the user is still mapping.

**Order.** `cleaning.apply_plan` runs the plan in the fixed order of section 6, the
one place a plan runs, for both the preview and the execution. `drop_rows_missing`
is its own step before the imputations (decided by Thach in 1F).

**Executing** (`cleaning.execute_run`) re-reads `raw.csv`, checks the plan, applies
it and writes `cleaned.csv`, `plan_final.json` (the plan that ran) and
`cleaning_report.json`. `cleaned.csv` keeps the source column names, writes dates
as ISO 8601 (2024-01-05, or 2024-01-05T10:30:00 when there is a time) and holds the
`__flag_*` columns the run added. The three files are written to temp files first
and renamed into place only when all exist, the report last, so a report on disk
means the run finished. Each existing file is moved aside before its replacement is
renamed in, and if anything fails (a full disk, a file another process holds open,
which Windows refuses to replace) every file is put back as it was, or removed if it
did not exist, with no temp or backup file left; a restore that fails is added to the
error. Files are flushed to disk before the rename. Two concurrent executions of
one run are not prevented here: the caller claims the run first (SPECS section 3). An action that fails on the data is a `CleaningError` naming the action and the
column, and a plan that leaves no row is refused (`CleaningError`); nothing is
written in either case, and the run is reported as CLEANING_FAILED (422, SPECS
section 10; decided by Thach at the end of 1F). `encoding_fallback` is warned when the file was decoded as
latin-1. The output is always UTF-8.

**Previewing** (`preview.preview_run`) runs the same engine on a bounded sample and
writes nothing. A file of up to 500 rows is previewed whole, and then the result is
exactly what the execution writes. A larger file gets a deterministic 500-row
sample: the problem rows found in the first 50,000 rows (up to 40 of each kind) plus
rows spread evenly over the whole file, first and last included. Anything computed
from the data (a median, exact-duplicate detection) is then the sample's, so on a
large file the figures are indicative. Of the sample, 20 rows are shown: every kind
of effect (each changed column, a dropped row, a flag) before any repeats, then the
other affected rows, then unaffected rows spread over the sample. Each shows its
cells before and after and which columns changed; a dropped row shows no after.
Per column, the missing share and the number of distinct values before and after.
A cell is cut at 200 characters for display; a change beyond the cut is still seen.

**Mixed UTC offsets.** A date column written with offsets ("2024-01-06T01:00+10:00")
keeps the date and time as written and drops the offset (decided by Thach in 1F):
read as UTC that cell would become 2024-01-05, and a report by day needs the
store's own date. The detectors (is this a date?) still read offsets as UTC, since
they only need a cell to parse. The change log says when offsets were dropped.

Measured on this machine (SPECS section 11 budgets: preview 3 s, execution 30 s):

| file | preview (reads the file) | preview on a parsed frame | execution |
|---|---|---|---|
| 9 columns, 710,000 rows, 60 MB | 1.9 s | about 0.6 s | 6.8 s |
| 40 columns, 500,000 rows, 54 MB | 3.9 s | 1.1 s | 6.7 s |
| 100 columns, 200,000 rows, 54 MB | 3.9 s | about 1.3 s | 7.4 s |
| 400 columns, 50,000 rows, 53 MB | 7.5 s | about 4.5 s | 12.6 s |

Execution is inside its budget everywhere. `preview_run` re-reads and re-parses
`raw.csv` on every call, which alone takes 2.6 s for 54 MB and 40 columns, so it
misses 3 s for a wide file near the ceiling, and the stage cannot remove that. The
preview refreshes on every edit, so the caller (1G) should keep the parsed frame in
memory per run and call `preview_frame` on it; that meets the budget up to about a
hundred columns. Files of hundreds of columns are slower still (the AI sees 25). 1G keeps the frame per
run (`FrameCache`, bounded by a budget in bytes and an idle time; a frame bigger than
the whole budget is previewed from the file every time) and calls `preview_frame`. Its
size was first budgeted in cells: a cell is 16 bytes for a short value and 5,000 for a
5 KB one, so only measured bytes bound the memory. The
cost of finding problem rows is bounded by cells (2,000,000), not only by rows.

**Defects the 1F review found, and what changed** (`docs/SPECS.md` change log):
- A file whose data rows end with an extra delimiter used to be read with every
  value one column to the left (pandas uses the first column as the index): the
  profile and the cleaned file were wrong and the preview crashed. Now the extra
  field is dropped when it is empty, and the file is rejected (PARSE_FAILED) when it
  holds data.
- A source column named like a flag (`__flag_...`, which a cleaned.csv uploaded again
  has) is never overwritten: the flag takes the next free name (`_2`, `_3`). A flag
  column that ends up all False because a later action dropped the flagged rows is
  removed; the change log still says what happened at that step.
- Only finite numbers are numbers: `inf`, `Infinity` and `1e999` are text, as in
  profiling, so a mean or an absolute value can no longer become infinity.
- A cell with no date in it (`now`, `today`, a bare time such as `10:30`) is not a
  date, and neither is one whose year is outside 1900-2100 (pandas read `Jan 5` as the
  year 1): they are flagged like any cell that does not parse. Before, `now` gave the
  time of the run and `10:30` today's date, so the same file gave a different result
  on another day. UTC offsets are recognised in the forms people write (`+10`, `-5`,
  `UTC`, `GMT+2`) as well as `+01:00` and `Z`, and the change log says offsets were
  dropped only when they were.
- A `standardize_categories` mapping may not send a label to an empty text or a
  missing-value token, and the report warns (`text_reads_as_missing`) how many cells
  hold text that would read back as missing once `cleaned.csv` is read again (a
  trimmed " N/A ", a trimmed "   ").
- On a sampled file the written date format (date only, or with a time) is decided on
  the sample, so a preview can show `2024-01-05` where the execution writes
  `2024-01-05T00:00:00`.

**Known limits** (open, decisions for later): a plan has one action per column, so a
column cannot be both trimmed and have its blank rows dropped (a cell of only spaces
is dropped by `drop_rows_missing` itself, which covers the required fields), and the
plan cannot say that `transaction_date` must be parsed. Thach decided to keep one
action per column until the review screen (6B) shows what is needed, rather than change
the contract on a guess. Cells beyond microsecond precision are truncated when a date
column is written. A file of hundreds of columns makes the preview slow, and there is no
limit on the number of columns; that is left to 8A.

