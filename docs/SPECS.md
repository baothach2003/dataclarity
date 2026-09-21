# DataClarity - Functional Specification (SPECS v2)

Source of truth for product behavior. Stage data schemas: `docs/CONTRACTS.md`.
AI internals: `docs/AI_PIPELINE.md`. If code and this spec disagree, the spec
wins until Thach approves a change.

## 1. Scope

### In-scope (v1)
- CSV upload (max 50MB, `.csv`, UTF-8 with latin-1 fallback)
- Stage 1 Collect: profiling, AI schema inference, AI cleaning plan, user review
  and editing with before/after preview, deterministic execution, clean CSV +
  change report
- Stage 2 Analyze: KPIs, RFM segments, product Pareto, velocity
- Stage 3 Diagnose: revenue decomposition + AI root cause with ruled-out
  hypotheses
- Stage 4 Predict: interpretable forecast + AI recommendations with expected
  impact and measurement plan
- Stage 5 Report: assembled 3-layer report (numbers, causes, actions) as HTML +
  in-app Insights page
- Import of approved clean data into PostgreSQL; dashboard over imported data
- Public demo, no login, protected by rate limits and retention cleanup

### Out-of-scope (v1) - Backlog only, never silently added
XLSX/JSON input, multi-file merge, auth/accounts, cross-session history, PDF
export, run-to-run comparison, ML forecasting models, i18n, mobile layout.

## 2. Why five stages

Each stage answers a different question and is independently replaceable:

| Stage | Question | Who cares |
|---|---|---|
| Collect | Can I trust this data? | analyst, before anything else |
| Analyze | What is happening? | manager reading KPIs |
| Diagnose | Why is it happening? | manager deciding where to act |
| Predict | What next, and what should we do? | marketer planning a campaign |
| Report | How do I present this? | everyone in the meeting |

Design consequence: a user can stop after stage 1 (just wanted clean data) and
the product is still useful. Stages 2-5 are additive, not mandatory.

## 3. User Flow

1. **Upload** - drop a CSV. Client checks type/size, server re-validates.
   Run created. State `uploaded`.
2. **Analyzing** - profiling + AI schema inference + AI cleaning plan. Shown as
   one step with a 3-part progress indicator. State `planned`.
3. **Review** - the core screen. User inspects and edits semantic types,
   canonical mapping, and per-column actions; preview updates on each change;
   clicks **Confirm & Clean**. State `cleaned` after execution.
4. **Results** - what changed, downloads, and two CTAs: **Run full analysis**
   (stages 2-5) and **Import to dashboard**.
5. **Analyzing insights** - stages 2, 3, 4 run sequentially with progress
   (Analyze -> Diagnose -> Predict). State `analyzed`.
6. **Insights** - KPI cards, the diagnosis panel (driver, evidence, ruled out),
   the ranked recommendations, forecast chart. Download the HTML report.
7. **Dashboard** - persisted view over imported data (inventory KPIs, low stock,
   top sellers, trend).

State machine: `uploaded -> profiled -> planned -> cleaned -> analyzed ->
imported`, plus `failed(reason)` from any state and `expired` after retention.
Transitions enforced server-side; out-of-order calls return 409.

## 4. Screens

### 4.1 Upload page
Drag-drop + file picker, size/type validation, privacy note (only a bounded
sample of rows is ever sent to the AI), progress bar, then the Analyzing state
with a 3-step indicator. Errors rendered inline per section 10.

### 4.2 Review screen (most important screen in the product)

**A. Dataset summary strip:** rows, columns, duplicate rows, overall missing %,
and the AI's domain confidence that this is inventory/sales data.

**B. Column table** - one row per source column:

| Field | Editable | Notes |
|---|---|---|
| Source column name | no | as it appears in the file |
| Detected dtype | no | from profiling |
| Semantic type | YES (dropdown) | numeric_continuous, numeric_discrete, categorical_nominal, categorical_ordinal, datetime, identifier, boolean, text |
| Canonical mapping | YES (dropdown) | canonical field or `ignore` |
| Issues | no | badges with counts; hover shows examples |
| Proposed action | YES (dropdown + params) | only actions legal for that semantic type and issue set; AI rationale shown on expand |
| Confidence | no | columns below 0.7 visually flagged for attention |

