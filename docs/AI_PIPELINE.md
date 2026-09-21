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
| 3 | diagnose | root cause | `prompts/root_cause.md` | `claude-sonnet-5` | metrics + decomposition | `diagnosis.ai_findings` |
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
  quantity | unit_price | transaction_type | supplier | customer | note | ignore
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
| drop_rows_missing | any | - | drop rows null in this column |
| drop_column | any | - | remove the column |
| parse_datetime | datetime | format?, dayfirst? | parse to ISO 8601; unparseable -> NaT, flagged |
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

- flag_duplicate_keys: `keys` must be the business key, defined in section 11
  (the count reported for `duplicate_business_key` and the rows this flags then
  describe the same thing)

**Fixed execution order** (not AI-controlled, because order changes results):
drop_column -> remove_exact_duplicates -> trim_whitespace -> normalize_case ->
parse_datetime / cast_type -> missing-value handling -> standardize_categories ->
fix_negative / clip_outliers_iqr -> flags.

## 7. Root cause step (stage 3)

Input to the AI: `metrics.json` plus the computed `decomposition` block
(`docs/CONTRACTS.md` section 7). The decomposition itself is computed in pandas
by sequential substitution, and tests assert the factor contributions sum to the
total change within tolerance.

Required output: headline, root_cause (driver, evidence, secondary), ruled_out
(at least two hypotheses with the figure that rules each out). Rejecting
hypotheses with evidence is mandatory - it is the main defence against
plausible-sounding but unsupported narratives.

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
   - stages 3 and 4: computed blocks (decomposition, forecast) still produced and
     shown; narrative sections marked "unavailable" in the report
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
`parse_datetime` on a column of mixed UTC offsets, which fails rather than pick a
time zone (a decision for 1F). An alternative carries a name only: its params are
supplied when the user picks it.
