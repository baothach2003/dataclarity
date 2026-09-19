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
- [ ] 0B `contracts/` package: Pydantic models for all 6 contract files per
      `docs/CONTRACTS.md`, with validation tests
- [ ] 0C `tests/test_architecture.py`: AST-based test failing on cross-stage
      imports, and on any import of `app` or `backend` from `stages/` or
      `shared/` (backs SPECS SEC-4); run registry helper (`runs/<run_id>/`
      creation, path resolution)
- [ ] 0D Frontend skeleton: Vite + React + TS, `/health` call, CORS via env var
- **DoD:** both apps run; architecture test passes; contracts importable

### Phase 1 - Stage 1 Collect (backend)
- [ ] 1A Upload endpoint `POST /api/runs` (multipart, `MAX_UPLOAD_MB` cap and
      type validation per SPECS section 11 SEC-1, including the 50MB ceiling
      check at startup), file stored under `runs/<run_id>/raw.csv`, `runs` DB
      row. Decide how a binary file renamed to `.csv` is rejected: it can
      decode as latin-1 and pass SEC-1 today
- [ ] 1B `stages/ingest/profiling.py`: pure pandas per-column + dataset stats ->
      `profile.json` contract. Unit tests with fixture CSVs
- [ ] 1C `shared/ai_client.py` (`docs/AI_PIPELINE.md` section 3) with the
      real-API guard fixture that activates CONSTRAINTS F4, then
      `stages/ingest/ai_schema.py`: AI stage A (schema inference) via the AI
      client, validated, retry-once, degraded mode. Tests with mocked AI
- [ ] 1D `stages/ingest/transforms.py`: the full transform catalog
      (`docs/AI_PIPELINE.md` section 6) as pure functions + change log. One test
      per transform including edge cases
- [ ] 1E `stages/ingest/ai_plan.py`: AI stage B (cleaning plan) + catalog/legality
      validation. Tests with mocked AI
- [ ] 1F `stages/ingest/cleaning.py`: preview (sample) and execute (full) engines
      -> `cleaned.csv` + `cleaning_report.json`. Tests
- [ ] 1G Endpoints wiring: `/analyze-schema`, `/plan`, `/preview`, `/execute` per
      `docs/SPECS.md` section 8. Tests with mocked AI
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
      customers, AOV, return rate. Tests with hand-calculated expected values
- [ ] 2B `metrics_customers.py`: RFM scoring + segment assignment (Champions,
      Loyal, At-risk, Hibernating, New). Tests
- [ ] 2C `metrics_products.py`: Pareto concentration, top/bottom movers,
      velocity + stockout projection. Tests
- [ ] 2D Assemble `metrics.json` contract + `POST /api/runs/{id}/analyze`. Tests
- **DoD:** numbers in `metrics.json` verified by hand against the fixture data

### Phase 3 - Stage 3 Diagnose
- [ ] 3A `decomposition.py`: revenue = customers x frequency x AOV, period-over-
      period attribution, contribution by segment/country/product group. Tests
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
      (arithmetic shown), how to measure. Validated. Tests with mocked AI
- [ ] 4C Assemble `forecast.json` + `POST /api/runs/{id}/predict`. Tests
- **DoD:** every recommendation cites a number that exists in the inputs; a
  manual review finds no fabricated figures

### Phase 5 - Stage 5 Report
- [ ] 5A `builder.py`: assemble `report.json` (3 layers: numbers, causes,
      actions) from all prior contracts. Tests
- [ ] 5B `html_report.py`: self-contained HTML with embedded Plotly charts;
      downloadable. Tests on structure, not pixels, including AI text escaped
      (SPECS SEC-3). Owner of the open decision to extend SEC-3 to text taken
      from the uploaded CSV (column names, product/category values): update
      SPECS first, then 5B and the Phase 6 screens follow it
- [ ] 5C `POST /api/runs/{id}/report` + download endpoints. Tests
- [ ] 5D `python -m stages.report --run <id>` CLI path verified (proves stage
      independence)
- **DoD:** the HTML report is readable standalone and matches the contract data

