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