UI guardrails: Confirm stays disabled until `product_name`, `transaction_date`
and `quantity` are mapped; mapping two columns to the same canonical field is
blocked inline; changing semantic type re-filters the legal action list.

**C. Preview pane:** before/after on a 20-row sample chosen to include affected
rows (not `head()`), changed cells visually marked, plus per-column deltas
(missing % and unique count, before vs after). Refreshed via the preview
endpoint on every plan edit, debounced 400ms.

**D. Actions:** Confirm & Clean (primary), Reset to AI proposal, Cancel.

### 4.3 Results page
Cards: rows in/out, cells imputed, rows dropped with reasons, duplicates removed,
categories standardized, dates parsed. Expandable per-action detail. Downloads:
`cleaned_<name>.csv`, `cleaning_report.json`. CTAs: Run full analysis, Import to
dashboard.

### 4.4 Insights page (stages 2-4 output)
- KPI cards with period-over-period deltas
- Decomposition visual: how much of the change came from customers vs frequency
  vs AOV
- Diagnosis panel: driver, evidence, secondary contributors, ruled-out
  hypotheses (showing what was ruled out is a deliberate trust feature)
- Recommendations list: priority, insight, cause, action, expected impact with
  its arithmetic, how to measure
- Forecast chart with a confidence band, or an explicit "insufficient history"
  message when the data is too short
- Download the HTML report

### 4.5 Dashboard page
Cards (total products, low-stock count, inventory value), 30-day trend line with
product selector, top-5 bar chart, low-stock table sorted by predicted stockout
date. Velocity math: average daily units over the last N=14 days, guarded against
zero velocity.

## 5. The Confirmation Contract (stage 1)

The frontend submits the final, user-edited plan. The backend re-validates it
(catalog whitelist, legality matrix, mapping rules), executes exactly that plan,
and builds the change report from what actually ran. The AI is not consulted
again. This is why the product can claim AI assistance without AI opacity.

## 6. Cleaning Principles (what "standard practice" means here)

- Missing numeric: median by default (robust to outliers); mean only if chosen
- Missing categorical: mode when missing < 5%, otherwise an explicit "Unknown"
  category rather than fabricating a majority
- Missing required fields (product_name, transaction_date, quantity): drop rows
  with a recorded reason, never impute
- Dates: parse to ISO 8601; ambiguous day/month resolved by majority evidence in
  the column and flagged in the report
- Negative/zero price or quantity: default flag-and-keep (may be a legitimate
  return), never a silent `abs()`
- Duplicates: exact-row duplicates dropped; business-key duplicates flagged only
- Category standardization: trim + case normalization, then merge near-identical
  labels with the mapping shown to the user
- Outliers: IQR flagging by default; clipping is opt-in

## 7. Analysis Requirements (stages 2-4)

- 7.1 Every KPI is computed in pandas and covered by a test with a hand-checked
  expected value. No KPI is ever produced by the AI.
- 7.2 Revenue decomposition uses sequential substitution over
  revenue = customers x frequency x AOV, and contributions must sum to the total
  change within rounding tolerance (asserted in tests).
- 7.3 RFM scoring uses quintiles on the run's own data; the reference date is
  max(transaction_date) + 1 day unless configured otherwise.
- 7.4 Forecasting is interpretable: weighted moving average plus a monthly
  seasonality index, with confidence bands. If history is shorter than 3 periods,
  return `insufficient_history: true` and skip the forecast rather than
  extrapolate from noise.
- 7.5 Seasonality is only claimed when the gap between the highest and lowest
  period exceeds 40% AND at least two cycles of data exist.
- 7.6 Every recommendation must name the metric to watch and the review window.

## 8. API Contracts

- `POST /api/runs` (multipart) -> 201 `{run_id, filename, size_bytes, status}`
- `GET /api/runs/{id}` -> status + which contract files exist
- `GET /api/runs/{id}/profile` -> `profile.json`
- `POST /api/runs/{id}/analyze-schema` -> `schema_inference.json`
- `POST /api/runs/{id}/plan` -> `plan_proposed.json`
- `POST /api/runs/{id}/preview` (body: final plan) -> before/after sample +
  column deltas (sample execution, max 500 rows)
- `POST /api/runs/{id}/execute` (body: final plan) -> `cleaning_report.json` +
  download urls
