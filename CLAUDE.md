# DataClarity - Project Instructions

Persistent context for Claude Code. Read fully before starting any task in this repo.

## 1. What this project is

A web app that turns a messy inventory/sales CSV into a decision-ready report
through five stages: **Collect -> Analyze -> Diagnose -> Predict -> Report**.
Stage 1 is interactive (AI proposes a cleaning plan, the user edits and approves);
stages 2-5 run on the approved clean data.

Roadmap and session rules: `PROJECT_PLAN.md` (re-read section 12 every session).
Functional source of truth: `docs/SPECS.md`. Stage input/output schemas:
`docs/CONTRACTS.md`. AI internals: `docs/AI_PIPELINE.md`. Frontend must follow
`docs/FIGMA_DESIGN_NOTES.md`. Measurable quality bar: `CONSTRAINTS.md`. If this
file conflicts with those, stop and reconcile with Thach - never silently pick
one.

## 2. Tech stack (do not deviate without asking)

- Python 3.11+, FastAPI, pandas, SQLAlchemy + Alembic, PostgreSQL
- statsmodels or pandas rolling statistics for forecasting - no ML frameworks
- Anthropic API; model ids from config/env only. Runtime: `claude-sonnet-5`
  (reasoning steps), `claude-haiku-4-5` (bulk cheap tasks)
- React + Vite + TypeScript (no plain .js), Recharts
- pytest / Vitest; AI is ALWAYS mocked in tests
- No Docker, no Celery, no Polars/Spark, no auth in v1. Files cap at 50MB and
  synchronous processing is fine. Do not add infrastructure "for scale" unasked

## 3. Architecture decisions (already made - do not re-litigate)

### 3.1 Stage isolation is the most important rule in this codebase
Each stage package (`stages/ingest`, `analyze`, `diagnose`, `predict`, `report`)
may import ONLY from: the standard library, third-party packages, and
`contracts/`. **A stage must never import from another stage.** Data flows
between stages exclusively through contract JSON files in `runs/<run_id>/`,
whose schemas live in `docs/CONTRACTS.md` and whose Pydantic models live in
`contracts/`. `tests/test_architecture.py` parses imports and fails the build on
any violation - treat a failure there as a blocker, never as a test to relax.

Why: hard boundaries keep each stage independently testable and replaceable, and
leave the door open to splitting into separate repos later without the version
sync cost of doing it today.

### 3.2 pandas computes, AI interprets
- The AI never receives raw file contents beyond the bounded sample defined in
  `docs/AI_PIPELINE.md` (max 30 rows, profile truncated).
- The AI never transforms data and never computes a KPI. Every number in the
  final report comes from a tested pandas function.
- AI output is untrusted input: validate against Pydantic schemas, reject any
  action outside the transform catalog, retry once, then degrade gracefully.

### 3.3 The user is the final authority (stage 1)
Nothing is executed until the user confirms the plan. The execute endpoint runs
exactly the submitted (user-edited) plan, never the AI's original proposal, and
the change report records what actually ran.

### 3.4 Backend layering
`routers/` -> `services/` -> `models/`. Routers hold no business logic. Backend
services ORCHESTRATE stages (call them, move contract files, persist status);
they never re-implement stage logic. Stage packages stay framework-free: no
FastAPI, no SQLAlchemy imports inside `stages/`.

### 3.5 Migrations from day one
All schema changes go through Alembic. Never drop/recreate tables.

## 4. Folder structure (target)

```
dataclarity/
├── CLAUDE.md  PROJECT_PLAN.md  CONSTRAINTS.md  KICKOFF_PROMPT.md  README.md
├── docs/       SPECS.md  CONTRACTS.md  AI_PIPELINE.md  FIGMA_DESIGN_NOTES.md
├── prompts/    schema_inference.md  cleaning_plan.md  root_cause.md  strategy.md
├── contracts/  profile.py  cleaning.py  metrics.py  diagnosis.py  forecast.py
│               report.py  __init__.py
├── stages/
│   ├── ingest/    profiling.py  ai_schema.py  transforms.py  ai_plan.py
│   │              cleaning.py  __main__.py
│   ├── analyze/   metrics_core.py  metrics_customers.py  metrics_products.py
│   │              __main__.py
│   ├── diagnose/  decomposition.py  ai_root_cause.py  __main__.py
│   ├── predict/   forecast.py  ai_strategy.py  __main__.py
│   └── report/    builder.py  html_report.py  __main__.py
├── shared/        ai_client.py  run_registry.py   # infrastructure, not logic
├── backend/app/   main.py  config.py  routers/  services/  models/
├── frontend/src/  api/  pages/  components/  types/
├── runs/          # gitignored
└── tests/         test_architecture.py  + per-stage test packages
```

