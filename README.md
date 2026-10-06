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
- **Numbers written for people are read only when the file says how.** A
  price with a thousands separator ("1,000.00"), a currency sign ("$10.00")
  or a decimal comma ("10,5") is read at upload - from the cells that prove
  the format; when nothing in the column says whether "1,000" is one
  thousand or one, Review asks and cleaning waits for the answer. Indian
  grouping ("1,00,000") and a currency code ("USD 10") are not read: their
  lines are listed as unmeasurable
  (`docs/DATA_FAILURE_MODES.md` lists every input shape and how it is
  handled).
- **A mistyped year is caught only when it lands after the upload.** A line
  dated after the day the file was uploaded (a 2042 for 2024) is left out of
  choosing the months compared, counted and reported beside the dates the
  file covers. A typo that lands between the data and the upload (a 2025 in
  a 2024 file) cannot be told from a late sale: it moves the period, and the
  run says the export was cut short.
- **Walk-in placeholders are only marked until confirmed.** A customer value
  such as "Guest" that Review asked about and nobody answered stays a
  customer - it cannot be told from a customer called Guest - and is marked
  "suggested, not confirmed" beside the customer figures and the causes.
- **Exact copies of a line are kept.** A repeated line cannot be told from a
  genuine repeat sale, so the AI never proposes removing them; Review offers
  it, and says how many lines and how much revenue removing them takes.
- **A small change names no cause.** The headline singles a cause out only
  when the month moved at least twice the shop's median month-to-month
  movement; inside that it says the change is within the shop's usual range
  (the hypothesis table still shows every verdict). Causes whose effect sits
  inside ordinary noise - a calendar shift of a few percent, a short
  stockout - are then left to the table, with a note above it saying so. A
  file with fewer than eight months before the compared one is too short to
  measure the usual movement: the headline names no cause and says why. In
  a shop with a season (one the forecast also claims: two full years that
  agree), the month is compared with the same month's change in the
  earlier years instead: within twice the shop's usual year-on-year
  difference it reads "consistent with the season" and names no cause;
  four times beyond it or more it is stated as a shortfall or an excess
  against the season; in between, the month-to-month test above decides
  (`PROJECT_PLAN.md` 3E1b).
- **A season can mask a loss.** When a season predicts a rise and a cause -
  customers lost, say - cancels most of it, revenue still rises a little:
  where the month falls short of the same month in earlier years by four
  times the shop's usual year-on-year difference or more, the headline says
  so, but cannot name why, because no tested cause measures the gap from
  the season. Where the month-to-month
  test still names a cause, it stands and the gap is stated beside it
  (`PROJECT_PLAN.md` 8D).
- **Missing days in a quiet shop.** Days with no sales are judged against
  the shop's own pattern and its month-to-month spread: in a shop that
  trades every day one lost day is caught, but in a shop that trades on a
  few days a week, or in a seasonal shop's quiet months, a lost day or two
  sits inside its ordinary variation and is not seen.
- **No AI recommendations in v1.** The report's suggested actions are
  code-written: code selects at most three findings and picks each action
  from a tested catalog. Five review cycles found that free text written by
  an AI cannot be closed by a banned-word list, so the AI step was removed;
  it is v2 work (`PROJECT_PLAN.md` Backlog, `docs/AI_PIPELINE.md` 8).
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
  (`PROJECT_PLAN.md` Phase 9). The peak grows with the file: about 330 MB at
  5 MB, 390 MB at 10 MB, 560 MB at 20 MB. `MAX_UPLOAD_MB`,
  `PREVIEW_CACHE_MAX_MB` and `MAX_CONCURRENT_HEAVY_STEPS` (profiling,
  Review's summary, cleaning, the analysis and the diagnosis; one at a time
  by default - a step over the limit waits) bound it.

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
stockout, a season, a season masking lapsed customers and more
(`docs/AI_PIPELINE.md` 7.11). At the fixed seed the diagnosis says what was
planted in **10 of 14** scenarios - 9 by the headline (the three with
nothing planted name no cause, the table's note says why), and the x100
price-entry error by its trust caution (its headline names the price change
the error made, the caution beside it) - with **no decoy** and **no false
alarm**. The season masking lapsed customers meets its own expectation - the
headline states the shortfall against the season - but cannot name the lost
customers (a known limit). Over 30 seeds (the planted cause in the headline, or
the x100 caution): lapsed customers, the x100 error and the six-month build
30 of 30; nothing planted, the price cut, a lost week and a masked shift 29;
discontinued products 26; a mix shift 25; a season 16 (customers buying less
often fits closer and takes the headline - the table still shows the season);
a stockout 9 and the calendar 2 - their effect sits inside the store's
ordinary month-to-month movement, so the headline names no cause and leaves
them to the table. In a strongly seasonal store: nothing planted 30 (consistent
with the season, or within the usual movement - never a cause); the season
masking lapsed customers 30 (the shortfall against the season stated, its
cause not named). At most one decoy (a cause supported that was not
planted) in at least 25 of 30 seeds holds for every scenario but the
calendar (23 of 30), a known limit (`PROJECT_PLAN.md` 8D).

## Status

See `PROJECT_PLAN.md` section 12.