- `POST /api/runs/{id}/analyze` -> `metrics.json`
- `POST /api/runs/{id}/diagnose` -> `diagnosis.json`
- `POST /api/runs/{id}/predict` -> `forecast.json`
- `POST /api/runs/{id}/report` -> `report.json` + html download url
- `POST /api/runs/{id}/import` -> `{products_created, products_updated,
  transactions_inserted, skipped:[{row, reason}]}`
- `GET /api/dashboard/summary` | `/trend?product_id=&days=30` | `/low-stock`
- Errors always `{error:{code, message, details?}}` with codes from section 10

## 9. Canonical Schema and Database

Canonical fields: `product_name` (required), `sku`, `category`,
`transaction_date` (required), `quantity` (required), `unit_price`,
`transaction_type` (in|out, default out), `supplier`, `customer`, `note`,
`ignore`.

```sql
runs(id, filename, size_bytes, status, created_at, expires_at, error_code)
products(id, sku UNIQUE NULL, name, category, unit_price_latest,
         current_stock, created_at, updated_at)
transactions(id, product_id FK, type, quantity, unit_price, transaction_date,
             customer, source_run_id FK, note)
```
`current_stock` is derived at import (net in minus out, floored at 0 with a
warning in the import summary when it would go negative).

## 10. Errors and Edge Cases (each needs a test and a UI message)

| Case | Behavior | Code |
|---|---|---|
| File > `MAX_UPLOAD_MB` (at most 50MB, SEC-1) | rejected client and server side | FILE_TOO_LARGE (413) |
| Not `.csv` | rejected | UNSUPPORTED_TYPE (400) |
| Empty or header-only | rejected with a clear message | EMPTY_FILE (400) |
| Unparseable / wrong delimiter | sniff delimiter, then reject | PARSE_FAILED (400) |
| Non-UTF8 | latin-1 fallback, warning in the report | success + warning |
| All-null column | flagged; default action drop_column | - |
| Not inventory data (domain_confidence < 0.5) | say so plainly; offer generic cleaning with downloads only; disable mapping-dependent import and stages 2-5 | NOT_INVENTORY (200 + flag) |
| AI invalid twice / API down | degraded mode: profiling + manual plan building still work; stages 3-4 still write their computed blocks with the AI blocks `null` (`docs/CONTRACTS.md` sections 7-8) | AI_UNAVAILABLE (200 + flag) |
| Stage called out of order | rejected | INVALID_STATE (409) |
| Plan contains an unknown or illegal action | whole plan rejected | INVALID_PLAN (422) |
| Plan (at execute) leaves `product_name`, `transaction_date` or `quantity` unmapped, or drops it | whole plan rejected; the preview allows it while the user is still mapping | INVALID_PLAN (422) |
| A valid plan fails on this data (an action raises, or no row is left) | run `failed`, nothing written; the message names the action and the column | CLEANING_FAILED (422) |
| Fewer than 3 periods of history at stage 4 | `insufficient_history: true`, no forecast | success + flag |
| Rate limit exceeded | rejected | RATE_LIMITED (429) |
| Run expired by retention | rejected with re-upload hint | EXPIRED (410) |

## 11. Non-Functional Requirements

- Performance: profiling and preview under 3 s for a 50MB file on the dev
  machine; full stage 1 execution under 30 s; stages 2-5 under 60 s combined.
  Synchronous processing is acceptable at this size
- AI budget: max 4 calls per run plus 1 shared retry; inputs bounded (60 columns,
  30 sample rows, 10 top values per column)
- Abuse guards: 10 uploads/hour/IP; 24-hour retention then a cleanup job deletes
  run directories and marks runs `expired`
- Privacy: uploaded data never leaves the server except the bounded sample sent
  to the Anthropic API; stated plainly on the Upload page
- Security: no secrets in code; CORS restricted by config; files stored under
  server-generated UUIDs, never user-supplied paths (testable detail: SEC-1 to
  SEC-5 below)
- Accessibility: keyboard-navigable review table; color is never the only signal

### Security requirements (testable)

Each item states the behaviour and the test that proves it. The mechanisms for
AI validation live in `docs/AI_PIPELINE.md`; the quality gates that run these
tests live in `CONSTRAINTS.md`.

