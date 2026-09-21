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
Rationale: hard module boundaries and the option to split into separate repos
later, without paying the version-sync cost of 5 repos today.

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
- [ ] 1F `stages/ingest/cleaning.py`: preview (sample) and execute (full) engines
      -> `cleaned.csv` + `cleaning_report.json`. Tests. Emit the SPECS
      section 10 `encoding_fallback` warning in `cleaning_report.warnings`
      when `profile.json` has `encoding_used: "latin-1"` (profile.json has
      no warnings field; 1B only records the encoding). Carried over from 1E, the
      things a plan check cannot see because they depend on the data (AI_PIPELINE
      section 11): `parse_datetime` on a column of mixed UTC offsets fails (the
      detectors read them as UTC, but writing UTC into the data would move
      dates: decide with Thach whether to convert, keep the wall-clock date, or
      flag the column); a `format` with a year that matches no cell flags every
      date; `cast_type` to integer beyond int64 is flagged (not raised);
      `standardize_categories` keys absent from the data; `dayfirst` flips ISO
      cells too. Also decide what happens to a plan that drops a required field
      or a business-key column with `drop_column` (the legality matrix allows
      it; SPECS 4.2 blocks Confirm until the required fields are mapped)
- [ ] 1G Endpoints wiring: `/analyze-schema`, `/plan`, `/preview`, `/execute` per
      `docs/SPECS.md` section 8. Tests with mocked AI. Decide the code for a
      malformed request (e.g. no `file` part): FastAPI's default 422
      `{"detail": [...]}` breaks the section 8 error envelope, and section 10
      has no code for it. The same holds for an unexpected server error (e.g.
      the database is down during `POST /api/runs`): today it is FastAPI's
      plain 500, outside the envelope. Map `stages.ingest.profiling`
      errors by their `.code` (`EmptyCsvError` -> EMPTY_FILE, `CsvParseError`
      -> PARSE_FAILED, both 400) when the profile step is wired to an endpoint.
      Wire schema inference: build the client with
      `AIClient.from_api_key(settings.anthropic_api_key...)` and pass
      `settings.model_reasoning`; map `AIUnavailable` to AI_UNAVAILABLE (200 +
      flag, its `reason` code in `details`); send `domain_confidence < 0.5` to
      the NOT_INVENTORY path (AI_PIPELINE 9.4); keep the run's `RetryBudget`
      across the schema and plan steps (it spans the run, not one request).
      The plan step is `ai_plan.propose_plan_run` (same `AIUnavailable`
      mapping); it raises `FileNotFoundError` for a missing input and
      `ValueError` when `schema_inference.json` no longer matches
      `profile.json` (map both). The `plan_final.json` validation reuses
      `transform_catalog.illegality_reason` and `transform_params.params_problem`,
      not the AI-specific coverage and retry-message code; an alternative
      carries a name only, so the UI supplies its params when it is picked
- **DoD:** full stage 1 works end-to-end via API only (no UI), verified on a
  deliberately messy fixture CSV

### Phase 2 - Stage 2 Analyze
- [ ] Install skills Wave 2 (see docs/SKILLS.md)
- [ ] Create `docs/adr/` (own docs session, after the Wave 2 install, using
      documentation-and-adrs) with: ADR-0001 one repo with five independent
      stage packages; ADR-0002 pandas computes, AI only interprets; ADR-0003
      model choice per task (reasoning model vs bulk model via `MODEL_REASONING`
      / `MODEL_BULK`, never the largest model at runtime; no model ids in the
      ADR). ADRs hold the "why"; existing docs keep the rule and link to the ADR
- [ ] 2A `metrics_core.py`: revenue by period, MoM growth, orders, active
      customers, AOV, return rate. Tests with hand-calculated expected values.
      Zero denominators (`revenue_change_pct` with no previous revenue, `aov`
      and return rate with no orders) need a contract decision first: the 1.0
      contract requires a number there
- [ ] 2B `metrics_customers.py`: RFM scoring + segment assignment (Champions,
      Loyal, At-risk, Hibernating, New). Tests
- [ ] 2C `metrics_products.py`: Pareto concentration, top/bottom movers,
      velocity + stockout projection. Tests. `days_to_stockout` at zero
      velocity needs a contract decision first (same reason as 2A)
