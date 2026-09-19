# DataClarity

Turn a messy inventory/sales CSV into a decision-ready report through a five-stage
pipeline: **Collect -> Analyze -> Diagnose -> Predict -> Report**.

Stage 1 is interactive: AI infers the schema and proposes a cleaning plan, the
user reviews and edits it with a before/after preview, then approves. Stages 2-5
run on the approved clean data and produce KPIs, a root-cause diagnosis, an
interpretable forecast with ranked recommendations, and an HTML report.

## Design principle

**pandas computes, AI interprets.** Every number in the final report comes from a
tested pandas function. The AI never sees the full file, never transforms data,
and never calculates a figure that appears in the output. It reads bounded
summaries and produces explanations, proposals and narrative, all validated
against strict schemas and a whitelisted action catalog.

## Architecture

One repository, five independent stage packages communicating only through JSON
contract files (`docs/CONTRACTS.md`). A stage may never import another stage;
`tests/test_architecture.py` enforces this. Each stage also runs standalone:

```
python -m stages.analyze --run <run_id>
```

## Documentation

| File | Content |
|---|---|
| `PROJECT_PLAN.md` | Phase-by-phase roadmap and current status |
| `CLAUDE.md` | Repo rules (architecture, conventions, what not to do) |
| `CONSTRAINTS.md` | Measurable quality bar: checks, thresholds, exceptions |
| `docs/SPECS.md` | Functional spec: flows, screens, API, edge cases |
| `docs/CONTRACTS.md` | JSON schemas passed between stages |
| `docs/AI_PIPELINE.md` | AI steps, transform catalog, failure handling |
| `docs/FIGMA_DESIGN_NOTES.md` | Design frames, node ids, tokens |

## Run locally

One `.env` at the repo root serves both apps: copy `.env.example` to `.env` and
fill in the values. The frontend reads only the `VITE_*` variables from it.

Backend (http://localhost:8000):

```bash
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Frontend (http://localhost:5173, must match `ALLOWED_ORIGINS`):

```bash
cd frontend
npm install
npm run dev
```

The page shows `Backend: ok` when the two apps can reach each other. Checks:
`pytest` from the repo root; `npm test`, `npm run lint` and `npx tsc -b` in
`frontend/`.

## Status

See `PROJECT_PLAN.md` section 12.
