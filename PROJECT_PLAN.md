# DataClarity - Project Plan (v2)

> Official roadmap. Used by both Thach and Claude Code. At the start of EVERY new
> session, re-read section 12 "Current Status" before doing anything. Functional
> detail lives in `docs/SPECS.md`, stage contracts in `docs/CONTRACTS.md`, AI
> internals in `docs/AI_PIPELINE.md`. This plan indexes phases and tasks only.

## 1. What this project is

**DataClarity** is a web application that turns a messy inventory/sales CSV into a
decision-ready report, through a 5-stage pipeline:

| Stage | Name | Question it answers | Package |
|---|---|---|---|
| 1 | Collect | What data do we actually have, and is it trustworthy? | `stages/ingest/` |
| 2 | Analyze | What is happening in this business? | `stages/analyze/` |
| 3 | Diagnose | Why is it happening? | `stages/diagnose/` |
| 4 | Predict | What happens next, and what should we do? | `stages/predict/` |
| 5 | Report | How do we present this so a human can decide? | `stages/report/` |

Stage 1 is the interactive part: the user uploads a CSV, AI infers the schema and
proposes a cleaning plan, the user reviews and edits it in the UI with before/after
preview, then approves. Stages 2-5 then run on the approved clean data.

**Secondary goal (equally important):** portfolio/CV project supporting an ICT
Business Analyst profile for a 190 visa application. Requires clean code, tests,
a professional README, a deployed demo link, and AI integration defensible in an
interview (not a thin wrapper).

**What to cut first if time runs short:** dashboard polish and stage 4 forecasting
sophistication. Never cut: the review-and-approve flow (stage 1) or the root-cause
logic (stage 3). Those are the differentiators.

## 2. Architecture decision: one repo, five independent packages

Each stage is a **self-contained Python package** that:
- reads its input only from the previous stage's **contract file** (JSON on disk,
  schema in `docs/CONTRACTS.md`, validated by Pydantic models in `contracts/`)
- writes its output as the next contract file
- can be run standalone from the CLI: `python -m stages.diagnose --run <run_id>`
- **must never import from another stage package**

This boundary is enforced by an automated test (`tests/test_architecture.py`)
that parses imports with `ast` and fails the build on any cross-stage import.
Full rationale, the alternative considered (five separate repos) and the
trade-offs accepted: `docs/adr/0001-stage-isolation-single-repo.md`.

```
[React frontend] --HTTP--> [FastAPI backend] --calls--> [stages/*]
                                  |                          |
                                  v                          v
                            [PostgreSQL]          [runs/<run_id>/*.json contracts]
```

## 3. Tech Stack

| Layer | Technology | Rationale |
|---|---|---|
| Backend API | Python 3.11+, FastAPI | One language for API and analysis |
| Data processing | pandas | 50MB / few hundred thousand rows ceiling; no Spark needed |
| Forecasting | statsmodels (or pure pandas rolling stats) | Interpretable; no heavy ML dependency |
| AI runtime | Anthropic API: `claude-sonnet-5` (inference, diagnosis, strategy), `claude-haiku-4-5` (cheap bulk tasks) | Sonnet where reasoning matters, Haiku where volume matters. Never Opus at runtime (cost) |
| Database | PostgreSQL + SQLAlchemy + Alembic | Migrations from day one (lesson learned) |
| Frontend | React + Vite + TypeScript | TS required, no plain JS |
| Charts | Recharts | Same as previous project |
| Design | Figma Pro (Thach) | Node ids recorded in `docs/FIGMA_DESIGN_NOTES.md` |
| Deploy | Render (API + DB), Vercel (frontend) | Free tier sufficient |
| Tests | pytest, Vitest | AI always mocked in tests |

## 4. Folder Structure (target)

```
dataclarity/
├── CLAUDE.md  PROJECT_PLAN.md  CONSTRAINTS.md  KICKOFF_PROMPT.md  README.md
├── docs/           SPECS.md  CONTRACTS.md  AI_PIPELINE.md  FIGMA_DESIGN_NOTES.md
├── prompts/        schema_inference.md  cleaning_plan.md  root_cause.md  strategy.md
├── contracts/      # Pydantic models shared by all stages - the ONLY shared import
│   ├── profile.py  cleaning.py  metrics.py  diagnosis.py  forecast.py  report.py
├── stages/
│   ├── ingest/     # stage 1: profiling, AI schema inference, cleaning engine
│   ├── analyze/    # stage 2: KPI + RFM + Pareto computation
│   ├── diagnose/   # stage 3: decomposition + AI root cause
│   ├── predict/    # stage 4: forecast + AI strategy
│   └── report/     # stage 5: HTML report assembly
├── backend/app/    # FastAPI: routers/, services/ (orchestration only), models/
├── frontend/src/   # api/  pages/  components/  types/
├── runs/           # per-run contract files + outputs (gitignored)
└── tests/          # unit tests per stage + test_architecture.py + e2e
```

## 5. Phases (small on purpose - one sub-phase = one Claude Code session)

> Hard rule: one sub-phase per session. Finishing early is fine; starting the next
> one is not, unless Thach explicitly says so.

### Phase 0 - Foundations
- [x] 0A Repo init, folder skeleton, backend FastAPI app factory, `/health`,
      config via pydantic-settings + `.env.example`, pytest wired, 1 passing test
- [x] 0B `contracts/` package: Pydantic models for all 6 contract modules per
      `docs/CONTRACTS.md` (8 models for the 9 JSON files), with validation
      tests
- [x] 0C `tests/test_architecture.py`: AST-based test failing on cross-stage
      imports, and on any import of `app` or `backend` from `stages/` or
      `shared/` (backs SPECS SEC-4); also stages -> web/DB frameworks,
      shared -> stages, and contracts -> anything internal or a framework
- [x] 0C2 Run registry helper (`shared/run_registry.py`: `runs/<run_id>/`
      creation, path resolution); `Settings.runs_dir` anchored to the repo
      root
- [x] 0D Frontend skeleton: Vite + React + TS, `/health` call, CORS via env var
- **DoD:** both apps run; architecture test passes; contracts importable
  (met 2026-09-19: "Backend: ok" confirmed by Thach in the browser)