- [ ] 2D Assemble `metrics.json` contract + `POST /api/runs/{id}/analyze`. Tests
- **DoD:** numbers in `metrics.json` verified by hand against the fixture data

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
      answer must repeat names exactly
- [ ] 8B Abuse guards: rate limits on uploads (SPECS section 11 abuse guards)
      and on every AI endpoint (SEC-2), each from its own required env var;
      a request-body size limit so an oversized upload is refused before it
      is fully received (today 1A returns 413 only after python-multipart has
      spooled the whole body); the retention cleanup also deletes run
      directories that have no `runs` row (left by a commit with an unknown
      outcome, see 1A2);
      the run-state transition for a rate-limited AI step (SEC-2); the
      trusted-proxy setting that yields the client IP (SEC-2; 9A sets the
      Render value); AI call budget per run; retention
      cleanup job; startup `ALLOWED_ORIGINS` checks per SEC-5;
      `DATABASE_URL` handled as a secret so it never reaches logs (SEC-4)
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

## 12. Current Status

**Phase in progress:** Phase 1. 1E closed 2026-09-21 (uncommitted until Thach
commits). Earlier: Phase 0 (0A `b790448` ... 0D `24307c3`), 1A (`83eccbf`), 1A2
(`ee5d7c9`), 1B (`f9b12d7`), 1C (`3d5d9d7`), 1D (`8ed0a19`). 1E delivered the
cleaning-plan step: `stages/ingest/ai_plan.py` (reads `profile.json` and
`schema_inference.json`, calls the AI, writes `plan_proposed.json`),
`plan_checks.py` (every check on the answer), `transform_params.py` (plan-time
param validation), `issue_recount.py` (pandas replaces the AI's issue counts),
the business key in `issue_counts.py`, `ai_input.build_plan_variables`, a
rewritten `prompts/cleaning_plan.md`, and a lone-surrogate guard in
`shared/ai_client.py`. pytest 1383 passed from the repo root and from
`backend/`, 0 skipped; Vitest 9 passed; `npx tsc -b` and `npm run lint` clean;
`npm audit` not run (needs the network).
**Next step:** Phase 1F (`stages/ingest/cleaning.py`, the preview and execute
engines). Its line above lists what 1E leaves to it.
**Notes:**
- 1E decisions (Thach): pandas overwrites the AI's count for every code the
  profile holds no figure for, with no retry on a difference; a count of 0
  removes the issue (profile-held codes too); `pct` stays null for computed
  codes; the business key is sku (else product_name) + transaction_date +
  transaction_type when mapped, and with no key the count is 0 and
  `flag_duplicate_keys` cannot be proposed. The cross-model second opinion was
  offered in every review cycle and skipped each time.
- 1E choices made without a question, for Thach to veto: the plan input carries
  each column's `legal_actions`, the `dataset_legal_actions` and the
  `business_key`, and leaves out the schema result's `examples` and
  `domain_reasoning`; alternatives of a dataset action are dataset actions only
  (the CONTRACTS example listed `flag_only`, which needs a column, and was
  corrected); repeated alternatives and the chosen action are tidied away, not
  rejected; an omitted or null `params` / `alternatives` / `rationale` defaults,
  so a slip on one entry does not hide the rest; the `detail` sentence of both
  dataset issues is generated from the figures (I first kept the AI's
  `duplicate_rows` sentence, and the review found the AI's own number in it);
  the retry message states the legal-actions hint once, lists dataset problems
  first and stays within 3500 characters, saying how many problems it left out;
  a `parse_datetime` format needs a year (or is `ISO8601`); an `impute_constant`
  value may not be empty or a word profiling reads as missing.
- 1E review (doubt-driven, three cycles, fresh-context reviewers, cross-model
  skipped each time). Cycle 1 (3 high): a plan could drop a column its own
  `flag_duplicate_keys` needs; a malformed date `format` passed and crashed at
  execution; a 400-digit `k` raised `OverflowError` past the retry. Cycle 2
  (11, none high): a lone-surrogate action name crashed the retry request;
  omitted fields hid other problems; alternatives were rejected before being
  tidied. Cycle 3 (12, one high): a lone surrogate in free text passed every
  check and crashed the contract write, in the schema step too; fixed once in
  `shared/ai_client.py`. Everything actionable is fixed with a test, and the
  fixes made after cycle 3 (the client guard and the cycle-3 items) were not
  reviewed again: no fourth cycle, decided by Thach (2026-09-21), because the
  skill stops at three and those fixes are mechanical and lower risk.
- Defects in earlier code that 1E found and fixed: `column_kinds.as_dates`
  raised on mixed UTC offsets (also in the 1C sample-row path, before any AI
  call); the date counters converted a whole text column (about 4 s per 200k
  rows per code) and now probe 500 cells first; `cast_type` to integer raised
  beyond int64; `near_duplicate_labels` deleted combining marks (decomposed
  Vietnamese, Hindi, Thai) and grouped labels made only of symbols. One existing
  test changed: `test_a_null_pct_is_accepted` had the AI claim a case issue the
  data did not have, so its CSV now has one (the assertion is unchanged).
- Accepted trade-offs (each is in AI_PIPELINE section 11 or a docstring): an
  impossible issue count (more than the rows) still uses the retry, because
  relaxing it would weaken two 1C tests; issue counts describe the raw file, so
  the cleaned file can differ; rows with a missing key part count as sharing the
  key, as `flag_duplicate_keys` marks them; a pct within 0.1 is kept as the AI
  wrote it, and `examples` / `domain_reasoning` are not number-checked;
  `near_duplicate_labels` ignores punctuation as its 1D definition says, so
  "A+" and "A-" are near-duplicates (say if that should change); a column that
  only turns into dates after 500 rows is treated as text, and a hostile CSV
  that opens with 500 dates can still cost about 4 s per date code; the recount
  has no cost bound (a 300,000-row column of unique text costs about 3 s over
  all 11 codes, up to 25 columns); an answer wrong in every column reports its
  first problems and how many are left.
- Technical debt: `stages/ingest/transforms.py` is 322 lines, over the ~300 of
  CLAUDE.md section 5 (it was 317 at the end of 1D). Left as it is by decision
  (Thach, 2026-09-21); split it (say, the casts and flags into their own module)
  when 1F next touches it, not before.
- The plan prompt met the real model once (2026-09-21, Thach ran a throwaway
  script on a 25-row CSV with planted dirt, two real calls, a few cents).
  Reported result: no retry was needed in either call; no imputation of a
  required field; `flag_duplicate_keys` used exactly SKU / Date / Type; every
  rationale cited a figure that was in the input. pandas gave `Qty` a
  `near_duplicate_labels` count of 1 ("-2" vs "2" differ only by punctuation)
  and the AI left it out of the plan, which is sensible but luck-dependent: the
  "A+ vs A-" question stays open, not urgent. One 25-row file is a smoke test,
  not coverage: a wider or dirtier file, or the golden-path test in Phase 5,
  would say more.
- Tooling: heredocs through the Bash tool collapse `\\` to `\`, so a script
  that writes escape sequences (`\ud800`, regexes) must be written with the
  file-writing tool, not a heredoc.
- 1D found three readings of `AI_PIPELINE` section 6 and Thach decided all
  three in the same session; section 6 was rewritten so none of them can be
  read two ways again (`docs/SPECS.md` change log, 2026-09-20). (a)
  `impute_constant` is categorical / text / boolean, per the legality matrix;
  the table's "Applies to: any" was the stale half and now matches. (b)
  `trim_whitespace` and `normalize_case` also apply to `identifier`: they
  standardize how a value is written and invent nothing, so a padded or
  mis-cased SKU is cleanable. Imputation stays illegal on an identifier, and
  `standardize_categories` was deliberately not widened - merging labels would
  collapse two ids into one. A plan that re-cases an identifier should say so
  in its rationale, because a case-sensitive source system may keep "ab-1" and
  "AB-1" apart. (c) The required-canonical-field rule forbids the four
  imputation actions only; every other action the semantic type allows stays
  legal, or `transaction_date` could never be parsed. The whole matrix is
  walked against a required field in `test_transform_catalog.py`.
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