### Phase 6 - Frontend
- [ ] Install skills Wave 3 (see docs/SKILLS.md)
- [ ] 6A Upload page + analyzing states (SPECS 4.1); decide how the
      client-side size check learns `MAX_UPLOAD_MB` without a second source of
      truth for the limit
- [ ] 6B Review screen part 1: column table with editable type / mapping / action
      (AI rationale rendered escaped, SPECS SEC-3)
- [ ] 6C Review screen part 2: before/after preview + confirm/cancel/reset
- [ ] 6D Results page: cleaning summary + downloads
- [ ] 6E Insights page: KPI cards, diagnosis panel, recommendations list (AI
      text rendered escaped, SPECS SEC-3)
- [ ] 6F Dashboard page: charts + low-stock table + report download
- **DoD:** a non-technical user completes upload -> report without instructions

### Phase 7 - Import and Persistence
- [ ] 7A Alembic migrations for `products`, `transactions`, `runs`
- [ ] 7B Import service: approved clean data -> canonical tables, upsert by
      SKU/name, import summary with skipped rows and reasons. Tests
- [ ] 7C Dashboard endpoints read from DB (not from run files). Tests
- **DoD:** dashboard numbers match the source file, hand-checked

### Phase 8 - Hardening
- [ ] 8A Edge cases from SPECS section 10 (empty, header-only, non-UTF8, wrong
      delimiter, all-null column, non-inventory data, `MAX_UPLOAD_MB` boundary)
- [ ] 8B Abuse guards: rate limits on uploads (SPECS section 11 abuse guards)
      and on every AI endpoint (SEC-2), each from its own required env var;
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

**Phase in progress:** 0A closed (committed `b790448`, pushed to
https://github.com/baothach2003/dataclarity). Three tooling/docs sessions since,
no application code: the rename CleanStock -> DataClarity (`4d62960`), the
SKILLS SETUP session (`1178c1b`, Wave 1 of `addyosmani/agent-skills` in
`.claude/skills/`, references in `.claude/references/`), and the SPECS UPDATE
session "Integrate engineering skills" (this one, 2026-09-19). This session
created `CONSTRAINTS.md` (Floor F1-F11 blocks, Warn W1-W4 reports; coverage
>= 80% of changed lines in `stages/` and `backend/app/services/`, project
coverage measure-and-hold, `pip-audit`, `npm audit` from 0D, 90 s task-end
budget), added SPECS section 11 SEC-1 to SEC-5 and the section 13 change log,
the CLAUDE.md "Skill usage" section, section 13 of this file (Definition of
Done), the Phase 2 ADR item, and wording updates in 1A, 1G, 5B, 6B, 6E, 8A, 8B.
Full detail: `docs/SPECS.md` section 13. 3 tests pass, 0 skipped.
**Next step:** Phase 0B (`contracts/` Pydantic models per `docs/CONTRACTS.md`,
with validation tests).
**Notes:**
- Wave 3 goes at Phase 6, not 0D (0D is only a Vite skeleton calling
  `/health`). Now recorded durably in the `docs/SKILLS.md` Wave 3 heading.
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
- Not created on purpose: `frontend/` (Vite scaffolding in 0D wants an empty
  directory) and `runs/` (created by the run registry in 0C).
- For 0C: `RUNS_DIR` is relative to the working directory today; the run
  registry should resolve it against the repo root. For Phase 1: when uvicorn
  runs from `backend/`, the repo root is not on `sys.path`, so services cannot
  import `stages`/`contracts` yet - decide how to launch (e.g. from root with
  `--app-dir backend`) before 1A.
- pytest shows 1 DeprecationWarning from `starlette/testclient.py` (anyio
  renamed `BlockingPortal`). Third-party, not our code; ignore until starlette
  updates. Do not count it as a new lint warning.
- Running a command via `!` in Claude Code uses Bash: use forward slashes
  (`backend/venv/Scripts/python -m pytest`), backslashes get stripped.
- No project linter is configured yet (a global ruff config flags `app` imports
  as third-party); consider adding a ruff config when Thach approves.
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