### Phase 1 - Stage 1 Collect (backend)
- [x] 1A Upload endpoint `POST /api/runs` (multipart, `MAX_UPLOAD_MB` cap and
      type validation per SPECS section 11 SEC-1, including the 50MB ceiling
      check at startup), file stored under `runs/<run_id>/raw.csv`. A binary
      file renamed to `.csv` is rejected by a NUL-byte check on the first
      8 KB (PARSE_FAILED); 0-byte and whitespace-only files are EMPTY_FILE.
      The `runs` DB row moved to 1A2 (Thach's decision)
- [x] 1A2 Database setup and the `runs` row: SQLAlchemy engine/session,
      Alembic init, the `runs` migration per SPECS section 9 (pulled forward
      from 7A), `POST /api/runs` writes the row (`status=uploaded`,
      `expires_at` from `RETENTION_HOURS`), and a DB/filesystem consistency
      test. Tests use SQLite (Thach's decision; the migration also runs
      against SQLite in a test); PostgreSQL only for dev/deploy, verified by
      hand. Needs PostgreSQL installed locally. Decide the write order, so a
      failed DB insert cannot leave an orphan `raw.csv` (or the reverse)
- [x] 1B `stages/ingest/profiling.py`: pure pandas per-column + dataset stats ->
      `profile.json` contract. Unit tests with fixture CSVs. Rejects a
      header-only file with EMPTY_FILE (SPECS section 10; 1A only rejects
      0-byte and whitespace-only files, without parsing). No stage CLI was
      added in 1B; the runs-root question moved to 5D
- [x] 1C `shared/ai_client.py` (`docs/AI_PIPELINE.md` section 3) with the
      real-API guard fixture that activates CONSTRAINTS F4, then
      `stages/ingest/ai_input.py` + `ai_schema.py`: AI stage A (schema
      inference) via the AI client, validated, retry-once, degraded mode.
      Checks that every profiled column appears exactly once (CONTRACTS
      section 3). `AIUnavailable` carries a reason code and the client logs
      it; the reason is not written to a contract file (Thach's decision:
      stage 1 degraded writes no file at all)
- [x] 1D `stages/ingest/transforms.py`: the full transform catalog
      (`docs/AI_PIPELINE.md` section 6) as pure functions + change log. One test
      per transform including edge cases. Also count, in pandas, the issue
      codes the profile holds no figure for (negative_values, zero_values,
      trailing_whitespace, invalid_dates, outliers_iqr, ...), so
      `ai_schema.py` can replace the AI's estimate with the computed count
      (1C checks only missing_values, duplicate_rows and all_null_column), and
      consider sample-row kinds 1C does not pick yet (text in a mostly numeric
      column, whitespace, bad dates)
- [x] 1E `stages/ingest/ai_plan.py`: AI stage B (cleaning plan) + catalog/legality
      validation. Tests with mocked AI. Also wired the pandas issue counts into
      `ai_schema.py` (`issue_recount.py`) and defined the business key, as the
      1D handover asked. The checks are in `plan_checks.py` and the param rules
      in `transform_params.py` (docs/AI_PIPELINE.md section 11)
- [x] 1F `stages/ingest/cleaning.py`: preview (sample) and execute (full) engines
      -> `cleaned.csv` + `cleaning_report.json` (+ `plan_final.json`, which nothing
      owned). Delivered: `cleaning.py` (`apply_plan`, the one place a plan runs, and
      `execute_run`), `preview.py` (`preview_run` / `preview_frame`, the sample and the
      20 rows shown), `plan_validation.py` (the plan the user submits, checked again),
      `transform_types.py` (the `transforms.py` split, 322 -> 281 lines),
      `problem_rows.py`, `contract_files.write_files_atomically` (with rollback), the
      `encoding_fallback` warning. Resolved from 1E: mixed UTC offsets keep the date as
      written; `drop_rows_missing` runs before the imputations; execute rejects a plan
      that drops a required field. Still open, in AI_PIPELINE section 12 "Known limits":
      one action per column (kept by decision until the review screen, 6B, shows what
      is needed), a plan cannot require `transaction_date` to be parsed
- [x] 1G Endpoints wiring: `/analyze-schema`, `/plan`, `/preview`, `/execute` per
      `docs/SPECS.md` section 8 (now updated with the built response shapes and the
      state table). Delivered: `app/schemas.py` (response models, `Notice`), `app/errors.py`
      (the envelope now also covers FastAPI's own 422/404/405 and an unexpected exception,
      via `RequestValidationError`/`StarletteHTTPException` handlers and an in-CORS
      middleware for `Exception`, so a 500 still carries CORS headers),
      `app/services/run_state.py` (the state machine: `load_run`/`load_live_run`,
      `require_status`, `advance`/`fail`, `claim_for_cleaning` with a compare-and-swap
      retry loop, `release`, `recover_claim`), `app/services/run_memory.py` (`FrameCache`
      bounded by measured bytes and idle time, one read lock per run so a slow parse of
      one run never blocks another; `RetryBudgets`, one `RetryBudget` per run shared by
      the schema and plan steps; `RunWork`, one piece of work at a time per run and a
      3-attempt cap per AI step, RATE_LIMITED past that), `app/services/analysis.py`
      (`analyze_schema`, `propose_plan`), `app/services/plan_execution.py`
      (`preview_plan`, `execute_plan`), `app/services/stage_errors.py` (every stage
      exception -> its SPECS section 10 code). A new `cleaning` run status (Alembic
      migration `5c1e7b3d9a42`) is the claim `execute` holds; a run left in it by a dead
      process or a lost status write is freed by the next call that reaches it
      (`load_live_run`), `cleaned` if its report exists, else `planned` - never a
      background sweep, since v1 runs one process. `execute_run` gained
      `require_required_fields=False` for a NOT_INVENTORY run (generic cleaning has
      nothing to map). Doubt-driven review (one cycle, fresh reviewer, cross-model
      declined by Thach) found 5 high-severity issues before anything was reviewed a
      second time: a missing prompt file leaking a server path as a false INVALID_STATE;
      a run strandable in `cleaning` forever; the AI callable an unbounded number of
      times per run (and a race where a slow request's answer could overwrite a
      concurrent one's, or claim a status the run no longer has); and one slow preview
      able to block every other request behind a single global parse lock. All fixed,
      each with a reproducing test, then verified by mutation testing (every mutant of
      the fix killed). `test_config.py`/`.env.example` gain `PREVIEW_CACHE_MAX_MB` and
      `PREVIEW_CACHE_TTL_SECONDS`, both required like every other setting: an existing
      `.env` needs the two lines added or the backend will not start
- **DoD:** full stage 1 works end-to-end via API only (no UI), verified on a
  deliberately messy fixture CSV (met 2026-09-22: upload -> analyze-schema -> plan ->
  preview -> execute driven through the API with the AI mocked, state transitions and
  409s on out-of-order calls asserted; concurrent-execute and concurrent-AI-step races
  driven with real threads and a real SQLite file so the claim is proven, not assumed)

### Phase 2 - Stage 2 Analyze
- [x] Install skills Wave 2 (see docs/SKILLS.md)
- [x] Create `docs/adr/` (own docs session, after the Wave 2 install, using
      documentation-and-adrs) with: ADR-0001 one repo with five independent
      stage packages; ADR-0002 pandas computes, AI only interprets; ADR-0003
      model choice per task (reasoning model vs bulk model via `MODEL_REASONING`
      / `MODEL_BULK`, never the largest model at runtime; no model ids in the
      ADR). ADRs hold the "why"; existing docs keep the rule and link to the ADR
- [x] 2A `metrics_core.py`: revenue by period, MoM growth, orders, active
      customers, AOV, return rate. Tests with hand-calculated expected values.
      Zero denominators (`revenue_change_pct` with no previous revenue, `aov`
      and return rate with no orders) need a contract decision first: the 1.0
      contract requires a number there
- [x] 2B `metrics_customers.py`: RFM scoring + segment assignment (Champions,
      Loyal, At-risk, Hibernating, New). Tests
- [x] 2C `metrics_products.py`: Pareto concentration, top/bottom movers,
      velocity + stockout projection. Tests. `days_to_stockout` at zero
      velocity needs a contract decision first (same reason as 2A)
- [x] 2D Assemble `metrics.json` contract + `POST /api/runs/{id}/analyze`. Tests
- **DoD:** numbers in `metrics.json` verified by hand against the fixture data
  (met 2026-09-22: `by_dimension.category`'s contribution_pct formula reproduces
  both worked-example figures in docs/CONTRACTS.md section 6 exactly, UK 57.1%
  and Home Decor 41.4%, computed from core's own revenue_current/previous)

### Phase 3 - Stage 3 Diagnose
- [ ] 3A `decomposition.py`: revenue = customers x frequency x AOV, period-over-
      period attribution, contribution by segment/country/product group. Tests.
      Decide the insufficient-data path (one month of data, zero previous
      customers or orders): CONTRACTS section 7 requires `decomposition`
- [ ] 3B `ai_root_cause.py`: AI reads decomposition output only, returns driver +
      evidence + ruled-out hypotheses, validated. Tests with mocked AI
- [ ] 3C Assemble `diagnosis.json` + `POST /api/runs/{id}/diagnose`. Tests
- **DoD:** for a fixture with a deliberately planted cause (e.g. one segment
  collapsing), the pipeline identifies that cause and rules out two decoys

### Phase 4 - Stage 4 Predict
- [ ] 4A `forecast.py`: interpretable forecast (rolling/weighted trend +
      seasonality index) for revenue and per-product demand, with confidence
      intervals and an explicit "insufficient history" path. Tests
- [ ] 4B `ai_strategy.py`: AI turns metrics + diagnosis + forecast into ranked
      recommendations, each with insight, cause, action, expected impact
      (arithmetic shown), how to measure. Validated. Decide whether stage 4
      calls the AI when `diagnosis.json` has `ai_findings: null`. Tests with
      mocked AI
- [ ] 4C Assemble `forecast.json` + `POST /api/runs/{id}/predict`. Tests
- **DoD:** every recommendation cites a number that exists in the inputs; a
  manual review finds no fabricated figures

### Phase 5 - Stage 5 Report
- [ ] 5A `builder.py`: assemble `report.json` (3 layers: numbers, causes,
      actions) from all prior contracts. Tests. First define the layer
      structure in CONTRACTS section 9 (today `dict[str, Any]`), including
      how a `null` AI block shows as "unavailable" (AI_PIPELINE section 9) and
      where `provenance.ai_calls` is traced from
- [ ] 5B `html_report.py`: self-contained HTML with embedded Plotly charts;
      downloadable. Tests on structure, not pixels, including AI text escaped
      (SPECS SEC-3). Owner of the open decision to extend SEC-3 to text taken
      from the uploaded CSV (column names, product/category values): update
      SPECS first, then 5B and the Phase 6 screens follow it
- [ ] 5C `POST /api/runs/{id}/report` + download endpoints. Tests
- [ ] 5D `python -m stages.report --run <id>` CLI path verified (proves stage
      independence). Decide how a stage CLI gets the runs root without
      importing the backend (SEC-4), e.g. a `--runs-dir` argument (no stage
      has a CLI yet as of 1B)
- **DoD:** the HTML report is readable standalone and matches the contract data

### Phase 6 - Frontend
> Not started. A scoped, deliberate exception pulled 3 of these screens (Upload,
> Review, Results - the Stage 1 screens, whose backend was already built and
> manually verified) forward into their own session, ahead of phase order and
> without the Wave 3 skills. Insights (6E) and Dashboard (6F) still wait for
> Phase 2-5, whose data they need. Full account in section 12 Notes, dated
> 2026-09-22.
- [ ] Install skills Wave 3 (see docs/SKILLS.md)
- [ ] 6A Upload page + analyzing states (SPECS 4.1); decide how the
      client-side size check learns `MAX_UPLOAD_MB` without a second source of
      truth for the limit
- [ ] 6B Review screen part 1: column table with editable type / mapping / action
      (AI rationale rendered escaped, SPECS SEC-3). Issue examples are AI text
      of unknown shape (a real call returned the string "null"): render them
      as given, escaped, without assuming they are row references
- [ ] 6C Review screen part 2: before/after preview + confirm/cancel/reset
- [ ] 6D Results page: cleaning summary + downloads
- [ ] 6E Insights page: KPI cards, diagnosis panel, recommendations list (AI
      text rendered escaped, SPECS SEC-3)
- [ ] 6F Dashboard page: charts + low-stock table + report download
- **DoD:** a non-technical user completes upload -> report without instructions

### Phase 7 - Import and Persistence
- [ ] 7A Alembic migrations for `products`, `transactions` (`runs` is done in
      1A2)
- [ ] 7B Import service: approved clean data -> canonical tables, upsert by
      SKU/name, import summary with skipped rows and reasons. Tests
- [ ] 7C Dashboard endpoints read from DB (not from run files). Tests
- **DoD:** dashboard numbers match the source file, hand-checked

### Phase 8 - Hardening
- [ ] 8A Edge cases from SPECS section 10 (empty, header-only, non-UTF8, wrong
      delimiter, all-null column, non-inventory data, `MAX_UPLOAD_MB` boundary);
      duplicate header names (pandas renames the second `a` to `a.1`, so the
      review screen would show a name that is not in the file); a pathological
      header (e.g. a 1 MB column name), which 1C cannot cut because the AI's
      answer must repeat names exactly; a limit on (or a warning about) the number of
      columns: a file of hundreds of columns makes the preview slow and the AI sees 25
      (left here by Thach at the end of 1F)
- [ ] 8B Abuse guards: rate limits on uploads (SPECS section 11 abuse guards)
      and on every AI endpoint (SEC-2), each from its own required env var;
      a request-body size limit so an oversized upload is refused before it
      is fully received (today 1A returns 413 only after python-multipart has
      spooled the whole body); the retention cleanup also deletes run
      directories that have no `runs` row (left by a commit with an unknown
      outcome, see 1A2);
      the run-state transition for a rate-limited AI step (SEC-2); the
      trusted-proxy setting that yields the client IP (SEC-2; 9A sets the
      Render value); AI call budget per run (1G added a per-run, per-step attempt cap,
      `RunWork`, RATE_LIMITED after 3; SEC-2's IP-based limit is still open); retention
      cleanup job (also frees a run 1G's `load_live_run` never touched, and reads
      `RunWork`/`FrameCache`/`RetryBudgets` for one process only - 8B decides what
      changes if the backend ever runs more than one); startup `ALLOWED_ORIGINS`
      checks per SEC-5; `DATABASE_URL` handled as a secret so it never reaches logs
      (SEC-4)
- [ ] 8C Test sweep + coverage review on `stages/` and `backend/app/services/`
- **DoD:** every hostile input fails gracefully with the specified message

### Phase 9 - Deploy and Documentation
- [ ] Install skills Wave 4 (see docs/SKILLS.md)
- [ ] 9A Deploy API + Postgres to Render; env vars + CORS for the real domain,
      including origins with a trailing slash and Vercel preview domains
- [ ] 9B Deploy frontend to Vercel; production smoke test
- [ ] 9C README: problem, architecture diagram, stage contracts, AI design
      decisions, local setup, demo link, screenshots
- [ ] 9D "What I learned" section for interviews
- **DoD:** public demo link works; README understandable in 2 minutes

### Backlog (never start without explicit approval)
Auth/accounts, XLSX input, multi-file merge, scheduled re-runs, PDF export,
comparing two runs, email delivery of reports, mobile layout.

## 6. Working with Claude Code on This Project

- One sub-phase per session, in order. No skipping, no bundling.
- Read `CLAUDE.md` + section 12 of this file at the start of every session.
- Every function in `stages/` or `backend/app/services/` gets a test the same
  session, not later.
- AI calls are ALWAYS mocked in tests. Never spend real tokens in the test suite.
- Commits: `feat:` / `fix:` / `test:` / `docs:` / `refactor:`
- Feature outside the checklist? Stop and ask Thach.
- Explain decisions to Thach in Vietnamese in chat; all files, code, comments and
  commits stay in English.
- **Mandatory every session:** before ending the turn, edit THIS file with the
  file-editing tool: tick completed items, rewrite section 12 (phase in progress,
  concrete next step, Notes). Overwrite stale notes, don't append forever.

## 7. Model Usage Policy

- Development (Claude Code): Sonnet 5 by default; Opus 5 only for hard debugging
  or architecture decisions.
- Runtime: `claude-sonnet-5` for schema inference, cleaning plan, root cause and
  strategy; `claude-haiku-4-5` for cheap bulk tasks. Model ids from config only.
- Budget: max 4 AI calls per run (1 per AI step) + 1 shared retry.
- Full policy (why two settings, not a hardcoded id; why never the largest
  model at runtime) and the trade-offs accepted:
  `docs/adr/0003-model-selection-policy.md`.

## 12. Current Status

**Phase in progress:** Phase 2 (Stage 2 Analyze) is DONE, closed 2026-09-22
with 2D: `stages/analyze/metrics_dimensions.py` (the `by_dimension` block -
revenue by category, current vs previous period; `country` always reports
`[]`, no canonical field carries country data, Thach's decision) and
`stages/analyze/assemble.py` (calls all four blocks' builders - `period`/
`core` from `metrics_core.py`, `customers` from `metrics_customers.py`,
`products` from `metrics_products.py`, `by_dimension` from this session -
validates the combined result against `contracts/metrics.py` and writes
`metrics.json` to the run directory atomically). `POST /api/runs/{id}/analyze`
wired (`backend/app/services/metrics.py` + `runs.py`): `cleaned` (or an
already-`analyzed` run) -> `analyzed`, no AI call anywhere in this stage
(docs/adr/0002), so no retry budget, no AI client, and no transient claim
status the way `execute`'s `cleaning` is - the computation is pure and
deterministic and metrics.json is written atomically, so a concurrent second
call is simply refused (`RunWork.execution`, reused as-is) rather than raced,
verified with a real `threading`-based test mirroring `test_api_races.py`. A
new error code, `ANALYSIS_FAILED` (422, added to `docs/SPECS.md` section 10
and `backend/app/errors.py`), covers both ways stage 2 cannot compute metrics
(a required canonical field, realistically `unit_price`, never mapped; or the
file was flagged NOT_INVENTORY at schema inference) - unlike CLEANING_FAILED
this does NOT fail the run, since `cleaned.csv` stays valid and downloadable
and only the optional stages 2-5 enrichment is unavailable (decided directly,
not asked, mirroring how a NOT_INVENTORY run already keeps its `cleaned`
status elsewhere; flagged for Thach to veto). `analyzed` needed no migration:
it was already in `RunStatus`, the first `runs` migration's CHECK constraint,
and `get_profile`'s own allowed-statuses list from day one - the session
brief's own recollection that it "wasn't defined" was stale, same class of
mistake as 2B's "SPECS section 5.1" reference. 2A-2C (`metrics_core.py`/
`metrics_customers.py`/`metrics_products.py`) closed earlier, committed as
`d5fceea` (2A+2B) and `4fb0f86` (2C). Before that: Phase 1 backend complete
(1A-1G, closed 2026-09-22). Two scoped-exception sessions ran after 1G, not
Phase 6 (full account in Notes below): the Stage-1-frontend session (Upload,
Review, Results), then a same-day bug-fix + Preview-pane-rebuild session -
both committed and pushed (`4d88e27`, `2694511`, `26bee96`). Earlier: Phase 0
(0A `b790448` ... 0D `24307c3`), 1A (`83eccbf`), 1A2 (`ee5d7c9`), 1B
(`f9b12d7`), 1C (`3d5d9d7`), 1D (`8ed0a19`), 1E (`4c96e92`), 1F (`afaa2a6`),
1G (`8f9c19d`), skills Wave 2 (`69697a9`). pytest 1941 passed (up from 1925:
8 new tests across `test_metrics_dimensions.py`/`test_assemble.py`, 7 more in
`tests/backend/test_api_analyze.py`, one existing test extended -
`tests/backend/test_errors.py`'s hardcoded SPECS-section-10 mirror table
gained the new `ANALYSIS_FAILED` row, which is what a pre-existing test
(`test_every_code_maps_to_its_specs_status`) caught and required, not a
weakening; no test deleted, skipped or had an assertion removed); Vitest not
re-run (no frontend code touched this session). No AI call this session
(Stage 2 makes none, ever). **No doubt-driven review cycle run this session**
(judgment call the brief asked for, explained in this session's Notes entry
below): the new arithmetic (`by_dimension.contribution_pct`) was verified to
reproduce both figures in docs/CONTRACTS.md section 6's own worked example
exactly, and the backend wiring composes already-reviewed primitives
(`run_state`, `RunWork`, `stage_errors`) rather than inventing new ones - the
one genuinely new runtime behavior (concurrent-call refusal) was verified
with a real multi-threaded test, not just read for plausibility.
**Next step:** Phase 3 (Stage 3 Diagnose) - `decomposition.py` (3A):
revenue = customers x frequency x AOV, period-over-period attribution,
contribution by segment/country/product group. Read that checklist line's
own "country" mention against this session's `by_dimension.country` finding
before assuming it means something different there - if Diagnose also wants
country-level attribution, it hits the exact same missing-canonical-field gap.
Phase 6 (Insights, Dashboard) is still not started.
**Action needed from Thach:**
1. Run this session's git commands (see this session's own summary in chat
   for the exact commands; uses a message file, not inline `-m`).
2. Re-verify the rebuilt Preview pane live in the browser (still outstanding
   from before 2A; not touched by any Stage 2 session).
3. `.env`'s `ANTHROPIC_API_KEY`: still not re-checked since the Stage-1-frontend
   session (no upload/browser action has run since) - confirm it is a fake
   key, not the `.env.example` placeholder, before the next browser-driven
   upload (see the Stage-1-frontend session's Notes paragraph below for what
   happened the one time this was missed).
- 2026-09-22, Phase 2D (closes Phase 2): `stages/analyze/metrics_dimensions.py`
  + `stages/analyze/assemble.py` + `backend/app/services/metrics.py` +
  `backend/app/schemas.py` (`AnalyzeResponse`) + `backend/app/errors.py` +
  `backend/app/services/stage_errors.py` (`ANALYSIS_FAILED`) +
  `backend/app/routers/runs.py` (`POST /analyze`) +
  `tests/stages/analyze/test_metrics_dimensions.py` +
  `tests/stages/analyze/test_assemble.py` + `tests/backend/test_api_analyze.py`
  (8 + 7 = 15 new tests, hand-calculated / real-threaded, plus 1 existing test
  extended - see above). Read `CLAUDE.md`, `PROJECT_PLAN.md` section 12
  (including 2C's own notes on the 2D scope gap), `docs/CONTRACTS.md` section 6
  in full, `docs/SPECS.md` sections 3 and 8, and `metrics_core.py`/
  `metrics_customers.py`/`metrics_products.py` (2A-2C) before writing anything,
  per the session's own brief.
  - Two things the brief itself got wrong were caught before writing any code,
    both flagged back rather than acted on as stated:
    1. **`analyzed` needs no migration.** The brief said the state machine
       "wasn't defined" for Stage 2 completion and asked to confirm whether
       `analyzed` needs adding. It was already there: `RunStatus.ANALYZED` in
       `backend/app/models/run.py`, the very first migration's CHECK
       constraint (`2a9492d9af49_create_runs_table.py`, `2026-09-19`, before
       Stage 1 was even finished), `docs/SPECS.md` section 3's own state
       machine text (`uploaded -> profiled -> planned -> cleaned -> analyzed
       -> imported`), and `get_profile`'s own allowed-statuses list. Nothing
       to invent; just wire the transition. Same class of mistake as 2B's
       "docs/SPECS.md section 5.1" reference (a prior session's own notes,
       not the current docs, misremembered).
    2. **`by_dimension.country` has no data source at all**, a bigger gap
       than anything 2A-2C hit: `contracts/profile.py`'s `CanonicalField` has
       no `country` (product_name, sku, category, transaction_date, quantity,
       unit_price, transaction_type, supplier, customer, note, ignore -
       `category` is real, `country` never was), and `docs/SPECS.md` section 9
       never defined one either. Put to Thach before implementing: `country`
       always reports `[]` (the recommended, and only offered, option) rather
       than fabricate an attribution from an unrelated field; `category`
       computes normally. Revisit only if a country canonical field is added
       to the schema - a stage-1 change, out of scope here.
  - `contribution_pct`'s formula (docs/CONTRACTS.md section 6: "share of the
    total change attributable to that dimension member, signed, not share of
    revenue") was reverse-engineered by hand from the worked example before
    writing any code, then confirmed by the implementation reproducing both
    figures exactly: total_change = core.revenue_current - core.revenue_previous
    (-140000 in the example); member_change / total_change * 100 gives UK
    (940000-1020000)/-140000*100 = 57.14... ~= 57.1, and Home Decor
    (210000-268000)/-140000*100 = 41.43... ~= 41.4 - both match the documented
    figures to one decimal place. This is why `compute_dimension_metrics`
    takes `core: CoreMetrics` directly, unlike `compute_customer_metrics`/
    `compute_product_metrics` (2B/2C), which only needed `period`: the
    denominator is core's own total, not a locally-recomputed one, a real
    dependency the contract text itself names.
  - Not asked, decided directly: a category value is stripped and
    case-folded before grouping, the same pattern 2C's own doubt-review
    established for product identity (`metrics_dimensions.py`'s own
    `_dimension_changes`) - applied proactively this time since the bug
    class (formatting noise silently fragmenting one real value into
    several) was already proven, not just theorized; a blank category value
    is excluded, same "missing" definition `metrics_core.is_blank` already
    uses for `customer`; `by_dimension.category` is unbounded and includes a
    member with revenue in only one of the two periods (no positivity
    filter, unlike products' top_products - a category dropping to $0, or
    newly appearing, is exactly what this block exists to show).
  - `metrics_core.RequiredColumnMissingError` gained a structured
    `canonical_field` attribute (was message-text-only) so the backend layer
    can report which field is missing without parsing a sentence - needed
    for `ANALYSIS_FAILED`'s `details`, the first time a caller outside
    `stages/analyze` needed to inspect this exception programmatically.
  - metrics.json's write is a small, local atomic single-file helper in
    `assemble.py` (temp file, fsync, `os.replace`), not a reuse of
    `stages/ingest/contract_files.py`'s `write_files_atomically` - that
    would be a cross-stage import (CLAUDE.md 3.1), and this session only
    ever writes one file, so the multi-file rollback that helper also
    handles is more than 2D needs. Flagged, not acted on: stages 3-5 will
    each hit this same "one atomic file write" need again, and duplicating
    a ~15-line helper three more times is a real DRY smell worth revisiting
    (moving the single-file case to `shared/`) when stage 3 starts, not
    decided unilaterally this session since it would mean touching stage 1's
    already-shipped, tested code for a stage-2 session's convenience.
  - `POST /analyze` needs no transient claim status the way `execute`'s
    `cleaning` is (decided directly, not asked): the computation is pure and
    deterministic (no AI, docs/adr/0002) and metrics.json's write is atomic,
    so a crash mid-computation leaves the run exactly as it was - never
    "stuck" the way an abandoned `cleaning` claim could be. `RunWork.execution`
    (already-built "one piece of work at a time per run" infrastructure) is
    reused as-is to refuse a concurrent second call outright rather than let
    both redundantly compute; verified with a real `threading.Event`-based
    test mirroring `tests/backend/test_api_races.py`'s own technique for
    `execute`, not just asserted.
  - `ANALYSIS_FAILED` does NOT move the run to `failed`, unlike the seemingly
    parallel `CLEANING_FAILED` (decided directly, not asked, flagged for
    Thach to veto): `cleaned.csv` is still valid and downloadable when stage 2
    can't compute metrics (a missing `unit_price` mapping, or a NOT_INVENTORY
    file), so failing the whole run would be harsher than the situation
    warrants - mirrors how a NOT_INVENTORY run already keeps its `cleaned`
    status and downloads elsewhere in the product (docs/SPECS.md section 10).
    A NOT_INVENTORY file reaching `/analyze` at all is now checked explicitly
    (reusing `analysis.is_not_inventory`/`not_inventory_notice`, already built
    for stage 1), not left to surface as a confusing generic
    "missing canonical field" error.
  - **No doubt-driven review cycle run** (2A skipped, 2B and 2C each ran one
    that found real bugs; this session's own brief asked to decide and
    explain, given it mixes new arithmetic with mostly-assembly work): skipped,
    because every piece of genuinely new logic was independently verified by a
    stronger method than adversarial reading would add on top - the
    `contribution_pct` arithmetic against the documented worked example's own
    numbers (not just internally-consistent hand math, actual published
    figures), and the concurrency behavior against a real multi-threaded race,
    not a single-threaded mock. What's left (`assemble.py`, the router, the
    schema) is thin composition of already-reviewed pieces (2A-2C's builders;
    `run_state`, `RunWork`, `stage_errors` from 1G), not novel algorithmic
    surface like 2B's two-pass RFM re-snapshot or 2C's implied-stock
    derivation - both of which is exactly where those sessions' review cycles
    found real, non-obvious bugs. If a future session finds a bug in this
    session's code, this reasoning - not the size of the diff - is the thing
    to revisit.
  - pytest 1941 passed (up from 1925), `tests/test_architecture.py` included,
    no existing test touched or weakened (one extended, per above).
- 2026-09-22, Phase 2C: `stages/analyze/metrics_products.py` +
  `tests/stages/analyze/test_metrics_products.py` +
  `tests/stages/analyze/test_metrics_products_declines_and_velocity.py` +
  `tests/stages/analyze/products_fixtures.py` (shared test builders, same
  pattern as `tests/stages/ingest/cleaning_fixtures.py`; the test file was
  split in two - `products_fixtures.py` 26 lines, the two test files 237 and
  104 - to stay under CLAUDE.md section 5's ~300-line guideline after the
  doubt-review fix-up added more tests). 15 tests, hand-calculated, then 4
  more from the doubt-review cycle below - 19 total. Read `CLAUDE.md`,
  `PROJECT_PLAN.md` section 12, `docs/CONTRACTS.md` section 6 (the `products`
  block) and `metrics_core.py` (2A/2B) before writing anything, per the
  session's own brief.
  - Confirmed, same pattern as 2A/2B: `docs/SPECS.md` has no section defining
    Pareto/velocity beyond one line under section 4.5 ("last N=14 days"), and
    that line is for the live Dashboard (Phase 7, DB-backed, querying real
    "now") - a different surface than this per-run file analysis. Neither
    `top_products` nor `biggest_decliners` has a documented list-size cap
    anywhere either (the Dashboard's own "top-5" bar chart, also section 4.5,
    is that different surface's own number).
  - The most consequential gap, bigger than anything 2A/2B hit: `days_to_stockout`
    needs a current-stock-on-hand figure per product, but Stage 2 has no such
    canonical field at all, and SPECS section 9's only stock formula ("net in
    minus out, floored at 0") is textually scoped to Phase 7's DB import, not
    this stage - without resolving this, `days_to_stockout` cannot be computed
    by any method. Four decisions were put to Thach before implementing, all
    four answered with the recommended option:
    1. **Stockout data**: derive the same "net in minus out, floored at 0"
       balance from cleaned.csv's own whole-file transaction history instead
       of a DB - every "in" row adds, every counted/"out" row subtracts (a
       return's negative quantity nets back in automatically, same sign logic
       as 2A's revenue). Self-contained pandas, no DB, no cross-stage
       dependency.
    2. **Velocity window**: `period.current` (the calendar month every other
       block already uses), not the Dashboard's fixed 14-day window - a
       static file upload has no "now" to anchor a rolling window to.
    3. **Zero velocity**: a product with no measurable current-period
       velocity is omitted from `velocity` entirely (not a placeholder) -
       also answers the "only ever an 'in' row" edge case from the brief.
    4. **List size**: `top_products` and `biggest_decliners` are each capped
       at the 10 highest-ranked entries, ties broken by product name.
       `velocity` stays unbounded (a stockout-risk inventory, not a
       leaderboard) - decided directly, not asked, since the brief's list-size
       question was specifically about the two ranked lists.
  - Not asked, decided directly: product identity is the row's `sku` value
    when present, else `product_name` (docs/AI_PIPELINE.md section 11's
    business-key precedent, extended here to a per-row fallback since a
    mapped sku column can still have blank cells row by row); `top_products`
    excludes a net-negative-revenue product (not a "top" performer);
    `biggest_decliners`' population is exactly products with nonzero
    previous-period revenue, reusing `metrics_core.pct_change`'s own
    zero-denominator convention rather than a new one; ties in both ranked
    lists break on product name for a deterministic, hand-checkable order.
  - `metrics_core.py` touched again (2A/2B's own 54 tests re-run unchanged
    after, all still green): `ParsedTransactions` gained a `valid` field
    (date/quantity/price present, regardless of transaction_type - needed to
    isolate "in" rows for the stock derivation, since `counted` alone can't
    be inverted back to "in" without it); `_require_column`/`_pct_change`
    promoted to public `require_column`/`pct_change` so this module reuses
    them verbatim instead of redefining "what's a valid decline" or "what
    happens when a required column is unmapped."
  - **Doubt-driven review cycle run** (this module introduces a genuinely new
    kind of computation - deriving an implied stock balance from transaction
    history, no precedent anywhere else in the codebase - plus several
    interacting groupby operations across current/previous/all-time row
    subsets and two different cap/tie-break implementations; comparable
    complexity to 2B, which found real bugs): one fresh-context adversarial
    cycle, cross-model offered and declined again (no gemini/codex CLI
    installed here). 4 findings, all reconciled as valid and fixed:
    - Fixed: product identity mixed `sku` and `product_name` values in one
      flat string namespace with no normalization - a SKU that happened to
      read the same as an unrelated product's name would silently merge
      them, and whitespace/case noise on the same real SKU
      ("SKU1"/" SKU1"/"sku1") fragmented one product into several duplicate
      rows. Fixed by stripping+case-folding the identity value before
      grouping (the same pattern `metrics_core.py` already uses for
      transaction_type matching) and keeping the sku- and name-sourced halves
      in separate namespaces (`sku:`/`name:` prefixes) so they can never
      collide.
    - Fixed: `TopProduct.units` used `int()`, which truncates a fractional
      summed quantity toward zero (a systematic downward bias) rather than
      rounding to the nearest whole unit - quantity is not guaranteed
      integral anywhere in the schema. Now uses `round()`.
    - Fixed: `Pareto`'s population (every product with any current-period
      revenue, including net-negative or net-zero) disagreed with
      `top_products`' population (revenue > 0 only) - two numbers in the same
      contract object that a reader would expect to relate to each other
      could describe different sets of products, understating concentration
      by more than half in the reviewer's reproduction. Pareto now applies
      the same revenue > 0 filter.
    - The reviewer investigated and explicitly dropped a fifth candidate (period
      drift between `product_metrics_for_run`'s own `select_period` call and
      core's) after verifying it is not practically reproducible - noted here
      only because it shows the review actually ran code rather than pattern-matching.
    - All 4 fixes are each pinned by a new hand-calculated regression test;
      the 15 pre-existing tests were re-run unchanged after every fix and
      stayed green throughout.
  - pytest 1925 passed (up from 1910), `tests/test_architecture.py` included,
    no existing test touched, none weakened.
- 2026-09-22, Phase 2B: `stages/analyze/metrics_customers.py` +
  `tests/stages/analyze/test_metrics_customers.py` (33 tests, hand-calculated,
  then 4 more from the doubt-review cycle below - 37 total). Read `CLAUDE.md`,
  `PROJECT_PLAN.md` section 12, `docs/CONTRACTS.md` section 6 (the `customers`
  block), `docs/SPECS.md` section 7.3, and 2A's `metrics_core.py` before
  writing anything, per the session's own brief.
  - The brief's own `docs/SPECS.md` section 5.1 reference for segment
    thresholds does not exist - section 5 is entirely the stage-1 confirmation
    contract, and section 7.3 is the *only* RFM text anywhere in the docs
    ("RFM scoring uses quintiles on the run's own data; the reference date is
    max(transaction_date) + 1 day"). The exact R/F thresholds Thach listed in
    the brief are not written down anywhere in the current docs (grepped
    `PROJECT_PLAN.md`, `docs/AI_PIPELINE.md`, `prompts/strategy.md` too - only
    the five segment *names* appear, in the Phase 2 checklist line and the AI
    strategy prompt's mapping-logic examples, never the thresholds) - same
    "confirm before assuming the old design is current" situation 2A hit.
  - Four decisions were put to Thach before implementing, all four answered
    with the recommended option:
    1. **Segment coverage**: the five given rules (Champions R>=4&F>=4, Loyal
       R>=3&F>=3, At-risk R<=2&F>=3, Hibernating R<=2&F<=2, New R>=4&F<=1)
       leave 4 of the 25 R x F combinations unclassified - (3,1), (3,2),
       (4,2), (5,2), a customer who is reasonably recent but
       low-to-middling frequency. A 6th catch-all segment, "Needs Attention",
       covers them; `segment` is a plain string in the contract, so a sixth
       value validates fine.
    2. **customers_previous**: docs/CONTRACTS.md's `SegmentSummary` has this
       field ("period-over-period comparison") but nothing says what
       "previous" means for a segment count, since RFM is normally one
       whole-history snapshot. Re-runs the same RFM pipeline restricted to
       transactions through the end of the previous period, anchored the day
       after it, and counts customers per segment under that earlier
       snapshot - shows real segment migration, matching the worked example
       (129 Champions last period -> 118 now).
    3. **Return-only customer**: a customer whose only-ever revenue-counted
       row is a return (negative quantity, 2A's convention) is scored and
       segmented like anyone else - no special case; their Monetary is
       honestly negative.
    4. **N=1 customer**: with 2-4 distinct customers, rank-based quintiles
       already spread them across 1-5 without error (verified empirically
       before asking, not assumed). With exactly one customer in the whole
       file, pandas' `qcut` cannot form bins at all (nothing to rank
       against); that lone customer scores 5 and 5 (best available).
  - Not asked, decided directly: RFM (Recency/Frequency/Monetary/segment) is
    one whole-file snapshot anchored at `metrics_core`'s own `Period.data_end
    + 1 day` (directly reused, not recomputed - confirmed this matches
    docs/CONTRACTS.md section 6's own worked example exactly: data_end
    2011-12-09 -> rfm_reference_date 2011-12-10), not scoped to
    current/previous period, since section 7.3 says "the run's own data" and
    a real quintile requires one full, stable population to bin against;
    quintiles use `.rank(method="first")` before `qcut` so ties spread across
    all 5 buckets instead of collapsing into one (a genuine "quintile" needs
    five equal-sized groups) - decided directly rather than asked, since it
    follows from the word "quintile" itself, not a business judgment call; no
    mapped `customer` column degrades the whole block to
    `segments: []`/`new_vs_returning` all zero rather than raise, mirroring
    2A's `active_customers = 0` in the same situation (`rfm_reference_date`
    is still computed - it doesn't depend on `customer`).
  - `metrics_core.py` refactored (2A's own tests re-run unchanged after, all
    still green) to extract `ParsedTransactions`/`parse_transactions`: the
    row-parsing and revenue-scope logic 2A already had, now a function both
    modules call instead of `metrics_customers.py` re-deriving it - same
    stage package, so importing it is not a cross-stage dependency (CLAUDE.md
    3.1). `compute_core_metrics`'s own behavior is unchanged; `select_period`
    also reused as-is.
  - **Doubt-driven review cycle run** (Thach's call was left to judgment,
    given this module's two-pass "previous snapshot" re-computation, rank-based
    tie-breaking and date-boundary arithmetic have more surface area for a
    subtle, hard-to-notice bug than 2A's did): one fresh-context adversarial
    cycle, cross-model offered and declined (neither `gemini` nor `codex` CLI
    is installed here). 4 findings, reconciled against the artifact text
    (not rubber-stamped):
    - Fixed: `NewVsReturning`'s "empty" result was a single mutable
      module-level singleton returned by reference from three call sites
      (`ContractModel` is not frozen) - an in-place mutation on one run's
      degraded result could have leaked into every other run's for the rest
      of the process's life. Now a fresh instance per call
      (`_empty_new_vs_returning()`).
    - Fixed: a whitespace-only `customer` cell was not treated as missing
      (only a true null was), fabricating a phantom customer with their own
      segment row - more consequential here than in 2A's mere off-by-one
      count. `docs/AI_PIPELINE.md` already defines "missing" as "null, or
      holding only spaces" elsewhere, so the fix (a shared `is_blank` helper
      in `metrics_core.py`) extends an existing convention rather than
      inventing one - and was backported into 2A's `_active_customers` too,
      so both blocks agree on who counts as an identified customer.
    - Fixed: `revenue_share_pct` divided by the raw signed whole-file total,
      so a net-negative dataset (returns outweighing sales) flipped every
      segment's sign - a small revenue-*positive* segment showed a negative
      share while the loss-making one showed over 100%. Now divides by the
      magnitude (`abs(total_monetary)`), a no-op for the ordinary all-positive
      case, sign-consistent otherwise.
    - Not fixed, classified as noise (already-decided in 2A, not a new bug):
      a missing `unit_price` mapping makes `parse_transactions` raise
      `RequiredColumnMissingError`, same as 2A's `compute_core_metrics` - this
      module correctly inherits that rather than fabricating a 0 Monetary or
      a misleadingly-empty customers block. Documented explicitly in the
      module docstring since the reviewer's question ("is this really
      intended") was fair even though the answer was already settled.
    - All 3 fixes are each pinned by a new hand-calculated regression test;
      the 50 pre-existing tests (2A's 17 + 2B's 33) were re-run unchanged
      after every fix and stayed green throughout.
  - pytest 1910 passed (up from 1873), `tests/test_architecture.py` included,
    no existing test touched, none weakened.
- 2026-09-22, Phase 2A: `stages/analyze/metrics_core.py` + `tests/stages/analyze/
  test_metrics_core.py` (17 tests, all hand-calculated). Read `CLAUDE.md`,
  `PROJECT_PLAN.md` section 12, `docs/CONTRACTS.md` section 6, `docs/adr/0002`,
  `CONSTRAINTS.md`, `contracts/metrics.py`, `docs/SPECS.md` section 9,
  `docs/FIGMA_DESIGN_NOTES.md`'s flagged open question, `docs/AI_PIPELINE.md`
  sections 5/11/12 and `tests/test_architecture.py` before writing anything, per
  the session's own brief.
  - Four decisions were flagged as genuinely unresolved (no config.yaml exists,
    no period field in `Settings`, and FIGMA_DESIGN_NOTES.md section 8 explicitly
    says "SPECS does not define how returns are identified... decide before Phase
    6") and put to Thach before implementing, all four answered:
    1. **Period selection** (no config anywhere; must come from the data itself,
       since stages stay framework-free and runnable standalone): `current` is the
       latest calendar month fully elapsed by `data_end` (`select_period` in
       `metrics_core.py`); `previous` is the month before it. Reproduces
       docs/CONTRACTS.md section 6's own worked example exactly (data_end
       2011-12-09 -> current 2011-11, the partial December excluded) - a
       dedicated test pins this. Falls back to `now`'s month when the data holds
       no parseable date at all.
    2. **Revenue scope**: an "in"-type row (stock coming back, e.g. a supplier
       restock) is excluded from revenue/orders/AOV entirely, never subtracted -
       `transaction_type` is stock movement direction only (docs/AI_PIPELINE.md
       section 5), never a returns concept, so folding it into a signed sum would
       misreport a restock as negative revenue. Unmapped transaction_type, or an
       unrecognised per-row value, defaults to "out" (docs/SPECS.md section 9).
    3. **Return detection**: a return is a revenue-counted row with negative
       quantity (the common POS convention of a negative-quantity sale line).
       `return_rate` = count of those rows / count of revenue-counted rows in the
       period. Works whether or not `transaction_type` is mapped, since it only
       depends on quantity's sign - the safer "always 0.0, deferred" alternative
       was offered and not chosen.
    4. **Zero denominators**: `revenue_change_pct` with `revenue_previous == 0`,
       and `aov`/`return_rate` with `orders == 0`, all report `0.0` - never a
       manufactured "100% growth from nothing" figure. A dedicated test
       (`test_zero_orders_in_the_previous_period_...`) pins this against the
       rejected alternative.
  - Not asked, decided directly (lower-stakes, no real alternative to weigh):
    `orders` = count of revenue-counted rows (the canonical schema has no
    invoice/order-id field to group by, so a row is the only unit available);
    `active_customers` = count of distinct `customer` values among
    revenue-counted rows in the period, `0` when `customer` isn't mapped (same
    "no signal -> 0" pattern as the return-rate design, just not one FIGMA_DESIGN
    _NOTES.md had already flagged); `unit_price` not being mapped (legal at stage
    1 - only `product_name`/`transaction_date`/`quantity` are required fields,
    docs/AI_PIPELINE.md section 11) raises `RequiredColumnMissingError`, since
    revenue cannot be computed without a price and pandas must not invent one
    (docs/adr/0002); a row whose date, quantity or price does not parse is
    excluded from every period-based number rather than guessed at (a real gap:
    docs/AI_PIPELINE.md section 12 notes a plan cannot require `transaction_date`
    to be parsed, so cleaned.csv's date column is not guaranteed to be ISO 8601)
    - `select_period`'s `data_start`/`data_end` still use every parseable date in
    the file, not just revenue-counted rows, since they describe the dataset's
    own span, not revenue's.
  - `compute_core_metrics(df, column_mapping, now=None)` is pure (no disk I/O);
    `core_metrics_for_run(runs_root, run_id, now=None)` reads `cleaned.csv` +
    `cleaning_report.json` via `shared/run_registry` and calls it - mirrors
    `profiling.py`'s `profile_csv`/`profile_run` split. Neither writes anything:
    assembling and writing the full `metrics.json` (the `customers`, `products`
    and `by_dimension` blocks too) is 2B-2D. `cleaned.csv` is read with
    `dtype=str` and every needed column converted explicitly in this module
    (`pd.to_datetime`/`pd.to_numeric`, `errors="coerce"`), the same "read every
    value as raw text" approach `profiling.py` uses for `raw.csv`, since nothing
    guarantees stage 1 already cast these columns.
  - No doubt-driven review cycle run: the session's own brief said to skip it if
    the hand-checked tests alone gave confidence once implemented, and 17 tests
    covering every branch (both zero-denominator paths, unmapped
    transaction_type/customer, case/whitespace-insensitive type matching, an
    unrecognised type value, unparseable dates/quantities/prices, a fully empty
    dataframe, all three required-column-missing paths, and the exact CONTRACTS.md
    worked example) did.
  - A pandas gotcha hit and fixed during testing, not part of any design
    decision: `df[type_col].str...` raised `AttributeError` on an empty or
    all-missing column, because an empty/NaN-only column can read back as
    `float64`, and `.str` only works on object/string dtype. Fixed with
    `.astype(object)` before `.str`; a dedicated empty-dataframe test still
    passes.

Earlier ask, now met - the real `.env` needed two lines `.env.example` had already
gained (`PREVIEW_CACHE_MAX_MB`, `PREVIEW_CACHE_TTL_SECONDS`):
```
PREVIEW_CACHE_MAX_MB=300
PREVIEW_CACHE_TTL_SECONDS=900
```
**Notes:**
- 2026-09-22, `docs/adr/` session (docs-only, no application code; git tree
  clean at start), using `documentation-and-adrs` (Wave 2). Read
  `PROJECT_PLAN.md` section 2 and the Phase 0/1 history, `docs/CONTRACTS.md`
  section 1 and `docs/AI_PIPELINE.md` sections 1-3 first, rather than
  summarizing from memory. Wrote exactly the three ADRs the Phase 2 checklist
  line names, in `docs/adr/` (the location that line and this session's brief
  both name; the skill's own default is `docs/decisions/`, but its own
  instructions say an established convention overrides that default, and
  `docs/adr/` was already established by the checklist line before this
  session ran):
  - `0001-stage-isolation-single-repo.md`: cites the 0A session's own
    Notes bullet ("ONE repo with five independent stage packages... instead
    of five separate repos... Splitting into separate repos later stays
    possible precisely because of that boundary") as the decision record,
    and section 2's rationale line, for the alternative-considered section
    the brief asked for.
  - `0002-pandas-computes-ai-interprets.md`: sourced from `CLAUDE.md` 3.2 and
    `docs/AI_PIPELINE.md` sections 1 and 3 (bounded input, the whitelisted
    transform catalog, the validate-retry-degrade policy).
  - `0003-model-selection-policy.md`: sourced from `docs/AI_PIPELINE.md`
    section 2 (`MODEL_REASONING`/`MODEL_BULK` split, `MODEL_BULK` unused in
    v1 but required like every other setting) and `backend/app/config.py` /
    `backend/app/services/analysis.py` (confirmed by reading the code, not
    assumed, that both of v1's stage-1 AI calls pass `settings.model_reasoning`
    today). States the policy, not a model id, as the brief asked.
  Each ADR uses the skill's own template (Status, Date, Context, Decision,
  Alternatives Considered, Consequences), with Consequences split into
  Benefits and Trade-offs accepted per the brief - the skill's default
  template does not separate them, this session's brief explicitly asked to.
  Linked from both `CLAUDE.md` (section 1's doc index, section 2's model line,
  3.1's and 3.2's "Why" paragraphs now point at the matching ADR instead of
  restating the rationale inline) and `PROJECT_PLAN.md` (section 2 and
  section 7), per the "docs hold the rule, ADRs hold the why" split the Phase
  2 checklist line itself states. Both checklist items now ticked (Wave 2
  install; `docs/adr/`). pytest 1856 / Vitest 54 re-run and unchanged (no
  application code touched). Thach confirmed in chat: Phase 2A is the next
  step right after this session, resolving the ambiguity the Wave 2 session
  had flagged between this checklist line and Phase 2A.
- 2026-09-22, skills Wave 2 install (tooling session, no application code;
  git tree was clean at start; Phase 1 1A-1G complete confirmed the trigger
  condition). CLI syntax re-verified with `npx skills add --help` rather than
  assumed from Wave 1: unchanged (`add -a <agent> --copy -y -s <skill>`, same
  as `docs/SKILLS.md` section 5). Installed exactly the four Wave 2 skills
  (`code-review-and-quality`, `code-simplification`, `documentation-and-adrs`,
  `ci-cd-and-automation`) via one `npx skills add` call; `skills-lock.json`
  updated automatically with correct source/hash entries, no manual edit
  needed. `npx skills list` shows all 14 (10 Wave 1 + 4 Wave 2), no more, no
  less. The two Wave 2 personas (`test-engineer`, `code-reviewer`) were copied
  by hand into the new `.claude/agents/` (this is the first session with any
  persona - Wave 1 installed no personas, so there was no literal prior
  precedent for "same mechanism"; used the same clone-to-scratch-copy-delete
  approach `docs/SKILLS.md` section 5 describes for skills): cloned
  `addyosmani/agent-skills` into the session scratchpad, copied
  `agents/code-reviewer.md` and `agents/test-engineer.md`, deleted the clone.
  Both files' "Composition" section links to `../docs/agents.md`, which
  resolves to `.claude/docs/agents.md` from `.claude/agents/` - that file is
  not installed (`docs/SKILLS.md` section 2 only names `.claude/references/`
  for shared checklists, nothing about agent docs), so the link is dangling;
  left as-is, flagged for Thach, not fixed since it is outside this session's
  named scope. `performance-checklist.md` copied into `.claude/references/`
  the same way; confirmed `code-review-and-quality/SKILL.md`'s
  `../../references/performance-checklist.md` link resolves. Added
  `.github/workflows/ci.yml` (ubuntu-latest, Python 3.14 matching
  `backend/requirements.txt`'s own pin, `pip install -r backend/requirements.txt`
  then `pytest` - `tests/test_architecture.py` runs as part of that, already
  collected by `pytest.ini`'s `testpaths`). No secrets or services:
  `tests/conftest.py` sets `DATABASE_URL=sqlite://` and every other required
  `Settings` field via `os.environ` before any test imports `app.config`, so
  CI never touches Postgres or needs `.env`. Decided without asking, for Thach
  to veto: triggers on both `push` (any branch) and `pull_request` into `main`,
  not `push` alone as the session brief's literal wording said - standard CI
  practice, costs nothing extra, still needs no secrets either way. Checked
  `CLAUDE.md`'s "Skill precedence" section against all four new skills' own
  text (grepped for commit/push/autonomous-run language): no new conflicts,
  so left unchanged, matching what `docs/SKILLS.md` predicted. Verified after
  every install step: pytest 1856 passed (repo root, via `backend/venv`'s
  `python -m pytest`), Vitest 54 passed across 9 files - both counts unchanged
  from before this session, as expected, since nothing in `stages/`,
  `backend/app/`, or `frontend/src/` was touched.
- 2026-09-22, later the same day: a bug fix + a Preview pane rebuild, both on
  the Review screen the previous session built.
  - **Bug fix** (found manually testing Review with real Kaggle data): the AI
    mapped a "Payment Method" column (Cash / Credit Card / Digital Wallet) to
    canonical_field `transaction_type`, which `docs/SPECS.md` section 9
    defines as stock movement direction (`in`/`out`) - an unrelated concept
    the field's own name (containing "type" and "transaction") invites
    confusing it with. Nothing downstream would have caught it: the mapped
    value is an ordinary string either way, so this would have silently
    corrupted `current_stock` once Phase 7 exists. Fixed in
    `prompts/schema_inference.md` (new "CANONICAL FIELD NOTES" section: the
    definition, what it is not, a concrete negative example mapped to
    `ignore`) and `docs/AI_PIPELINE.md` section 5 (same clarification,
    inline). Regression test: `tests/stages/ingest/test_schema_inference_prompt.py`
    (4 tests, mirrors the existing `test_cleaning_plan_prompt.py` pattern of
    testing a prompt's own content, since the fix is prompt wording and there
    is no code to unit-test). A real-API check that the model now avoids the
    wrong mapping (like 1C's one-off) was not run this session - offered to
    Thach, not done, given the token-spend note two bullets down.
  - **Preview pane rebuild**: `design/mockups/Review.png` was re-exported
    (file-modified today) but `docs/FIGMA_DESIGN_NOTES.md` was not updated
    alongside it (unchanged since 2026-09-19, no "Preview pane" section). The
    missing section 7 was written from the new PNG plus Thach's own
    description before building against it (old section 7 "Handoff notes" ->
    8, "Design principles" -> 9; nothing elsewhere in the repo references
    either by number). `frontend/src/components/PreviewPane.tsx` rebuilt as
    one table (was Before/After side by side): a pinned Row column, only
    columns changed in the displayed sample shown by default (the rest behind
    "Show unchanged columns (N)"), a dotted underline as the non-color signal
    on a changed/filled cell (SPECS section 11), the original value and the
    action that ran in a tooltip on hover AND keyboard focus
    (`tabindex="0"`, `aria-describedby`), numeric columns right-aligned with
    a trailing ".0" dropped, the row-count chip labeled "(full file,
    projected)". New domain module `frontend/src/domain/previewDisplay.ts`.
    Dropped-row reasons ("No qty", "Duplicate") are real now, not the
    fabricated-vs-honest tradeoff the previous session's Notes flagged -
    `PreviewResult` still carries no reason field, but the reason is now
    *derived* from the plan actually submitted plus the row's own "before"
    values (both already available once `PreviewPane` takes the `plan` as a
    prop): "Duplicate" when `remove_exact_duplicates` is planned and another
    displayed row has identical "before" values (checked first, since that
    action runs before any column action in the fixed execution order,
    `docs/AI_PIPELINE.md` section 6); otherwise "No `<field>`" when a
    required field's column has `drop_rows_missing` and this row is blank
    there; otherwise "Dropped", claiming nothing further, when neither is
    determinable from the 20 rows on screen (a duplicate whose pair fell
    outside them, or a non-required column's `drop_rows_missing`). 12 new
    domain tests + 6 new component tests
    (`frontend/src/domain/previewDisplay.test.ts`,
    `frontend/src/components/PreviewPane.test.tsx`).
  - Checked, as asked: whether "no cells appeared visually tinted" in the old
    preview was a pre-existing bug. The old component's code did set the
    `preview-cell--changed`/`--added`/`--removed` classes correctly, and the
    previous session's own live-browser screenshot (before this rebuild)
    showed yellow/green/red cells rendering. Does not look like a code bug;
    moot now regardless, since that component no longer exists - if it
    recurs with real data after this rebuild, it needs its own look with the
    exact file that showed it.
  - **No AI tokens spent this session** (contrast with the paragraph below):
    `.env`'s `ANTHROPIC_API_KEY` was checked before touching anything
    upload-related, and no browser/upload flow was driven this time - Thach
    asked to re-verify live himself. Both dev servers were started only to
    confirm a clean boot (`/health`, then left running for Thach to check),
    never driven past that.
- 2026-09-22 Stage-1 frontend session (scoped exception, not Phase 6 - see the note
  under Phase 6 above): built `frontend/src/pages/{Upload,Analyzing,Review,Results}Page.tsx`
  wired to the real 1G API, per `docs/FIGMA_DESIGN_NOTES.md` frames `Upload` (`7:851`),
  `Upload - Analyzing` (`7:955`), `Review` and its 4 variant frames, `Results` (`7:1098`),
  using the design tokens in that file's section 4 (`frontend/src/styles/tokens.css`).
  No router: `App.tsx` is a small screen state machine (Upload -> Analyzing -> Review ->
  Results), since only these 3 screens exist and Insights/Dashboard need Phase 2-5 data
  that does not exist yet. 33 Vitest tests (up from 9): upload validation, the
  plan-edit-to-preview debounce (fake timers), required-field gating, NOT_INVENTORY
  mapping-disabled mode, error-state rendering per `design/mockups/Errors.png`, and an
  `App.test.tsx` integration path including the branch that must skip `POST /plan`
  when the schema step came back AI_UNAVAILABLE (no `schema_inference.json` written,
  so `/plan` would itself answer INVALID_STATE). `npx tsc -b` and `npm run lint` clean.
- **Real AI tokens were spent, by accident.** The repo's real `.env` (not `.env.example`)
  already held a real `ANTHROPIC_API_KEY`, not the placeholder. Manual browser
  verification of the Upload -> Review flow (CLAUDE.md "Definition of Done": verify at
  runtime, not only via tests) was run without first checking the key, so the one
  upload made 2 real calls (schema inference, cleaning plan) against Thach's account -
  small (this project's earlier 1C real-call note: about 3 cents for one call), but a
  real miss of CLAUDE.md section 8 / the DoD item ("run with a fake `ANTHROPIC_API_KEY`
  ... real tokens are spent only when Thach asks"). Flagged to Thach the moment it was
  noticed, mid-session; no further AI-triggering action (re-upload, "Try AI again") was
  taken afterward - the rest of the manual check (editing the plan, the debounced
  preview, Confirm & Clean, the Results downloads) used `/preview` and `/execute`,
  neither of which calls the AI. Lesson for every future session: check which key is in
  the real `.env` before the first browser-driven upload.
- Two gaps in the built API were found while building the screens the API is supposed
  to serve, and fixed rather than worked around, since both are already implied by
  `docs/SPECS.md` section 8 and needed by SPECS section 4.2/4.3, not new scope:
  - `GET /api/runs/{id}/profile` (`app/services/analysis.py:get_profile`,
    `tests/backend/test_api_profile.py`, 4 tests): the Review screen's dataset summary
    strip (SPECS 4.2 A: rows, columns, duplicate rows, missing %) and the Analyzing
    screen's row/column count need `profile.json`, which no endpoint returned;
    `schema_inference.json` cannot substitute (capped at 25 columns, no dataset
    totals). Read-only, no work claim; INVALID_STATE before the run is profiled,
    EXPIRED if the file is gone.
  - `GET /api/runs/{id}/download/cleaned.csv` (`app/services/downloads.py`,
    `tests/backend/test_api_downloads.py`, 5 tests): the Results screen's CSV download
    (SPECS 4.3) - `execute`'s response never carried `cleaned.csv` itself, only the
    report (SPECS 8 already says "download urls" belong on that response; 1G did not
    build them). The uploaded filename is user-supplied and only its extension was
    checked at upload (SEC-1), so the download filename is sanitized to
    `[A-Za-z0-9._-]` before it reaches the `Content-Disposition` header (a test proves
    a filename with `"`, `;` and CRLF cannot inject a header). `cleaning_report.json`
    needed no endpoint: `execute`'s response already carries the full report, so its
    download button serializes that in the browser.
  These were decided without asking, for Thach to veto: both are thin, read-only,
  reuse the existing state-machine/error patterns (`run_state.require_status`,
  `stage_errors.files_gone`), and were each given the same test coverage a 1G endpoint
  got.
- UI simplifications versus the mockups, decided without asking, for Thach to veto:
  - The Action cell's params editor is inline under the dropdown, not a floating
    popover (`design/mockups/Review - Edit Action.png`); `fix_negative` is one dropdown
    entry ("Fix negative values") with an inline strategy select, not the mockup's two
    entries ("Flag negatives (keep)" / "Fix negative values..."). Same data submitted
    either way - the difference is only how many clicks reach the params.
  - The mockup's "abs" strategy label is "Set to 0"; the transform actually replaces a
    negative with its absolute value (-5 -> 5), never 0
    (`stages/ingest/transforms.py fix_negative`, `strategy="abs"`). Built as "Make
    positive (absolute value)" instead of copying a label that misdescribes the data.
    Flagged for Thach to fix the mockup text or confirm the behavior is what he wants.
  - The preview pane's dropped-row reasons ("No qty", "Dup. row") and the "What ran"
    table's expanded row (specific row numbers, "Reason recorded per row:
    missing_required_field(quantity)") in the mockups are not data
    `PreviewResult`/`ChangeLogEntry` actually carry (`stages/ingest/preview.py`: a
    dropped row's `changed` is forced empty, with no reason code; `ChangeLogEntry` has
    no row list). Built honestly instead of invented: the preview shows "Row dropped"
    with no reason, and a "What ran" row only expands when it has real params to show.
    Worth a contract addition later if Thach wants the mockup's level of detail.
  - `drop_column` entries are shown one per column (`docs/CONTRACTS.md` section 5: one
    `ChangeLogEntry` per column dropped), not aggregated into the mockup's single
    "4 columns" row - aggregating would need grouping rules the contract does not
    define.
  - Column issue badge severity (low/medium/high, the badge color) is a client-side
    heuristic (`frontend/src/domain/issueSeverity.ts`): `ColumnIssue`
    (`docs/CONTRACTS.md` section 3) carries no severity, only `DatasetIssue` does. The
    rule: `missing_values` is high on a required field or at >= 5% elsewhere (the same
    5% line SPECS section 6 uses for impute-vs-Unknown), medium below that; cosmetic
    codes (whitespace, case, near-duplicates, exact duplicates) are low; codes that can
    corrupt a column or drop data unnoticed (`all_null_column`,
    `non_numeric_in_numeric`) are high; everything else is medium. Matches every badge
    color in `design/mockups/Review.png`'s sample data by construction, but is a rule
    this session invented, not one SPECS or CONTRACTS states - for Thach to veto or
    move into SPECS if it should bind the backend too.
  - Upload's client-side size check uses the SPECS section 1 ceiling (50MB), not the
    server's actual configured `MAX_UPLOAD_MB` (open question left by the original 6A
    line: no second source of truth for the real, possibly lower, limit exists on the
    frontend). A file over 50MB is rejected before upload; a file the server's real
    limit rejects (if lower than 50MB) still gets the server's real FILE_TOO_LARGE
    answer, shown the same way. `frontend/src/domain/upload.ts` has the reasoning.
- Not built this session (deliberately out of scope, per the session's own brief):
  dataset-actions editing (`remove_exact_duplicates` / `flag_duplicate_keys` are shown
  nowhere in the UI; a manually-built plan always starts with none, an AI plan keeps
  whatever it proposed); an accessibility or Vitest coverage pass beyond what the tests
  above already exercise; i18n (none needed, SPECS 11 says English only).
- 1G decisions (Thach): none asked mid-session; the design choices (profiling folded
  into `analyze-schema`, preview/execute allowed from `profiled` for a hand-built plan,
  the NOT_INVENTORY waiver, byte-budgeted cache over a cell-budgeted one, a per-run
  per-step AI attempt cap) are explained in the 1G checklist line and in `docs/SPECS.md`
  section 3's new state table for Thach to veto.
- 1G review (one doubt-driven cycle, fresh reviewer, cross-model declined by Thach):
  5 high-severity findings (a leaked server path, a run strandable in `cleaning`, an
  unbounded AI call count with a state-mismatch race, one preview able to starve the
  server) and 6 medium (the cache counted cells not bytes; an evict during a read could
  restore a stale frame; a NUL byte in a run id reached PostgreSQL as a 500; a
  concurrent `analyze-schema` on a fresh run read a stale status; `MemoryError`/`OSError`
  wrongly failed the run for good; the real `.env` needed updating). All fixed, each
  with a reproducing test (`tests/backend/test_api_hardening.py`,
  `test_api_recovery.py`, `test_run_state_hardening.py`); the fixes were then checked by
  mutation testing (every mutant killed), not reviewed a second time, by the same
  one-cycle decision as 1C/1F.
- One bug found while splitting long test files after the review (not in the reviewed
  code itself): Python 3.14 defers annotation evaluation (PEP 649), so a missing
  `import` used only in a type hint or inside a lambda is not a `NameError` until that
  code actually runs - a test with a stray missing import can pass for the wrong reason
  if the code under test also happens to answer 500. Fixed by pinning the real cause
  with `caplog` in `test_a_missing_prompt_template_is_a_500_that_shows_no_server_path`.
- Old 1F notes (kept for history):
- 1F decisions (Thach): a date written with a UTC offset keeps its date and time as
  written and drops the offset; `drop_rows_missing` is its own step before the
  imputations (`EXECUTION_ORDER`, AI_PIPELINE section 6); execute rejects a plan that
  drops a column mapped to a required field (the preview allows it); one review cycle
  only, cross-model skipped.
- 1F choices made without a question, for Thach to veto: execute also writes
  `plan_final.json` (CONTRACTS lists it, nothing owned it); the preview is its own
  module (`preview.py`, 300-line rule) and `cleaning.py` holds the shared engine;
  `cleaned.csv` keeps the source column names, writes ISO dates and holds the `__flag_*`
  columns; `column_mapping` omits ignored and dropped columns; a plan that leaves no
  row is refused; a parsed year outside 1900-2100, `now`, `today` and a bare time are not
  dates (the range is my choice: say if it should differ); a `standardize_categories`
  mapping may not target an empty text or a missing-value token, and the report warns
  (`text_reads_as_missing`) when cleaned text would read back as missing; a file whose
  rows have an extra field that holds data is rejected (PARSE_FAILED).
- 1F review (one doubt-driven cycle, fresh reviewer, cross-model skipped): 17 findings.
  The high one was in 1B: a trailing delimiter on every row made pandas use the first
  column as the index, so `profile.json` was wrong, the preview crashed and execute wrote
  shifted data. Fixed with tests, all in AI_PIPELINE section 12: that, the rollback when a
  rename fails (Windows refuses to replace a file another process holds open), flag
  columns overwriting a source column or left all False, infinity counted as a number,
  `now` / `10:30` / year-less dates, offset forms like `+10` and `UTC`, an honest
  change-log detail, wide files (execution 45 s -> 17 s, the problem-row search bounded by
  cells), `write_contract` line endings, `fsync`. Not fixed: a blank required cell
  survives (one action per column, `drop_rows_missing` drops only missing), concurrent
  executes (1G claims the run), the preview date format on a sampled file, preview over
  3 s on files near 50 MB (the read alone is 2.6 s: cache the frame), nanoseconds
  truncated. The fixes made after the review were not reviewed again, by decision.
- Tests changed in 1F, none deleted or skipped: two 1E tests that pinned "mixed offsets
  fail until Thach decides" now test the decided behavior; `test_the_order_is_the_documented_one`
  has the new order (every earlier pair is still asserted); one `test_contract_files`
  expectation followed the rollback (a failed second rename no longer leaves the first
  file behind).
- 1E in short (details in AI_PIPELINE sections 11 and 12): pandas overwrites the AI's
  issue counts, with no retry on a difference, and a count of 0 removes the issue; the
  business key is sku (else product name) + transaction date + transaction type; the
  plan step's answer checks report every problem in the one retry message
  (`plan_checks.py`); three review cycles found a plan dropping the column its own
  `flag_duplicate_keys` needs, a lone UTF-16 surrogate crashing the write (fixed once, in
  `shared/ai_client.py`) and more. The plan prompt met the real model once (Thach, a
  25-row file, no retry needed, no required field imputed).
- Decided by Thach at the end of 1F: the date range 1900-2100 stays;
  `near_duplicate_labels` is reported only for text and categorical columns (so a number,
  an identifier, a date and a boolean are outside it; "A+" and "A-" in a text column
  still count as near-duplicates, which was accepted); `drop_rows_missing` also drops a
  cell of only spaces; one action per column stays until the review screen (6B) shows
  what is needed; CLEANING_FAILED (422) for a run that fails on its data; a column-count
  limit is left to 8A.
- Accepted limits of 1E's answer checks: an impossible issue count still uses the retry,
  counts describe the raw file, rows with a missing key part count as sharing the key,
  `examples` and `domain_reasoning` are not number-checked, the recount has no cost bound
  (about 3 s per 300,000 rows of unique text over 11 codes).
- Tooling: heredocs through the Bash tool collapse `\\` to `\`, so a script that writes
  escape sequences (`\ud800`, regexes) must be written with the file-writing tool, not a
  heredoc.
- 1D catalog decisions: `cells_affected` counts cells this action changed or
  removed, `rows_affected` counts rows it dropped or marked, and one action
  fills one of the two (the table in `transforms.py`'s docstring is the list).
  An action that ran and changed nothing is still logged with two zeros
  (Thach). A failed cast or parse leaves the cell missing and adds a boolean
  flag column `__flag_<kind>__<column>`, added only when something is flagged.
  Dropping rows keeps the row index, so a gap shows where a row was.
- 1D `cast_type` targets are integer / float / string / boolean, and
  `normalize_case` modes title / lower / upper; both are data in
  `transform_catalog.py` for 1E to validate a plan against. Casting "3.7" to
  integer is a flagged failure, never a 4.
- 1D issue counts: every one of the 15 issue codes has a source for its number:
  three come from `profile.json`, eleven from `issue_counts.count_column_issue`
  and `duplicate_business_key` from `count_duplicate_business_key`. 1E wired
  them into `ai_schema.py` through `issue_recount.py` (see the 1E notes).
- 1D counting definitions worth knowing: `invalid_dates` and
  `mixed_date_formats` count 0 unless more than half the column's values
  parse as dates (otherwise every product-name column would report its whole
  length); `inconsistent_case` counts cells that are not the dominant
  spelling of their case-folded label; `near_duplicate_labels` ignores case,
  spacing and punctuation but never counts a pure case difference, so the two
  codes stay disjoint; `mixed_types` counts the minority kind when a column
  holds both numbers and text.
- 1D sample rows: `_problem_masks` now has six kinds, not three (added: text
  in a column of numbers, padded whitespace, an unparseable date). Because
  six kinds share the 30 rows, `PER_PROBLEM_KIND` went from 5 to 3, so
  ordinary rows are still visible - the semantic types are inferred from
  them. `test_each_problem_kind_is_capped_at_five` was renamed and rewritten
  for the new cap (a stricter assertion, not a weaker one); the four new
  kinds have their own tests.
- 1D performance: deciding a column's kind uses a 500-row probe
  (`column_kinds.PROBE_ROWS`) before converting the whole column, the same
  trade-off `profiling.py` already makes for its numeric probe. Measured on
  this machine: `pd.to_datetime(format="mixed")` is about 0.025 s per 200k
  values and `pd.to_numeric` about 0.1 s, so an unprobed scan of 25 columns
  of a 50MB file would have cost seconds.
- 1C call policy (`docs/AI_PIPELINE.md` sections 1-3 updated): no sampling
  parameters, because `claude-sonnet-5` rejects `temperature` with a 400;
  thinking disabled, so the 3000 tokens and 30 s cover the JSON answer; the
  SDK's own retries off, so every retry is counted against the run budget.
  The caller passes the API key, the model id and the run's `RetryBudget`
  (`shared/` may not read settings, SEC-4). Structured outputs
  (`output_config.format`) are a later candidate, to be checked with a real
  call first.
- 1C degraded mode: `AIUnavailable.reason` is one of timeout, network, auth,
  rate_limited, api_error, invalid_response, truncated, refused. Truncated
  and refused answers are not retried; API failures do not spend the retry.
  The reason is logged and carried by the exception, never written to a
  contract (Thach). A degraded run writes no `schema_inference.json` and
  deletes an earlier one, so no later step reads a valid-looking file; other
  errors (a broken template) leave it alone.
- 1C bounded input: 25 columns (not 60: more does not fit in 3000 output
  tokens), 30 stratified sample rows, every value cut to 100 characters
  including the mark. Sample rows go as a header plus positional value
  lists, so 25 names are not repeated 30 times. Column names are never cut,
  because the answer must repeat them exactly; a pathological header belongs
  to 8A.
- 1C answer checks (all use the single retry): every sent column exactly
  once, one canonical field per column, column issue counts within the rows
  and dataset counts within the cells, and the figures the profile holds
  (`missing_values` vs `null_count`/`null_pct` with a 0.1 tolerance,
  `duplicate_rows`, `all_null_column`) must match. Any other code must have
  `pct: null`. The AI's names are matched back to the file's exact names
  when trimming and case-folding leaves one candidate. Answers are validated
  strictly (`true` is not 1.0), and unknown extra keys are ignored on
  purpose, since they are dropped rather than stored.
- 1C review: three doubt-driven cycles (the skill's limit), each with a
  fresh-context reviewer; cross-model skipped by Thach each time. Cycle 1
  found the unbounded value size and the unchecked figures; cycle 2 the
  dataset counts measured in cells and the stale-profile hole; cycle 3 a
  real bug in cycle 2's own fix (an `elif` chain skipped the `pct` rule for
  `all_null_column`). Everything actionable is fixed with tests. Accepted
  trade-offs: issue `examples` have no length cap, and the dataset figures
  cover the whole file while only 25 columns are described (the profile the
  AI sees now says how many).
- Why call 1 was rejected in that check: the model put cell values in issue
  `examples` and wrote a real `null` there, which `list[str]` refuses (the
  schema layer in `shared/ai_client.py`, five times). The retry turned it into
  the string "null" and passed. `prompts/schema_inference.md` now says
  `examples` are row references ("row 4"), never a value and never null, so
  that the run's single shared retry is not spent on formatting.
- 1C verified against the real API once (2026-09-20, Thach ran a throwaway
  script on a 12-row messy CSV, about 3 cents): call 1 was rejected, the
  retry corrected itself and passed both the schema and the stage checks, and
  the model obeyed the new `pct` rule. It distinguished `duplicate_rows` from
  `duplicate_business_key` and found `mixed_date_formats` and
  `near_duplicate_labels` in the planted dirt. Everything else in the suite
  is mocked; this was the only real call.
- CONSTRAINTS F4 is active: `tests/conftest.py` blocks the real httpx2/httpx
  transports and records every attempt, so a call the SDK or our client
  swallows still fails the test at teardown. Verified with a probe that
  caught the error and still failed.
- 1B decisions (Thach): missing = the 19 pandas 3.0 default NA tokens, listed
  explicitly in `NA_TOKENS` (so "NA" counts as missing, even when it means
  Namibia); `sample_values` = up to 5 values per column from evenly spaced
  rows (`i * (n - 1) // 4`), raw text, missing kept as null.
- 1B design: the file is read once with every value as text, so
  `top_values`/`sample_values` show the file's own spelling ("0012",
  "12.50"). A column is numeric when it has at least one value and every
  non-missing value is a finite number; then `dtype` is pandas' `int64` /
  `float64` (float64 when there are gaps) and the stats are filled, else
  `dtype` is `str` and the stats are null. Quartiles and median use pandas'
  default linear interpolation. `unique_count` compares raw text ("8.5" and
  "8.50" are two values). Top values: count descending, ties by value.
  Percentages are not rounded.
- 1B encoding and delimiter: UTF-16 BOM -> `utf-16`; else strict UTF-8 (BOM
  stripped from the first column name); else `latin-1` (SPECS section 10).
  The latin-1 warning belongs in `cleaning_report.warnings`
  (`encoding_fallback`, CONTRACTS section 5), so 1B only records
  `encoding_used` and 1F emits the warning (written into the 1F line).
  Delimiter: `csv.Sniffer` over `, ; \t |`; a header with none of them is a
  single-column file; otherwise `CsvParseError`.
- 1B errors: the stage raises `EmptyCsvError` (`code = EMPTY_FILE`: no lines,
  or header-only) and `CsvParseError` (`code = PARSE_FAILED`: a row with too
  many fields, invalid UTF-16, undeterminable delimiter). 1G maps them to the
  envelope (written into the 1G line). `profile.json` is written atomically
  (temp file + `os.replace`).
- 1B performance (SPECS section 11: profiling a 50MB file under 3 s): a
  generated realistic 50 MB CSV (712,645 rows x 9 columns) took 5.1 s at
  first; two result-preserving optimizations brought it to 3.3 s (a
  200-value probe that rejects text columns before a full numeric
  conversion, and reusing `value_counts` for unique count and top values);
  `pyarrow==25.0.1` (Thach approved; pandas 3 then uses it as its string
  backend, no code change) brought it to 2.86 s. The margin is thin (~5%);
  re-measure if profiling grows. No timing test in the suite (it would be
  machine-dependent and flaky).
- One-off security check for the new dependency (Thach's request, 1B), not
  the official W3 install: pip-audit 2.10.1 ran from a throwaway venv that was
  deleted afterwards (project venv unchanged, 52 packages). `pyarrow==25.0.1`:
  no known vulnerabilities. Whole project venv: one finding, pip 26.1.2
  `PYSEC-2026-3721` (fixed in 26.2); pip is the venv installer, not a
  `requirements.txt` dependency. Fixed with Thach's approval: the project
  venv now has pip 26.2.1. A recreated venv must upgrade pip the same way.
- 1A2 schema: `runs` has exactly the 7 SPECS section 9 columns, with no JSON
  columns (contract files live on disk). Types behave the same on SQLite and
  PostgreSQL: `id` is `String(36)` (the canonical UUID string, not a native
  UUID); `status` is an enum of the SPECS section 3 states stored as VARCHAR
  + CHECK `ck_runs_run_status` (`create_constraint=True` explicitly: its
  default is False in SQLAlchemy 2.0); timestamps use `UtcDateTime` (naive
  UTC stored, aware UTC returned; the TZDateTime pattern from the SQLAlchemy
  docs), because SQLite keeps no timezone.
- 1A2 consistency rule: a `runs` row exists only if its `raw.csv` is complete
  on disk. Order: file (fsynced) -> flush -> commit. A flush failure means
  nothing was committed, so the directory is deleted. A commit failure has an
  unknown outcome, so the directory is kept; a directory without a row is
  garbage for the 8B retention cleanup. Both branches are tested.
- Alembic: run it from the repo root with
  `backend\venv\Scripts\alembic -c backend\alembic.ini <command>`. `env.py`
  reads `DATABASE_URL` through `Settings` (no URL in `alembic.ini`), or uses
  a connection passed by tests. `render_as_batch=True` because tests migrate
  SQLite. Migrations never import the models (the first one uses
  `sa.DateTime()` where the model has `UtcDateTime`). Tests: upgrade, no
  drift against the models (`compare_metadata`), the CHECK constraint name
  (autogenerate does not compare CHECKs), and downgrade.
- Tests never touch a real database: `tests/conftest.py` sets
  `DATABASE_URL=sqlite://`, and `create_app(settings, engine=...)` takes an
  injected in-memory engine.
- Launch decision (1A): the dev server runs from the REPO ROOT with
  `python -m uvicorn app.main:app --app-dir backend --reload`, the same two
  path entries as `pytest.ini` (root + `backend`). Starting it from
  `backend/` now fails with `No module named 'shared'`, which is intended.
  CLAUDE.md section 8 and README updated. pytest still works from both.
- 1A upload rules: checks run type -> size -> empty -> binary. The type check
  creates no run; any later rejection deletes the run directory. The file is
  copied in 64 KB chunks with a running byte count, never read whole.
  Limitation: FastAPI/python-multipart has already spooled the whole body
  before the handler runs, so an oversized upload is still received in full
  (to a temp file) before the 413; a request-size limit at the server or proxy
  belongs to 8B abuse guards.
- 1A decisions (Thach): endpoint first, DB in 1A2; SQLite for tests;
  header-only files rejected in 1B; NUL-byte check for binary files in 1A.
  Messages are English UI copy in `services/uploads.py`.
- F10 now also covers `npm run lint` in `frontend/` (approved by Thach).
- 0D frontend setup: one `.env` at the repo root for both apps. Vite reads it
  through `envDir: '..'`, and only `VITE_*` variables reach the browser.
  `VITE_API_BASE_URL` is in `.env.example` and must be in every local `.env`
  (without it the page says "not configured").
  `server.strictPort: true` so Vite never drifts off the port listed in
  `ALLOWED_ORIGINS`. Layout: `src/api/` (fetch + response checks),
  `src/components/`; tests next to the code (`*.test.ts(x)`, jsdom).
- 0D template changes: the current `create-vite` react-ts template has no
  `"strict": true` (added to both tsconfigs for F5) and ships oxlint (swapped
  for ESLint + typescript-eslint `strictTypeChecked` + react-hooks, as Thach
  asked). The config is `eslint.config.ts` (no plain .js), which needs the dev
  dependency `jiti`; ESLint's native TS loading is still behind an unstable
  flag. `npm run lint` uses `--max-warnings=0`. ESLint enforces F6 too:
  planted `any`, `@ts-ignore` and a reasonless `@ts-expect-error` were all
  errors.
- Floors now active: F5 (`npx tsc -b`), F6, Vitest in F1 (`npx vitest run` or
  `npm test`), W4 (`npm audit --audit-level=high`). `CONSTRAINTS.md` F10 still
  names only ruff; adding `npm run lint` in `frontend/` to F10 is a tightening
  (allowed by F11) for Thach to approve in a docs session.
- 0C2 design: `shared/` may not import the backend, so the registry does not
  read settings. The caller passes an absolute runs root (from 1A on, a
  service passes `settings.runs_dir`); a relative root raises `ValueError`.
  `config.py` anchors a relative `RUNS_DIR` to its existing `REPO_ROOT`, the
  only place that finds the repo root. `REPO_ROOT` was not moved into
  `shared/`, because `config.py` would then import `shared`, which is not
  on `sys.path` when uvicorn runs from `backend/` (see the Phase 1 launch
  note below).
- Registry API: `create_run(runs_root) -> NewRun(run_id, path)`, `run_dir`,
  `run_file` (the file need not exist; stages write to it). Only a canonical
  lowercase UUID is accepted as a run id (`InvalidRunIdError`, a
  `ValueError` -> 400 later), so an id from a URL can never climb out of
  `runs/` (SPECS section 11: never user-supplied paths); a well-formed id with
  no directory raises `RunNotFoundError` (a `LookupError` -> 404 later).
  Filenames must be bare names.
- Tests never touch the real `runs/`: `tests/conftest.py` sets `RUNS_DIR` to
  an absolute temp dir outside the repo, and a test in
  `tests/backend/test_config.py` fails if that changes. Registry tests use
  `tmp_path`.
- 0C rules, decided with Thach: stages may not import another stage, `app` /
  `backend`, or fastapi / starlette / sqlalchemy / alembic; a file directly in
  `stages/` (not in a stage) may import no stage, so it cannot become a back
  door; `contracts/` may import none of `stages`, `shared`, `app`,
  `backend`, the frameworks; `shared/` may import neither `stages` nor
  `app` / `backend`. `backend/app/` is walked but has no rule yet (a
  routers -> services rule could be added there later).
- How the guard works: the walker and the rules live in
  `tests/test_architecture.py` itself, so the F3 review of that file covers
  them. Stage ownership comes from the path (no list of stage names).
  Relative imports are resolved; `from stages import x` counts as importing
  `stages.x`; imports under `TYPE_CHECKING` or inside functions count;
  `importlib.import_module` / `__import__` count only with a literal name (a
  computed name cannot be resolved statically). `app.*` and `backend.*` are
  the same boundary, because `backend/` is on the path.
- Fixtures: `tests/architecture_fixtures/violations/` (18 files, one
  violation each, all listed in the test) and `clean/`. They are parsed,
  never imported, and are outside the four scanned roots; a test asserts
  that. A test also asserts that all four real roots are reached, so a typo
  in `SCAN_ROOTS` cannot silently scan nothing. F3 verified: an import
  planted in `stages/ingest/` and in `contracts/` failed the build, then was
  removed.
- 0B decisions (Thach): unknown fields are ignored (`extra="ignore"` on
  `ContractModel`, matching CONTRACTS section 10); strict AI-output checks
  stay in the stages (1C/1E/3B/4B). `report.json` layers are
  `dict[str, Any]` until 5A. Degraded AI in stages 3-4: the AI blocks are
  required keys with nullable values, all null or all filled; CONTRACTS
  sections 7, 8 and 10 and the SPECS section 10 error row were amended in
  place at `1.0` (no file existed yet), recorded in the SPECS change log.
- 0B conventions for later contract work: `_base.py` holds `ContractFile`
  (`schema_version` must be `1.x`, `generated_at` must carry a timezone) and
  the shared types (`Percent`, `UnitInterval`, `YearMonth`, ...). Enums are
  `Literal`s, only where the docs define one (AI_PIPELINE sections 5-6,
  plan `source`); everything else is `str`. Bounds only where definitional
  (counts >= 0, percentages of a whole, confidence, `low <= point <= high`,
  chart `len(x) == len(y)`); revenue, shares and return rates are unbounded
  because refunds can make them negative. Nullable fields are required keys
  (no default) so a dropped key never parses as `null`.
- Follow-ups found in 0B live in their owning sub-phase lines in section 5:
  1C (every profiled column exactly once), 2A/2C (zero denominators vs
  required numbers), 3A (insufficient-data decomposition), 4B (AI call when
  `ai_findings` is null), 5A (layer structure, "unavailable", `ai_calls`),
  1C (why the AI was unavailable: carried by `AIUnavailable`, logged, and
  maybe recorded in degraded files). Not addressed (run-model question, not a contract one): a
  re-run of stage 3 after stage 4 ran degraded leaves `forecast.json` stale.
- `pydantic==2.13.5` is now pinned in `backend/requirements.txt` (it was
  already installed as a FastAPI dependency; `contracts/` imports it
  directly). Pytest adds the repo root to the path, so `tests/contracts/`
  imports `contracts` without an install step.
- Wave 1 has no personas, so `.claude/agents/` does not exist yet;
  doubt-driven-development's mention of `agents/` is prose, not a link. Personas
  arrive with Wave 2 (test-engineer, code-reviewer) and Wave 4 (security-auditor).
- `CONSTRAINTS.md` exists at enforcement level "written only": the agent runs
  the checks at task end, Thach before committing. Not installed yet, each
  needing Thach's approval: `pytest-cov` + `diff-cover` (W1/W2; add
  `coverage.xml` to `.gitignore` then), `pip-audit` (W3), a project ruff config
  (F10). W4 (`npm audit`, from 0D) confirmed by Thach on 2026-09-19.
- The 8 open items from the SPECS UPDATE doubt review now live in their
  owning sub-phase lines in section 5, so they survive Notes rewrites: 0C
  (`app`/`backend` imports from `stages/`/`shared/`), 1A (binary renamed to
  `.csv`), 1C (`shared/ai_client.py` + F4 guard fixture), 5B (extend SEC-3 to
  CSV-derived text; SPECS first), 6A (size limit without a second source of
  truth), 8B (rate-limited run-state transition; trusted proxy, value set in
  9A), 9A (CORS trailing slash, Vercel preview domains).
- Local root folder is renamed by Thach manually to
  `C:\Users\Happy\Desktop\dataclarity` (Windows cannot rename a folder that
  Claude Code / VS Code / a terminal is using). A venv hardcodes its absolute
  path (`pyvenv.cfg`, `activate*`, every `Scripts\*.exe` launcher such as
  `uvicorn.exe`, `pytest.exe`, `pip.exe`), so after the rename `backend\venv` is
  recreated (same name `venv`) and requirements reinstalled.
- Claude Code history and memory are keyed by folder path: after the rename,
  `claude -c` in the new folder will not find old sessions. This section is the
  handover.
- Images in `design/mockups/*.png` may still show "CleanStock" as drawn text;
  they are binary Figma exports and are not edited here.
- 0A delivered: git repo (`main`), empty packages for `contracts/`, `stages/*`,
  `shared/`, `backend/app/{routers,services,models}`; `create_app(settings)`
  factory + `GET /health` in `routers/health.py`; `config.py` (pydantic-settings,
  every variable required, no defaults, `.env` read from repo root,
  `hide_input_in_errors` so the API key never lands in logs); CORS from
  `ALLOWED_ORIGINS` (comma-separated); `pytest.ini` at repo root.
- `.env` lives at the REPO ROOT only (not `backend/`); created with dev values,
  `ANTHROPIC_API_KEY` left as a placeholder for Thach. First startup failure
  (8 missing fields) was simply the missing `.env`, not a path bug.
- Local Python is 3.14 (via `py`); `python` on PATH is the Microsoft Store stub.
  `backend/requirements.txt` is pinned to versions verified on 3.14.
- `pytest` works from the repo root AND from `backend/` (CLAUDE.md section 8).
  pytest honours `testpaths` only when invoked from the rootdir, so the root
  `conftest.py` redirects a bare run from a subdirectory to `testpaths`; runs
  inside `tests/` or with explicit paths are untouched. `pytest.ini` adds `.`
  and `backend` to the path.
- `tests/conftest.py` forces fake env values before `app.main` is imported, so
  the suite never reads the real `.env` or API key.
- Not created on purpose: `runs/` (created on the first run through
  `shared/run_registry.py`; gitignored).
- pytest shows 1 DeprecationWarning from `starlette/testclient.py` (anyio
  renamed `BlockingPortal`). Third-party, not our code; ignore until starlette
  updates. Do not count it as a new lint warning.
- Running a command via `!` in Claude Code uses Bash: use forward slashes
  (`backend/venv/Scripts/python -m pytest`), backslashes get stripped.
- No Python linter is configured yet (a global ruff config flags `app` imports
  as third-party); consider adding a ruff config when Thach approves. The
  frontend has ESLint since 0D.
- Architecture decision made this session: ONE repo with five independent stage
  packages and contract files between them, instead of five separate repos.
  Boundary enforced by `tests/test_architecture.py` (Phase 0C). Splitting into
  separate repos later stays possible precisely because of that boundary.
- Figma frames are being designed by Thach in parallel. Frontend phases (6A-6F)
  must not start until `docs/FIGMA_DESIGN_NOTES.md` has real node ids.
- No auth in v1; public demo protected by rate limits and retention cleanup.
- Forecasting (Phase 4A) deliberately uses interpretable statistics, not ML
  models, so every number in the report can be explained in an interview.

## 13. Definition of Done for every sub-phase

The standing bar every sub-phase clears before it is ticked. It adapts
`.claude/references/definition-of-done.md` to this project. `CLAUDE.md` section 7
is canonical: this checklist links to its items and adds only the items the
reference contributes (runtime verification, contract discipline, decision
records). If the two ever differ, `CLAUDE.md` section 7 applies. The **DoD:** line
under each phase in section 5 is that phase's acceptance criteria, checked in
addition to this list.

- [ ] Scope: only the sub-phase's items are implemented (`CLAUDE.md` section 7
      item 1)
- [ ] Tests written and passing: new code in `stages/` or
      `backend/app/services/` has tests with hand-checked expectations
      (`CLAUDE.md` section 7 item 3 and `CLAUDE.md` section 5); every suite
      passes (`CLAUDE.md` section 7 item 2)
- [ ] Constraints respected: every Floor row in `CONSTRAINTS.md` passes,
      including no new lint warnings (`CLAUDE.md` section 7 item 4; checked by
      command once a ruff config exists); Warn rows are reported to Thach
- [ ] Verified at runtime where the sub-phase delivers something runnable: a
      stage via `python -m stages.<name> --run <run_id>`, an endpoint via the
      running API, not only via tests. Run with a fake `ANTHROPIC_API_KEY` so
      every AI step takes the degraded path; real tokens are spent only when
      Thach asks
- [ ] Contracts: any contract change follows `docs/CONTRACTS.md` section 10
- [ ] Decision records: from Phase 2 on, an architectural decision worth
      keeping gets an ADR in `docs/adr/`
- [ ] Current Status updated: checklist ticked and section 12 rewritten with the
      file-editing tool (`CLAUDE.md` section 7 item 5; section 6 of this file)
- [ ] Key decisions explained to Thach in Vietnamese (`CLAUDE.md` section 7
      item 6)
- [ ] Commit proposed: exact `git add`, `git commit -m "..."` and `git push`
      commands given to Thach ("Skill precedence" in `CLAUDE.md`)

Reference items that do not apply in v1: observability beyond basic logging
(`docs/SKILLS.md` section 4), feature flags (none in this project), and a
rollback path (only for the Phase 9 deploy, via the Wave 4 skills). "Human
review before merge" is met because Thach reviews and types every git command.
