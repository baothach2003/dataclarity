# DataClarity

Turn a messy inventory/sales CSV into a decision-ready report through a five-stage
pipeline: **Collect -> Analyze -> Diagnose -> Predict -> Report**.

Stage 1 is interactive: AI infers the schema and proposes a cleaning plan, the
user reviews and edits it with a before/after preview, then approves. Stages 2-5
run on the approved clean data and produce KPIs, a root-cause diagnosis, an
interpretable forecast with ranked recommendations, and an HTML report.

## Scope of v1

v1 analyses sales, not inventory. Revenue, orders, customers, products and
their diagnosis come from the file's sale, return and discount lines; stock
figures (velocity, days to stockout, low stock) read "not supported in v1"
on every file, because a stock balance needs a stock ledger the export rarely
carries and a figure that can be wrong is worse than none.

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

Backend (http://localhost:8000). The server runs from the repo root, so the
backend can import the shared `stages/`, `contracts/` and `shared/` packages:

```bash
cd backend
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt
cd ..
python -m uvicorn app.main:app --app-dir backend --reload
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

## Known limitations

v1's foundational definitions - what a line, an order, a customer, a product,
a date and a period are, and how text is read - are frozen (`CLAUDE.md` 3.6).
A case they do not handle is recorded as a known limit rather than patched:
the full list, with how each was found, is `PROJECT_PLAN.md` item 8D. The
main ones:

- **Stock figures are not supported.** v1 analyses sales, not inventory.
- **When the data cannot tell two meanings apart, v1 does not guess.** It
  keeps one reading, reports the lines and money involved, and shows a note
  beside the figures they affect - for example, a return booked as stock
  received, or a refund that cannot be told from a coupon at a negative
  price (`docs/LINE_TAXONOMY.md` section 0).
- **No verdict on whether a month was unusual.** A month is compared with
  the same month a year earlier; the file rarely holds enough years for a
  robust verdict (`docs/adr/0007-no-step4-verdicts-in-v1.md`).
- **Speed.** Stage 2 takes about 40 seconds on the full Online Retail II
  file (1 million lines), above the few seconds `docs/SPECS.md` section 11
  aims for.

## Status

See `PROJECT_PLAN.md` section 12.
