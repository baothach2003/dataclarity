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
- **The forecast's season.** Stage 4 multiplies the forecast by a monthly
  seasonality index only when two or more years agree on it. Some shapes
  still read as a season: a change of level between the two years in a
  noisy history, one big month at the peak of a mild season, or a real
  season with a one-time step. On those the forecast and its band are
  unreliable. None occurs on the demo files (`PROJECT_PLAN.md` 8D).
- **Speed.** On the 39 MB demo sample (below) the analysis takes about 18
  seconds and the diagnosis about 24; at the 50 MB upload cap, 25 and 31 -
  55 of the 60 seconds `docs/SPECS.md` section 11 gives stages 2-5
  together, and profiling takes 11 seconds where it asks for 3. Stages 4
  and 5 are not built yet, so the whole pipeline is not timed; these
  figures leave out the AI's own response time.

## Demo data

The demo file is a sample of **Online Retail II** - two years (December 2009
to December 2011) of a UK online gift retailer's invoice lines: Chen, D.
(2019). *Online Retail II* [Dataset]. UCI Machine Learning Repository.
https://doi.org/10.24432/C5CG6D - licensed under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). **Changes made:** the two
yearly sheets joined into one CSV and sampled as described below; no line
was edited. The data is not in this repository:
`scripts/demo/online_retail_ii.py` builds the sample from the UCI download,
checks the workbook inside against its recorded SHA-256, and prints the
sample's own (the same on every platform).

What it keeps (460,859 lines, 39.1 MB of 1,048,576 bytes - 40,972,029
bytes - under the 50 MB upload cap):
- the workbook's two sheets as one file, their nine overlapping days
  (1-9 December 2010, in both) dropped by date - never as "duplicates",
  since the file also holds genuine repeated lines;
- every line of 2,659 of the 5,942 customers, drawn with a fixed seed (502)
  at a fraction of 0.46; the lines with no customer, drawn by invoice at the
  same fraction (4,001 of 8,752 invoices), so revenue from unidentified
  buyers stays in the figures;
- both entered-then-cancelled typing mistakes whole (80,995 and 74,215
  units, sold and cancelled minutes apart), whatever the draw.

```bash
pip install -r scripts/demo/requirements.txt    # openpyxl, to read the workbook
python scripts/demo/online_retail_ii.py path/to/online+retail+ii.zip   # keep the download outside the repo
# -> demo_data/online_retail_ii_sample.csv (git-ignored)
```

The recorded sample comes from the library versions pinned in
`backend/requirements.txt` (pandas, numpy) and `scripts/demo/requirements.txt`.
With other versions the sample can differ: the command then writes it as
`online_retail_ii_sample.not-recorded.csv` beside the path, never over a
recorded sample, prints its checksum and exits with 1.

## Status

See `PROJECT_PLAN.md` section 12.