- **SEC-1 Upload size and type.** The server enforces the configured cap
  `MAX_UPLOAD_MB` (1 MB = 1,048,576 bytes). `MAX_UPLOAD_MB` must not exceed the
  50MB design ceiling in section 1; the app refuses to start unless it is a
  positive integer no greater than 50. A
  file of exactly the cap is accepted; a file
  one byte over returns 413 `FILE_TOO_LARGE`. A filename whose extension is not
  `.csv` (case-insensitive) returns 400 `UNSUPPORTED_TYPE`. The browser-supplied
  MIME type is not trusted and not checked. Content that cannot be read as a CSV
  is handled by `EMPTY_FILE` and `PARSE_FAILED` (section 10), not by the type
  check. Test: boundary sizes, `.CSV` accepted, `.xlsx` and `.csv.exe`
  rejected, startup fails for `MAX_UPLOAD_MB` of 0 and of 51.
- **SEC-2 Rate limit on AI endpoints.** Every endpoint whose handler can trigger
  an Anthropic API call is rate-limited per client IP. The client IP is the
  address recorded by the deploy's own proxy, never a value the client can set
  in a header. The limit is a required configuration value, set to 40 requests
  per hour per IP in `.env.example` when 8B adds it (10 uploads x 4 AI steps).
  The check runs
  before any AI call; over the limit returns 429 `RATE_LIMITED`. A
  rate-limited run must still reach the same outcomes as degraded mode
  (`docs/AI_PIPELINE.md` section 9): manual plan building in stage 1, and the
  computed blocks of stages 3 and 4. The run-state transition that achieves
  this is specified when 8B is implemented. The count may live in process memory (no extra
  infrastructure in v1), so a restart resetting it is accepted. This limit is
  separate from the 10 uploads/hour/IP guard above and from the per-run AI
  budget. Test: request N+1 within the window returns 429 and the mocked AI
  client records no call.
- **SEC-3 LLM output is untrusted.** Rule: `CLAUDE.md` section 3.2; mechanism:
  `docs/AI_PIPELINE.md` sections 3 and 9. Testable behaviour: a mocked AI
  response that fails schema validation, or that contains an action outside the
  catalog, never reaches a contract file or the transform engine. AI-generated
  text is escaped wherever it is rendered (frontend and `report.html`), never
  inserted as HTML. Test: a mocked response with a schema violation, and one
  with an off-catalog action, leave no contract file written; a mocked response
  carrying `<script>` in a text field appears escaped in the rendered output.
- **SEC-4 Secrets only from the environment.** Secrets (`ANTHROPIC_API_KEY`,
  the credentials in `DATABASE_URL`) come only from environment variables or
  the `.env` file (`CLAUDE.md` section 5), never from source code, fixtures or
  contract files. Stages and `shared/` never import `backend/` to get them;
  they receive them from their caller or read the same sources themselves (the
  mechanism is decided with the AI client). No secret value appears in logs,
  API responses, or error `details`. Test: with a distinctive fake key and
  database password (strings that occur nowhere else in the test setup),
  neither appears in a startup validation error, an API error response, or
  captured logs.
- **SEC-5 CORS only from `ALLOWED_ORIGINS`.** The CORS allow-list is exactly the
  origins in `ALLOWED_ORIGINS`. A request from an unlisted origin receives no
  `Access-Control-Allow-Origin` header (covered by
  `tests/backend/test_cors.py`). The app refuses to start when `ALLOWED_ORIGINS`
  is empty, or when any entry contains `*` or is `null`. Test: startup fails for
  `""`, `"*"`, `"https://*.vercel.app"` and `"null"`.

## 12. Design

All screens have hi-fi Figma frames (Thach, Figma Pro).
`docs/FIGMA_DESIGN_NOTES.md` records the file link, node id per screen, design
tokens and component patterns. Frontend sessions must open the referenced frame
before building; never invent layout or tokens.

## 13. Change log

Newest first. One entry per documentation session that changes a
source-of-truth file.

### 2026-09-21 - Preview, execution and the order of a plan (Phase 1F)
- What: `docs/AI_PIPELINE.md` section 12 (re-validating the plan, executing,
  previewing, mixed UTC offsets), a rewritten fixed order in section 6
  (`drop_rows_missing` before the imputations) and the `parse_datetime` row.
  `docs/CONTRACTS.md` sections 4 and 5 state how `plan_final.json` and the report's
  values are built. Section 10 of this file gains one INVALID_PLAN row.
