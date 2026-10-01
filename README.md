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
| `docs/DATA_FAILURE_MODES.md` | Every known input-data failure mode, how it is caught and handled, and its test |
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
- **Numbers written for people are not read.** A price with a thousands
  separator ("1,000.00"), a currency sign ("$10.00") or a decimal comma
  ("10,5") is counted nowhere: its lines are listed as unmeasurable, but
  the revenue shown beside them silently leaves them out. Export plain
  numbers (`docs/DATA_FAILURE_MODES.md`, which lists every input shape and
  how it is handled).
- **A month that barely moved still gets a cause.** On a synthetic store
  with nothing planted, every one of 30 months named a cause: the engine has
  no test of whether a change is larger than the shop's usual month-to-month
  movement. Read a small change's cause with that in mind (`PROJECT_PLAN.md`
  3E2-F1).
- **No AI recommendations yet.** Stage 4's AI strategy step is built but
  off in v1 (`STRATEGY_AI_ENABLED=false`): its reviews found numbers and
  words it could still let through, so forecast.json carries the forecast
  alone until that is decided (`PROJECT_PLAN.md` 4B).
- **The forecast's season.** Stage 4 multiplies the forecast by a monthly
  seasonality index only when two or more years agree on it. Some shapes
  still read as a season: a change of level between the two years in a
  noisy history, one big month at the peak of a mild season, or a real
  season with a one-time step. On those the forecast and its band are
  unreliable. None occurs on the demo files (`PROJECT_PLAN.md` 8D). A
  season read from exactly two years - the fewest it can be read from, where
  a one-time change of level cannot be fully told from the season - says so
  beside the forecast; the demo sample's does.
- **Speed.** On the 39 MB demo sample (below) the whole pipeline takes
  65-69 seconds end to end, stages 2-5 44-45 of them (the analysis about
  20, the diagnosis about 25; the forecast and the report under a second)
  against the 60 `docs/SPECS.md` section 11 gives them; at the 50 MB upload
  cap the analysis and the diagnosis alone take 55. Profiling takes 9-11
  seconds where SPECS asks for 3. The AI's own response time is not in
  these figures.
- **Memory.** The server process peaks at about 830 MB on the demo sample
  and about 990 MB at the 50 MB cap (stage 1's cleaning is the peak, about
  13 times the file's size; the analysis and the diagnosis reach 680-780
  MB), and keeps about 300 MB of caches between steps. One 50 MB file needs
  about 1 GB; each run processed at the same time adds about 0.5-0.7 GB
  (`PROJECT_PLAN.md` Phase 9).

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

## How well the diagnosis finds a planted cause

A fixed-seed synthetic store (`tests/scenarios/`) plants one known cause per
scenario - a price cut, a mix shift, lapsed customers, a lost week, a
stockout, a season and more (`docs/AI_PIPELINE.md` 7.11). At the fixed seed
the diagnosis says what was planted in **8 of 12** scenarios - 7 by the
headline, and the x100 price-entry error by its trust caution (its headline
names the price change the error made, the caution beside it) - with **8
decoys** (causes supported that were not planted) and **2 false alarms**,
both on the scenarios where nothing was planted. Over 30 seeds: lapsed
customers and the x100 error are caught in 30 of 30; the price cut, the mix
shift, a lost week and a masked shift in 29; discontinued products 26; a
stockout 22 (a small plant, inside the store's noise); a season 17; the
calendar 8; and **a month with nothing planted is never left without a
cause (0 of 30)**. Outside those, 17 of 300 runs named a cause that was not
planted. Measured before the stage 3 completion work (3E1b); the misses are
open decisions in `PROJECT_PLAN.md` 3E2-F1, 3E2-F2 and 3E2-F3.

## Status

See `PROJECT_PLAN.md` section 12.