Note: `shared/ai_client.py` is infrastructure (HTTP + validation + retry), not
analysis logic. Stages may import it. It must contain zero business rules.

## 5. Coding conventions

- Type hints everywhere; Pydantic v2 for every contract and API payload
- TS strict mode; no `any` without a comment justifying it
- Components `PascalCase.tsx`; Python files `snake_case.py`
- Split any file over ~300 lines
- Every new function in `stages/` or `backend/app/services/` needs a unit test in
  the same session; transforms and metrics additionally need edge-case tests
  (empty df, single row, all-null column, zero denominator)
- Every metric function must be verifiable by hand: the test asserts a
  hand-calculated expected value, not just "no exception"
- Comments explain why, not what
- Secrets only via `.env`; `.env.example` documents required variables
- English everywhere in the repo, including UI copy

## 6. What NOT to do

- Do not import one stage from another (see 3.1)
- Do not import FastAPI or SQLAlchemy inside `stages/`
- Do not send full file contents to the AI, or exceed the bounded sample
- Do not let AI output skip Pydantic validation or the action catalog whitelist
- Do not let the AI compute or estimate any number that appears in the report
- Do not execute a cleaning plan without explicit user confirmation
- Do not hardcode model ids, CORS origins, thresholds, or file paths
- Do not call the real Anthropic API from tests
- Do not start frontend phases before FIGMA_DESIGN_NOTES.md has real node ids
- Do not add features outside the current sub-phase without asking Thach
- Do not commit `runs/`, `.env`, or any uploaded data

## 7. Definition of Done (per sub-phase)

1. Only the sub-phase's scope is implemented, nothing more
2. `pytest` passes, including `tests/test_architecture.py`
3. New code in `stages/` or `services/` has tests with hand-checked expectations
4. No new lint warnings
5. `PROJECT_PLAN.md` checklist + section 12 updated with the file-editing tool
6. Key decisions explained to Thach in Vietnamese in chat

## 8. Commands

```bash
# backend: the venv lives in backend/, but the server runs from the REPO ROOT
# so `app` (via --app-dir backend) and stages/, contracts/, shared/ (via the
# root on sys.path) are all importable - the same paths pytest.ini sets
cd backend && python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cd ..
python -m uvicorn app.main:app --app-dir backend --reload
pytest    # from the repo root or from backend/

# run a single stage standalone (proves stage independence)
python -m stages.analyze --run <run_id>

# frontend
cd frontend && npm install && npm run dev && npm test
```

## Skill precedence
- Rules in this file override any installed skill (see docs/SKILLS.md).
- `.claude/docs/agents.md` is the upstream agent-skills bundle's own general
  background reading on how personas/skills/commands compose (e.g. its `/ship`
  fan-out example, Agent Teams). It is reference material, not a DataClarity
  rule. Never apply anything from it that conflicts with this file - agent
  committing/pushing on its own, multi-task autonomous fan-out, scope beyond
  the current checklist item, or any other conflict with sections 1-11 or this
  section. This file always wins over it, the same as over any installed skill.
- Never run git commit or git push. Propose the message; Thach types the commands.
- At the very end of EVERY session (any phase, sub-phase or tooling session), give
  Thach the exact, copy-pasteable `git add ...`, `git commit -m "..."` and
  `git push` commands, with the full proposed commit message spelled out. Never
  assume he remembers the convention or will ask for it.
- One sub-phase per session. Never start the next task without Thach's approval.
- Never skip, delete or weaken a test to make it pass. tests/test_architecture.py may be created (Phase 0C) or extended to cover new boundaries, but never relaxed to make a build pass.

## Skill usage
Read `CONSTRAINTS.md` before writing code.

| Moment in the session | Skill |
|---|---|
| Session start | context-engineering |
| Implementing a task | incremental-implementation + test-driven-development |
| Writing code against a library or SDK | source-driven-development |
| Stage 3 or stage 4 logic, or any contract change | doubt-driven-development |
| A test fails, a build breaks, or behaviour is unexpected | debugging-and-error-recovery |

What each installed skill is for, and when each wave is installed:
`docs/SKILLS.md`.