- Why: decided by Thach in 1F. A date with a UTC offset keeps the date as written
  (read as UTC it moves a day, and a report by day needs the store's date). The
  missing-value step was one group, so a median depended on the order of the
  columns in the plan; dropping first makes it the median of the rows that stay.
  A plan that drops a required field cannot feed stages 2-5, and Confirm is locked
  until they are mapped (4.2), so the execution rejects it. Also: the execution
  writes `plan_final.json` (CONTRACTS lists it as stage 1 output D, and no
  sub-phase owned it).
- Decided by Thach at the end of 1F: `drop_rows_missing` also drops a cell of only
  spaces; `near_duplicate_labels` is reported only for text and categorical columns;
  the date range 1900-2100 stays; one action per column stays until the review screen
  (6B) shows what is needed; CLEANING_FAILED (422) is the code for a run that fails on
  its data (the row added to section 10 above); a limit on the number of columns is
  left to 8A.
- Review (one doubt-driven cycle, cross-model skipped by Thach): 17 findings, all
  actionable ones fixed and listed in AI_PIPELINE section 12. The preview budget
  (SPECS section 11: 3 s) is met only when the caller keeps the parsed file in
  memory and only up to about a hundred columns; execution meets 30 s everywhere.
  Two changes reach outside the stage: profiling now rejects a file whose rows have
  more fields than the header when the extra field holds data (PARSE_FAILED), and
  a date outside 1900-2100 is treated as not a date (a range chosen in 1F, for
  Thach to confirm).
- Files: `docs/AI_PIPELINE.md`, `docs/CONTRACTS.md`, `docs/SPECS.md`,
  `stages/ingest/transform_catalog.py`, `stages/ingest/profiling.py`,
  `PROJECT_PLAN.md`.
- Unchanged on purpose: the 16 actions, the legality matrix, `schema_version` `1.0`,
  and every field of every contract file.

### 2026-09-21 - Cleaning plan validation and issue counts (Phase 1E)
- What: `docs/AI_PIPELINE.md` gains section 11 (issue counts computed by pandas,
  the business key, the cleaning-plan checks and what they leave to 1F) and a
  pointer from section 6. `docs/CONTRACTS.md` section 3 says where an issue's
  `count` comes from, section 4 states the rules for `alternatives` and corrects
  its dataset-action example, and section 10 records both. `prompts/cleaning_plan.md`
  now lists each action's params, the per-column `legal_actions`, the business key
  and the dataset-action rules.
- Why: 1C could only check the three counts the profile holds, and 1D had
  computed the rest without a home. Decided by Thach in 1E: pandas overwrites the
  AI's count without a retry and a count of 0 removes the issue; `pct` stays null
  for computed codes; the business key is sku (else product name) + transaction
  date + transaction type when there is one. Found while implementing: the
  CONTRACTS example gave a dataset action the alternative `flag_only`, which the
  legality matrix (and `transforms.flag_only`, which needs a column) rules out.
- Also: `shared/ai_client.py` now treats an answer holding a lone UTF-16
  surrogate as invalid (AI_PIPELINE section 3), found by the 1E review: it
  crashed the retry request and the contract write, in the schema step as well.
- Files: `docs/AI_PIPELINE.md`, `docs/CONTRACTS.md`, `docs/SPECS.md`,
  `prompts/cleaning_plan.md`, `PROJECT_PLAN.md`.
- Unchanged on purpose: the 16 actions, the legality matrix and the required-field
  rule (1D), the 4-call / 1-retry budget, max tokens 3000, `schema_version` `1.0`.
  AI_PIPELINE section 4 asks for a golden-path re-run after a template change;
  that test arrives in Phase 5, so the change is covered by the mocked tests only.

### 2026-09-20 - Transform catalog legality (Phase 1D)
- What: `docs/AI_PIPELINE.md` section 6 no longer contradicts itself.
  `impute_constant` is "categorical/text/boolean" in the table, matching the
  legality matrix, instead of "any". `trim_whitespace` and `normalize_case`
  gain `identifier`. The required-canonical-field rule now says in words that
  it forbids the four imputation actions only, and that every other action the
  semantic type allows stays legal there.
- Why: the three points were found while implementing the matrix as data in
  1D; each could be read two ways, and the wrong reading of the third would
  have made `transaction_date` unparseable, breaking the pipeline's main job.
  `identifier` was added because trimming or re-casing a SKU standardizes how
  a value is written and invents nothing, unlike imputation, which stays
  illegal on an identifier. Decided by Thach in the 1D session.
- Files: `docs/AI_PIPELINE.md`, `docs/SPECS.md`,
  `stages/ingest/transform_catalog.py`,
  `tests/stages/ingest/test_transform_catalog.py`,
  `tests/stages/ingest/test_transforms.py`, `PROJECT_PLAN.md`.
- Unchanged on purpose: the 16 actions themselves, their params, the fixed
  execution order, and every contract file (`TransformAction` in
  `contracts/cleaning.py` already listed all 16, and legality was never part
  of a contract). No `schema_version` bump: no file format changed.

### 2026-09-19 - AI call policy and issue pct (Phase 1C)
- What: `docs/AI_PIPELINE.md` section 2 drops "Temperature 0" (rejected by
  `claude-sonnet-5`), disables thinking, and turns the SDK's own retries off;
  section 3 documents the `call_structured` signature, the `validate`
  callback and the `AIUnavailable` reason codes. `docs/CONTRACTS.md` section 3
  makes an issue's `pct` nullable, in place at `1.0` (section 10 note).
- Why: the documented call would fail with a 400 on the configured model;
  thinking would share the 3000-token budget and the 30 s timeout with the
  JSON answer; the prompt already allowed a null `pct` that the contract
  rejected. Decided by Thach in the 1C session.
  `prompts/schema_inference.md` gained the rules the code enforces: a `pct`
  only for `missing_values` and `all_null_column`, source names copied
  exactly, and the shape of the sample rows. AI_PIPELINE section 1 records
  the 25-column and 100-character bounds for this step.
- Files: `docs/AI_PIPELINE.md`, `docs/CONTRACTS.md`, `docs/SPECS.md`,
  `contracts/profile.py`, `prompts/schema_inference.md`, `PROJECT_PLAN.md`.
- Unchanged on purpose: the 4-call / 1-retry budget, max tokens 3000, the
  30 s timeout, and `schema_version` `1.0`. AI_PIPELINE section 4 asks for a
  golden-path re-run after a template change; that test arrives in Phase 5,
  so the change is covered by the mocked tests only.

### 2026-09-19 - Degraded AI in stages 3-4 (Phase 0B)
- What: `docs/CONTRACTS.md` sections 7 and 8 now say how `diagnosis.json` and
  `forecast.json` represent an unavailable AI step (the AI blocks are
  required keys with nullable values, all null or all filled; the computed
  blocks are always filled). Section 10 records why this was done in place at
  `1.0`. The section 10 error row "AI invalid twice / API down" in this file
  now covers stages 3-4.
- Why: `docs/AI_PIPELINE.md` section 9 requires stages 3-4 to keep writing
  their computed blocks when the AI fails, but the contracts made the AI blocks
  mandatory. Found while writing the `contracts/` models; decided by Thach.
- Files: `docs/CONTRACTS.md`, `docs/SPECS.md`, `PROJECT_PLAN.md`.
- Unchanged on purpose: `schema_version` stays `1.0` (no contract file had been
  written yet); `docs/AI_PIPELINE.md`.

### 2026-09-19 - Integrate engineering skills into the project workflow
- What: created `CONSTRAINTS.md` (floor, warn-level coverage and dependency
  checks, exceptions); added SEC-1 to SEC-5 as testable security requirements
  in section 11; added the "Skill usage" section and a `CONSTRAINTS.md` pointer
  to `CLAUDE.md`; added `PROJECT_PLAN.md` section 13 (Definition of Done for
  every sub-phase) and the Phase 2 ADR item; aligned sub-phases 1A, 1G, 5B, 6B,
  6E, 8A and 8B with the new requirements; section 10 now names
  `MAX_UPLOAD_MB` as the size limit; recorded the Wave 3 timing in
  `docs/SKILLS.md`.
- Why: turn the installed engineering skills into a written, checkable workflow
  and quality bar, and make the security non-functional requirements testable.
- Files: `CONSTRAINTS.md`, `CLAUDE.md`, `docs/SPECS.md`, `PROJECT_PLAN.md`,
  `docs/SKILLS.md`, `README.md`.
- Unchanged on purpose: `docs/CONTRACTS.md` and `contracts/` (no schema_version
  bump), `docs/AI_PIPELINE.md`, phase order, and the "what to cut first" list.
