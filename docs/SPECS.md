# CleanStock - Functional Specification (SPECS v2)

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
| File > 50MB | rejected client and server side | FILE_TOO_LARGE (413) |
| Not `.csv` | rejected | UNSUPPORTED_TYPE (400) |
| Empty or header-only | rejected with a clear message | EMPTY_FILE (400) |
| Unparseable / wrong delimiter | sniff delimiter, then reject | PARSE_FAILED (400) |
| Non-UTF8 | latin-1 fallback, warning in the report | success + warning |
| All-null column | flagged; default action drop_column | - |
| Not inventory data (domain_confidence < 0.5) | say so plainly; offer generic cleaning with downloads only; disable mapping-dependent import and stages 2-5 | NOT_INVENTORY (200 + flag) |
| AI invalid twice / API down | degraded mode: profiling + manual plan building still work | AI_UNAVAILABLE (200 + flag) |
| Stage called out of order | rejected | INVALID_STATE (409) |
| Plan contains an unknown or illegal action | whole plan rejected | INVALID_PLAN (422) |
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
  server-generated UUIDs, never user-supplied paths
- Accessibility: keyboard-navigable review table; color is never the only signal

## 12. Design

All screens have hi-fi Figma frames (Thach, Figma Pro).
`docs/FIGMA_DESIGN_NOTES.md` records the file link, node id per screen, design
tokens and component patterns. Frontend sessions must open the referenced frame
before building; never invent layout or tokens.
