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
- Stage 2 Analyze: KPIs, RFM segments, product Pareto, the revenue identity and the
  lines outside revenue (stock figures are not supported in v1)
- Stage 3 Diagnose: an 8-step diagnostic engine (data-trust gate, calendar
  adjustment, signal-vs-noise, Shapley metric tree, localization, a fixed
  hypothesis catalog with verdicts) whose conclusions the AI only narrates
- Stage 4 Predict: interpretable forecast + code-written suggested actions
  (no AI writes a recommendation in v1: the report redesign's step 4)
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

How the steps move through it (stage 1 in 1G; stages 2-5 in 2D, 3G-lite, 4C and 5C):

| Call | Allowed from | Moves the run to |
|---|---|---|
| `POST /analyze-schema` | `uploaded`, `profiled` | `profiled` (profiling happens here when the run is `uploaded`; the run stays `profiled` whatever the AI does; an answer already given is final, INVALID_STATE; a call that got no answer may be repeated, up to 3 attempts a step, then RATE_LIMITED) |
| `POST /plan` | `profiled`, and `schema_inference.json` must exist | `planned`; stays `profiled` when the AI is unavailable |
| `POST /preview` | `profiled`, `planned` | no change |
| `POST /line-summary` | `profiled`, `planned` | no change |
| `POST /currency` | `profiled`, `planned` | no change |
| `POST /execute` | `profiled`, `planned` | `cleaning` while it runs, then `cleaned` |
| `POST /analyze` | `cleaned`, `analyzed` | `analyzed` |
| `POST /diagnose` | `analyzed` | stays `analyzed` (3G-lite: stages 2-4 all live in it; which of their files exist says how far the run went - a stage run again removes the later stages' outputs) |
| `POST /predict` | `analyzed`, and `diagnosis.json` must exist | stays `analyzed` (4C); the AI, when its step is on, is asked at most 3 times a run and an answer already accepted is final - a fourth predict still writes the forecast |
| `POST /report` | `analyzed`, and `diagnosis.json` and `forecast.json` must exist | stays `analyzed` (5C); report.json and report.html written together |

`cleaning` is not a step the user sees: it is the claim a run holds while its plan
executes, taken by one atomic conditional UPDATE, so a second `execute` (or a
`preview`) for the same run gets INVALID_STATE (409) instead of racing the first.
Preview and execute are allowed from `profiled` on purpose: with the AI
unavailable, or a file that is not inventory data, the run never reaches `planned`
and the user builds the plan by hand (section 10). An invalid plan releases the
claim (the run is as it was); a valid plan that fails on the data moves the run to
`failed` with CLEANING_FAILED; an unexpected error also releases the claim, and so
does running out of memory or disk (`MemoryError` / `OSError` are not a verdict on the
data, so they are not CLEANING_FAILED).

One piece of work runs at a time per run (an AI step or an execution): a second one gets
INVALID_STATE (409, `details.reason: "step_in_progress"`). Review's whole-file summary
(`POST /line-summary`, 2E-t3) has its own rule: one at a time per run
(`details.reason: "summary_in_progress"`), never holding off a preview or an execution. A run left in `cleaning` that
nothing in the server is executing (the process died, or the write of its final status
failed) is freed by the next call that reaches it: `cleaned` when its report exists,
otherwise `planned`. One process only (v1).

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

**Date question (session 2E-j, Thach),** above the order notices: when the
date column's day-month-year cells can be read day first or month first and
the file proves neither (or both), Review asks "How are the dates in "X"
written?" - Day first (31/12/2026) or Month first (12/31/2026) - and Confirm
waits for the answer (stage 1 refuses to run without one: either default
fabricates dates). A proven order is shown with its proof, and the user may
override it ("They are written month first"; Thach, 2E-o Q8) - the cells
only the proven order can hold then have no date and are counted as
undated; a parse step on the date column that reads the other way is shown
with its fix. The answer
applies only to the column it was given for.

**Order notices (session 2E-e2, Thach),** above the column table, following
the mapping as the user edits it (a dropped column is unmapped). None blocks
Confirm. An answer applies only to the columns it was given for: after a
remap the question is asked again.
- **Blank order ids:** "Up to N lines have no order id" (N = blank cells of
  the column mapped to `order_id` on the raw file): while any sale or return
  line has no id the whole file counts lines. Actions: drop these lines
  (`drop_rows_missing` on that column; the notice then says their revenue
  leaves every figure), upload a fixed file, or keep them and count lines.
  Ids are never filled in: one made-up id would merge every blank line into
  one order. Stage 2's exact count is in `metrics.json`.
- **Is the order id a receipt number?** Asked when `order_id` is mapped and
  the order-id check could read dates only - most receipts name no customer,
  one customer is on most, or fewer than two are named (stage 1's
  per-receipt measure, `order_id_date_only`; approximated from the profile
  after a remap or once a placeholder is confirmed): a daily batch or
  Z-report code passes that check. Yes / No, it is a batch code; an answer
  can be changed. Unanswered counts as No: orders are counted as lines.
- **Is "Guest" a placeholder for walk-ins?** (2E-k) Asked for each candidate
  stage 1 found (a placeholder word - "Guest", "Walk-ins", "GUEST01",
  "Khach le", "Retail_Customer", "Misc", "Consumidor Final", "n/a" and the
  like, any share - or 10% or more of the lines or of the sale revenue, or the
  largest of the remaining values at 4 times the next one, taken again after
  each; read from the profile's top values after a remap, lines only). Shares are floored to one decimal. Yes:
  those lines have no customer. No: a real customer. An answer can be
  changed and applies to the customer column it was given for.
- **Lines that may not be products** (2E-d2, Thach). One notice lists each
  product key stage 1 found whose SKU or commonest name begins or ends with a
  class word ("POSTAGE", "AMAZON FEE", "Adjust bad debt", "Discount",
  "SAMPLES"; read from the profile's top values after a remap), with its
  lines, its positive and negative money and a suggestion, and a choice per
  key: not answered, a product, a charge paid by the customer (stays in
  revenue, no order), a discount (stays in revenue), many items under one
  code (sold, not ranked as a product; 2E-l), a fee or cost (leaves revenue),
  an accounting adjustment (leaves revenue), a gift card sold (owed until
  redeemed: leaves revenue; 2E-t1, suggested for "gift card", "gift voucher",
  "gift certificate" and codes like `gift_0001_10`). Nothing is chosen for the user;
  unanswered, the lines stay products - except a line with no SKU whose name
  is sold under exactly one classed SKU: it takes that SKU's class unless its
  name is answered, "a product" included (2E-l). Every class leaves the
  product tables.
- **The whole file, as your answers stand** (2E-t3; docs/LINE_TAXONOMY.md
  section 5). Below the line-class question, one notice gives the revenue
  identity of the whole file - gross sales - returns - discounts - other
  deductions (unconfirmed) + other revenue = net revenue - for the plan and
  the answers as they stand, and the lines the plan keeps; below it, the
  returns on codes nobody confirmed and the undated lines when there are
  some, what is outside revenue (fees and costs, adjustments, gift cards,
  stock received by the sign of its amount), the lines that cannot be
  measured by reason (their money unknown), the lines no rule placed, and
  the notes with their measures. Stage 1 computes it on the lines execute
  would write, with the functions metrics.json's blocks come from
  (`POST /line-summary`): once when Review opens, then when the user asks
  again - never on every edit, as the whole file takes seconds and a
  started computation cannot be stopped (2E-t3 review 1 #1). After an edit
  the figures shown are marked "before your latest changes", with "Add up
  again"; an error offers "Try again". Until the plan maps and keeps a
  date, a quantity and a unit price, while the date question is open, or
  when the file's amounts are too large to add up, it says so instead. Not
  asked for a file that is not inventory data.
- **Columns the cleaned file writes under another name** (Q24): a source
  column named `line_class`, `class_source` or `suggested_class` and kept by
  the plan is written as `<name>_source` (numbered while taken), and Review
  says so before the run, with what cleaned.csv's own column holds.
- **Is the customer written on a receipt's first line only?** Asked when the
  customer fill would happen (`receipt_fill_lines` above 0), or without a
  count when that was not measured for the current columns (stage 1 could not
  tell, a remap, the blank-id lines dropped, no schema); never when the plan
  imputes the customer column (nothing is left to fill). Yes, or no answer: a
  receipt's unnamed lines are its named customer's (2E-f). No: they stay
  without a customer.
- With a column mapped to `transaction_type`, the blank-id notice also says
  that dropping the blank-id lines drops stock-in lines with no id, which
  leave the report of stock received (v1 has no stock figure - 2E-t2).
- An answered notice never promises what stage 2 will not do: a receipt
  number whose ids stage 1 found spanning days, or blank ids kept, still
  count lines, and a fill waits for every line to have an id. A plan that
  fills the blank customers in is told that the column can then pass as a
  receipt number unless the user answers No. A No to the receipt question
  stays (and shows) while that column is the order id. No fill question is
  asked when the plan imputes the customer column or drops the rows with no
  customer.
The answers travel in the plan's `confirmations` (docs/CONTRACTS.md section 4).

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
zero velocity. **Out of v1** (Thach, 2026-09-28, the line taxonomy's scope cut):
v1 analyses sales, not inventory - no low-stock count, inventory value or
low-stock table; the stock ledger is a v2 item (PROJECT_PLAN's Backlog).

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
- Duplicates: exact-row duplicates kept - a copy cannot be told from a genuine
  repeat sale, so the AI never proposes removing them; the user may add the
  removal in Review, which shows the lines and revenue it takes (Thach,
  2026-10-02, 2E-u4); business-key duplicates flagged only
- Category standardization: trim + case normalization, then merge near-identical
  labels with the mapping shown to the user
- Outliers: IQR flagging by default; clipping is opt-in

## 7. Analysis Requirements (stages 2-4)

- 7.1 Every KPI is computed in pandas and covered by a test with a hand-checked
  expected value. No KPI is ever produced by the AI.
- 7.2 Revenue attribution uses the **Shapley value**, never sequential
  substitution, over `revenue = customers x frequency x AOV` and every other
  multiplicative decomposition in stage 3. Contributions must sum to the total
  change exactly (relative tolerance 1e-9, asserted in tests). Sequential
  substitution is banned because its answer depends on the order a developer
  picked: `docs/adr/0004-shapley-attribution.md`. Full engine:
  `docs/AI_PIPELINE.md` section 7.
- 7.2a Stage 3 tests a **fixed hypothesis catalog**, written before any run and
  identical for every run; every hypothesis is reported including the ones
  ruled out, and the AI may not choose, add, remove or re-rank them
  (`docs/adr/0005-pre-registered-hypothesis-catalog.md`). Causes the schema
  cannot reach are listed as not testable rather than omitted.
- 7.3 RFM scoring uses quintiles on the run's own data; the reference date is
  max(transaction_date) + 1 day unless configured otherwise. A customer with
  exactly one order scores F = 1 whatever the ranks say (Thach, 2E-f): one
  purchase is a fact, not a rank.
- 7.4 Forecasting is interpretable: weighted moving average plus a monthly
  seasonality index, with confidence bands. If history is shorter than 3 periods,
  return `insufficient_history: true` and skip the forecast rather than
  extrapolate from noise.
- 7.4a As built (4A): revenue only; the history is the contiguous complete
  months holding revenue, ending at the compared month; 3 months ahead; an
  80% band from the method's own errors h months ahead (out of sample for a
  season), which held the true month 76-98% of the time at every horizon
  on flat, trending and seasonal swept series of 12 months or more (a jump
  after the history is unforeseeable), 54-67% on a trend of 3-4 months;
  CONTRACTS section 8 has the details. 7.5's "gap between the highest and
  lowest period exceeds 40%" is read as (strongest calendar month's index -
  weakest) / strongest, the most cautious of its readings - confirmed by
  Thach, 2026-10-01 - measured against the business's own trend; and a
  season must repeat from year to year and must not be a steady ramp
  through the year, the shape a step between two years leaves (the
  standing rule: the data cannot tell them apart, so none is claimed, and
  the forecast says why). A season claimed from exactly two years carries a
  note that it rests on the fewest years a season can be read from (Thach,
  2026-10-01, 4A option (b): the step/season split is not certain at two
  cycles - Hyndman & Kostenko 2007). The method's known limits (a noisy step, a step
  on top of a season, one big month at a mild season's peak) are
  PROJECT_PLAN 8D's.
- 7.5 Seasonality is only claimed when the gap between the highest and lowest
  period exceeds 40% AND at least two cycles of data exist.
- 7.6 Every recommendation must name the metric to watch and the review window.
  As built (4B): the window is checked by code (`how_to_measure` carries a
  `{window:...}` token, at most a year, rendered by code); the metric is
  asked by the prompt and not checked - read by the manual review of real
  answers (Phase 4's DoD).

## 8. API Contracts

- `GET /api/limits` -> `{max_upload_mb}`: the server's own `MAX_UPLOAD_MB`,
  which the Upload page checks before uploading (PROJECT_PLAN 6A: one source
  of truth for a number that can differ per deployment). Until it answers, or
  if it fails, the page names no limit and checks only section 1's 50 MB
  ceiling, which no server exceeds, saying so if it refuses a file - never
  showing the ceiling as the server's limit; the server still enforces its
  own (SEC-1)
- `POST /api/runs` (multipart) -> 201 `{run_id, filename, size_bytes, status}`
- `GET /api/runs/{id}` -> status + which contract files exist
- `GET /api/runs/{id}/profile` -> `profile.json`
- `POST /api/runs/{id}/analyze-schema` -> `schema_inference.json`
- `POST /api/runs/{id}/plan` -> `plan_proposed.json`
- `POST /api/runs/{id}/preview` (body: final plan) -> before/after sample +
  column deltas (sample execution, max 500 rows)
- `POST /api/runs/{id}/line-summary` (body: final plan, answers included) ->
  Review's whole-file view of the line taxonomy (2E-t3): nothing written
- `POST /api/runs/{id}/currency` (body: the plan as edited) -> Review's
  currency question (the report redesign's step 5, design 6.2 and 6.3):
  nothing written
- `POST /api/runs/{id}/execute` (body: final plan) -> `cleaning_report.json` +
  download urls

As built in 1G (200 responses; the run id is always in the URL and repeated in the body):
- `analyze-schema` -> `{run_id, status: "profiled", schema_inference | null, notices}`
- `plan` -> `{run_id, status: "profiled" | "planned", plan | null, notices}`
- `preview` -> `{run_id, preview: {rows_in_file, sample_rows, sampled, rows_after,
  columns_after, rows, deltas}}`
- `currency` -> `{run_id, question}`; `question` is `contracts/currency.py`'s
  `CurrencyQuestion` - `{finding, options, selected, blocked, unreadable,
  hint}`: stage 1's finding on the raw file on the plan's unit-price
  columns (the reading execute applies), the ISO codes in Review's order
  (a narrowed family first, else GBP, EUR, USD, AUD, CAD, NZD, JPY, CNY,
  CHF, INR, SGD, HKD, then the rest alphabetically), the pre-selection (a
  found code, else `not_stated`; null when blocked), and stage 1's own
  sentences: `blocked` (more than one currency - the sentence execute
  refuses with), `unreadable`, `hint`
- `line-summary` -> `{run_id, reserved_renames: [{source, written_as, holds}], summary
  | null, summary_unavailable_reason}`; `summary` is `contracts/lines.py`'s
  `LineSummary` - `{lines, undated_lines, identity, outside_revenue,
  unclassified, unmeasurable, notes}`, every scope `file` - and null, with the
  reason, until the plan maps and keeps a date, a quantity and a unit
  price, while the date question is open, or when a whole-file figure's
  amounts are too large to add up (metrics.json refuses such a figure too,
  and adds up the compared months apart - either can overflow where the
  other does not). The plan is checked first, as the preview checks it:
  INVALID_PLAN, CLEANING_FAILED (422), EXPIRED (410); one summary at a time
  per run, a second while one runs INVALID_STATE (409, `details.reason`
  `summary_in_progress`) - it never holds off a preview or an execution.
- `execute` -> `{run_id, status: "cleaned", report, notices}`
- `notices` holds the section 10 cases that are a 200 with a flag, each as
  `{code, message, details?}` like an error: `AI_UNAVAILABLE` (`details.reason`
  is the AI client's reason code), `NOT_INVENTORY` (`details.domain_confidence`,
  `details.domain_reasoning`). Stage 4 asks no AI in v1, so it raises no
  notice (`AI_NOT_ASKED` was its code while it had an AI step).
  `schema_inference` / `plan` are `null` exactly when
  the AI produced no accepted answer.
- The body of `preview` and `execute` is the plan as `plan_proposed.json` has it,
  as the user edited it. It is validated as a contract by the backend, so an action
  outside the catalog is INVALID_PLAN, not INVALID_REQUEST. The backend sets the
  plan's `source` itself: `ai` when the plan equals the proposal, `user_edited`
  when it differs, `manual` when there is no proposal.
- The download urls of `execute` are not part of 1G (no download endpoint exists
  yet); the report is in the response.
- A run's `raw.csv`, parsed, is kept in memory between previews, bounded in bytes
  (`PREVIEW_CACHE_MAX_MB`, measured on the frame, not estimated from its cell count) and
  by idle time (`PREVIEW_CACHE_TTL_SECONDS`); it is dropped when the run is executed or
  fails. The run's one shared AI retry, its AI attempt counts and the work in progress
  are kept in memory too. All of it is per process and lost on restart; see
  `backend/app/services/run_memory.py`.
- `POST /api/runs/{id}/analyze` -> `metrics.json`
  - As built in 2D (200): `{run_id, status: "analyzed", metrics, notices}`.
    `notices` is always `[]`: stage 2 has no AI and no degraded path
    (`docs/adr/0002`), so a run it cannot compute metrics for is
    ANALYSIS_FAILED (section 10), never a 200 with a flag. Allowed from
    `cleaned` or `analyzed` (a re-run overwrites metrics.json and removes
    the later stages' outputs, before writing - `docs/CONTRACTS.md` section
    1, 3G-lite); out of order is INVALID_STATE. No
    transient claim status the way `execute`'s `cleaning` is: the
    computation is pure and deterministic (no AI, docs/adr/0002) and
    metrics.json is written atomically, so a concurrent second call for the
    same run is simply refused (`RunWork.execution`, the same
    "one piece of work at a time per run" guard 1G built) rather than
    raced or claimed - there is no partial-write state a crash could leave
    the run stuck in.
- `POST /api/runs/{id}/diagnose` -> `diagnosis.json`
  - As built in 3G-lite (200): `{run_id, status: "analyzed", diagnosis,
    notices}`. Steps 1-7 only, in the designed degraded mode: no AI call,
    `ai_findings` and `model_used` null, the code-written headline and
    verdicts stand (`docs/AI_PIPELINE.md` sections 7.9 and 9); `notices` is
    `[]` (3F adds AI_UNAVAILABLE when the narration is tried and fails).
    Allowed from `analyzed` only, which the run keeps; a re-run overwrites
    diagnosis.json, written atomically, and removes the later stages'
    outputs before writing it; one piece of work at a time
    per run (INVALID_STATE, `step_in_progress`). Its files gone: EXPIRED; a
    metrics.json another version wrote: INVALID_STATE "run the analysis
    again"; cleaned.csv's classes changed: ANALYSIS_FAILED ("re-upload");
    amounts stage 3's attribution multiplies past a float (stage 2 could
    add them): ANALYSIS_FAILED (`amounts_too_large`).
    Stage 3 on the full Online Retail II file takes about a minute
    (synchronous, v1).
- `POST /api/runs/{id}/predict` -> `forecast.json`
  - As built in 4C (200): `{run_id, status: "analyzed", forecast, notices}`.
    The computed forecast and the code-written suggested actions
    (forecast.json 2.1: `actions_status` "list" or "suppressed" - the report
    redesign's step 4, Thach's option (d)); stage 4 asks no AI in v1, so
    `model_used`, `recommendations` and `do_not_do` are null and `notices`
    is empty. Allowed from
    `analyzed` once diagnosis.json exists (none: INVALID_STATE "Run the
    diagnosis first", `details.missing`); the run keeps `analyzed`; a re-run
    overwrites forecast.json, written atomically, and removes the report's
    files. A diagnosis of other months than the metrics': INVALID_STATE
    (`details.reason` `diagnosis_mismatch`); its files gone: EXPIRED; a run
    file another version wrote: INVALID_STATE "run that stage again";
    amounts past a float: ANALYSIS_FAILED (`amounts_too_large`). No AI is
    asked (v1). One piece of work at a time per run (INVALID_STATE,
    `step_in_progress`).
- `POST /api/runs/{id}/report` -> `report.json` + html download url
  - As built in 5C (200): `{run_id, status: "analyzed", report, html_url,
    notices}`. Stage 5 writes report.json from the earlier stages' files -
    computing nothing, calling no AI (`notices` is `[]`) - then report.html
    from it: both or neither within the process (around report.json's rename
    the previous pair is set aside and the page rendered; either failing puts
    the previous pair back, or removes a first one half written; a crash
    between them can leave report.json alone - the next report writes both).
    The uploaded file's name comes from the run's
    row; no AI recommendation is shown in v1, whatever forecast.json holds
    (Q42, Q53) - the suggested actions stand in the front's section 4. Allowed from
    `analyzed` once diagnosis.json and forecast.json exist (none:
    INVALID_STATE "Run the diagnosis first" / "Run the prediction first",
    `details.missing`); the run keeps `analyzed`; a re-run of stages 2-4
    removes the report's files. Files describing other months:
    INVALID_STATE (`details.reason` `files_mismatch`); its files gone:
    EXPIRED; a later stage's file another version wrote: INVALID_STATE "run
    that stage again" - a stage 1 file: EXPIRED "upload the file again",
    except stage 1's AI answers (`schema_inference.json`,
    `plan_proposed.json`), which feed only the provenance and are read as
    absent. One piece of work at a time per run (INVALID_STATE,
    `step_in_progress`).
- `GET /api/runs/{id}/download/report.html` (5C) -> the page, as an
  attachment (`report_<name>.html`, the name sanitized as the cleaned file's
  is; `X-Content-Type-Options: nosniff`, on every download). From
  `analyzed` or `imported`; no report yet: INVALID_STATE "Build the report
  first" (`details.missing`). A page is served only beside a report.json
  of this version (4A-b): a report another version of DataClarity built
  (report.json of another major), or a page with no report.json, gets the
  first step that works - what `POST /report` answers for a missing
  earlier file (EXPIRED, or "Run ... first"), else the earliest file the
  report is built from that another version wrote (`another_version`:
  INVALID_STATE "Run the prediction again" for a forecast.json 1.x;
  EXPIRED "Upload the file again" for a stage 1 file), else INVALID_STATE
  "Build the report again"; a report.json or page that cannot be read:
  INVALID_STATE `unreadable` ("Build the report again"). While a step holds
  the run (a report being built again, or an earlier stage run again), any
  of those answers - and a page set aside for the moment - is INVALID_STATE
  `step_in_progress` ("wait"); a current page is served even then. Its
  files gone: EXPIRED (the cleaned file's download too). No work claim:
  downloads never hold each other off. report.json needs no
  download: the report's response carries it (as `execute`'s carries the
  cleaning report).
- `POST /api/runs/{id}/import` -> `{products_created, products_updated,
  transactions_inserted, skipped:[{row, reason}]}`
- `GET /api/dashboard/summary` | `/trend?product_id=&days=30` | `/low-stock`
- Errors always `{error:{code, message, details?}}` with codes from section 10

## 9. Canonical Schema and Database

Canonical fields: `product_name` (required), `sku`, `category`,
`transaction_date` (required), `quantity` (required), `unit_price`,
`transaction_type` (in|out, default out; a line typed "in" is stock received,
outside revenue whatever its sign - the line taxonomy's Q25; any other value is
read by the line's signs), `supplier`, `customer`, `note`,
`order_id` (optional, 2E-e: the id shared by every line of one order,
invoice, receipt or transaction - when mapped, orders are order ids, not
lines), `ignore`.

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
| AI invalid twice / API down | degraded mode: profiling + manual plan building still work; stage 3 still writes its computed blocks with the AI blocks `null` (`docs/CONTRACTS.md` section 7) | AI_UNAVAILABLE (200 + flag) |
| Stage 4 | asks no AI in v1 (the report redesign's step 4): the forecast and the code-written suggested actions are written; no notice | - |
| Stage called out of order | rejected | INVALID_STATE (409) |
| Run id that names no run (unknown, or not a UUID) | rejected | NOT_FOUND (404) |
| Malformed request (no `file` part, a body that is not a JSON object, a wrong type) | rejected; the message lists where, never the value sent | INVALID_REQUEST (400) |
| Unexpected server error (a database that is down, a bug) | generic message, nothing of the exception; logged on the server | INTERNAL_ERROR (500) |
| Plan contains an unknown or illegal action, or is not a valid plan document | whole plan rejected; `details.problems` lists every reason; a refusal about how the dates or numbers read (an unanswered date or number question, an answer the file's cells disprove, a parse step that would write dates wrong) adds `details.reason` `reading` - its problems say what to do in Review, and the UI shows them, no other INVALID_PLAN's (6D) | INVALID_PLAN (422) |
| Plan (at execute) leaves `product_name`, `transaction_date` or `quantity` unmapped, or drops it | whole plan rejected; the preview allows it while the user is still mapping | INVALID_PLAN (422) |
| A valid plan fails on this data (an action raises, or no row is left) | run `failed`, nothing written; the message names the action and the column | CLEANING_FAILED (422) |
| Stage 2 cannot compute metrics for this data (a required canonical field, `unit_price`, was never mapped; or the file was flagged NOT_INVENTORY at schema inference) (2D); or cleaned.csv's line classes are not stage 1's - a value outside a closed list, or some of the three columns without the others (2E-t2); or a figure's amounts or quantities - any month's - are too large to add up (2E-t3, 2E-v); or stage 3 cannot diagnose this data: its classes changed after the analysis, or its attribution multiplies the amounts past a float (3G-lite); or stage 4's forecast carries the amounts past a float (4C) | run stays as it was - `cleaned.csv` is still valid and downloadable (and, at stage 3, metrics.json), only the later stages are unavailable, nothing is written or removed; the message names the missing field, the domain reasoning, or the class column and says to re-upload; or says the amounts are too large to add up (`details.reason` `amounts_too_large`: the file's own amounts, so re-uploading it would not help) | ANALYSIS_FAILED (422) |
| Fewer than 3 periods of history at stage 4 | `insufficient_history: true`, no forecast | success + flag |
| Rate limit exceeded, or the AI already asked 3 times for one step of a run (1G) | rejected | RATE_LIMITED (429) |
| Run expired by retention, or its files are gone, or a stage 1 file of it was written by another version of the app (an older or newer contract major - 2E-v; any endpoint) | rejected with re-upload hint; the last case names the file when one model reads one file (`details.reason` `another_version`, `details.file`) | EXPIRED (410) |
| A later stage's output (metrics.json, diagnosis.json, forecast.json, report.json) was written by another version of the app (2E-v; any endpoint) | rejected; the message says to run that stage again (`details.reason` `another_version`, `details.file`) | INVALID_STATE (409) |

## 11. Non-Functional Requirements

- Performance: profiling and preview under 3 s for a 50MB file on the dev
  machine; full stage 1 execution under 30 s; stages 2-5 under 60 s combined.
  Synchronous processing is acceptable at this size
- AI budget: max 4 calls per run plus 1 shared retry (stage 4 asks none in v1); inputs bounded (60 columns,
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
  inserted as HTML. **Text taken from the uploaded file is untrusted the same
  way** (session 5B, the decision PROJECT_PLAN gave it): the file's name,
  column names, product, category and customer values, and every sentence
  that quotes them - a note, a reason, a hypothesis statement or its
  evidence, a trust message - are escaped wherever rendered; `report.html`
  escapes every string it takes from `report.json`, and its charts carry
  only months and numbers, never text from the file or the AI (Plotly draws
  its own markup in labels). Test: a mocked response with a schema violation,
  and one with an off-catalog action, leave no contract file written; a
  mocked response carrying `<script>` in a text field, and a product name or
  file name carrying markup, appear escaped in the rendered output.
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

### 2026-09-22 - The stage 1 endpoints (Phase 1G)
- What: section 3 gains the table of how the four calls move a run and the `cleaning`
  claim; section 8 the response shapes and the `notices` convention; section 10 three
  rows (NOT_FOUND, INVALID_REQUEST, INTERNAL_ERROR) and two reworded ones
  (INVALID_PLAN also covers a body that is not a valid plan; EXPIRED also covers files
  that are gone). `.env.example` gains `PREVIEW_CACHE_MAX_MB` and
  `PREVIEW_CACHE_TTL_SECONDS`, both required like every setting: an existing `.env`
  must get the two lines or the backend will not start.
- Why: 1G wired the endpoints. The new codes close the gap 1A named: FastAPI's own
  422 `{"detail": [...]}` and the plain 500 were outside the section 8 envelope.
- Decided without asking (Thach may veto): profiling runs inside `analyze-schema`;
  `preview` and `execute` are allowed from `profiled` (the hand-built plan path);
  `execute` of a run the AI called NOT_INVENTORY waives the required-field rule
  (`execute_run(require_required_fields=False)`), which is what makes "generic
  cleaning with downloads" possible; a plan body is validated by the service.
- Added after the 1G doubt-review (one cycle, cross-model skipped by Thach): one piece
  of work at a time per run and at most 3 AI attempts a step (a schema already inferred
  is not asked for again); the state of a run is re-checked after an AI step and the
  answer never claims one it no longer has; a run stuck in `cleaning` is freed by the
  next call (see section 3); the frame cache is charged in bytes, read per run, and a
  run evicted during a read is not stored; a run id that is not a canonical UUID is
  NOT_FOUND before the database is asked; RATE_LIMITED gains its first use.

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
