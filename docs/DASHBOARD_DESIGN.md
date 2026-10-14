# The dashboard - design (PROJECT_PLAN item 9D)

Status: **design, written in the overnight run of 2026-10-14 (step 1).**
Thach was away and asked the run to continue without his approval. Every
choice below is his (D1-D7, PROJECT_PLAN 9D), forced by an existing rule
(named beside it), or a **decision made alone**, marked so and listed in
section 9 for his veto.

Why: Thach's manual test found that the redesigned page still does not let a
reader SEE the result at a glance. He wants a dashboard before deploy that
works for ANY sales file, not shaped on the Kaggle file.

Thach's decisions, short (the full text and reasons are at PROJECT_PLAN 9D):

| | Decision |
|---|---|
| **D1** | The whole dashboard before deploy, the AI part included; any real AI call needs his approval |
| **D2** | KPI tiles always first; which tiles depends on the file's fields; this month and its change on the previous whole month, from existing fields; an incomplete previous month shows the existing reason, no change; never a tile shown only to fill the row |
| **D3** | Widgets below, by the data and by what the analysis found; order: the widget tied to stage 3's named cause, then the size of what each shows moving (existing contributions), then a fixed fallback order; a widget whose data the file lacks is not shown; the front section stays, placed by the same rule; Technical details last |
| **D4** | Option A: code decides layout and order; the AI only chooses up to 2 category columns from a list code builds; validated names only; the user changes or removes them in Review; AI failure -> no breakdown |
| **D5** | Scope freeze reopened for one thing: stage 2's "sales by <category column>" for the compared months (additive) |
| **D6** | Chart type from the data's shape: time series a line, categories sorted horizontal bars, parts of a whole only with very few parts |
| **D7** | One copy: report.json carries the dashboard block; report.html and Insights draw it; the page computes and words no figure |

Sources used for every figure here: Thach's Kaggle run of 2026-10-14
(`ae5e8361`, read as written), the Online Retail II demo runs as stage 5's test
fixtures hold them (`tests/stages/report/fixtures/demo_classed`,
`demo_unanswered`) and the smoke test's classed run (`0d20a8dc`, real product
names), a minimal shape cut from the Kaggle file (section 6.4), and the
scenario generator S0-S13 at seed 1 (the draft rule in the scratchpad,
`draft_dashboard.py` / `draft_scenarios.py`; the production code is step 3's,
tests first).

## 1. The page, top to bottom

```
[KPI tiles - one row, 2 to 5 tiles]                        (D2, section 2)
[caution lines, when a data check cautions]                (3.3a: beside the figures)
[widget 1] [widget 2] ...                                  (D3 order, section 4)
   charts: sales by month, where the change came from, customers,
           products, category, breakdown 1, breakdown 2, returns
   text:   summary, what was checked, what to do next, next month,
           what this report cannot know
[Technical details - closed]                               (always last)
```

The text widgets ARE the front section of report.json 2.9, unchanged in
wording (one copy: the dashboard names them, it does not re-write them).

**The caution lines move up** (forced by CLAUDE.md 3.3a, found by the
diversity check, section 6: S10's x100 prices and S5's lost week put the
summary, which carries the caution, below six charts drawn from the cautioned
figures). `front.caution` is drawn directly under the tiles. Nothing else of
the summary moves (D3: the summary is placed by the rule).

## 2. KPI tiles (D2)

Every figure comes from report.json's layer 1 (`layer_1_numbers.kpis`), from
the bridge (`tree.lever.bridge`) or from the front's own sentence A - no new
stage field, nothing computed (CONTRACTS 11: "every other KPI is shown as its
two months' values side by side"). So the "change" of a tile other than sales
is its previous month's value beside this month's, never a difference.

| Tile | Shown when | This month | Its change | Unit | When data is missing |
|---|---|---|---|---|---|
| **Sales** | always | `kpis.revenue.current` | `bridge.shown_change` and `revenue_change_pct`, printed exactly as sentence A prints them ("+4,925.00 (+11.9%) on November 2024"; Q22, Q56) - the exact `core.revenue_change` when the bridge is withheld (Q24) | money (ISO code, Q8) | current withheld: the tile shows its reason in plain words (as the front's "cannot be shown" sentence); previous incomplete: "Not compared with <month>: the file does not cover it whole" (the front's own wording) |
| **Orders** (order id mapped, `orders_basis` order_id) / **Lines** (`lines`) | always (the count is never null) | `kpis.orders.current` | "was 308 in November 2024" (`kpis.orders.previous`) | count | previous incomplete: no "was", the sales tile carries the reason once |
| **Average order value** / **Average line value** | `kpis.aov.current` not null | `kpis.aov.current` | "was ..." (`kpis.aov.previous`; null with its reason -> no "was") | money | current null: **no tile**; its reason is one line under the row ("Average order value is not shown: <reason>") |
| **Customers who placed an order** | a column is mapped to `customer` AND the bridge draws a customers bar (`bridge.bars[factor=customers]`) | that bar's `value_cur` | "was 609 in October 2011" (`value_prev`) | count | no such bar (bridge withheld, two-factor split, not compared): **no tile**, one line under the row: "Customers are not shown: this month is not compared with the last" / "...: the change is not split this month". Active customers (who bought or returned) stay in Technical details (Thach, Q4) |
| **Return rate** (`Orders with a return, per order sold` on order ids; `Return lines per sale line` on lines - layer 1's labels) | the file has returns in the months the tile reads: `core.identity.current.returns` (and `previous.returns` when compared) not 0.00 as printed | `kpis.return_rate.current` at the appendix's precision (`0.152`) | "was 0.169 in October 2011" | ratio (never a percentage: CONTRACTS 6, "no reader may treat it as a share") | current null: no tile, its reason under the row |

Rules held by the tiles:
- **Never an empty or zero tile to fill the row** (D2): a tile is shown with a
  figure, or not at all; the one exception is Sales, which always stands and
  carries its own reason when its figure is withheld (it is the anchor of the
  row, and the reason is the content).
- **Direction**: a small arrow from the order of the two PRINTED figures (up,
  down, same - equal as printed is "same"), in the neutral text colour: no
  green or red, because a colour would be a verdict on the month (ADR-0007; the
  KPI card's "up = green" stays an open issue of the old cards only). Sales'
  arrow follows the sign of the shown change.
- **Notes beside each tile** (3.3a): `kpis[].notes`, as layer 1 already holds
  them.
- **Blocked**: every tile shows this month only, no "was", no arrow; the
  sales tile's line says "Not compared: the data checks did not pass - see
  Technical details" (the blocked sentence's pattern, Q70).
- Order of the tiles: Sales, Orders/Lines, Average order/line value,
  Customers, Return rate (layer 1's order).

## 3. Widget catalog (D3, D6)

Each widget's data condition, chart type, the contract fields it reads, and
the NEW fields. "Size" is what the order rule reads (section 4); every size is
an EXISTING money contribution, never a figure computed for it.

| Widget | Shown when (else not shown - D3) | Chart (D6) | Reads | Size (money) | Tied to |
|---|---|---|---|---|---|
| **Sales by month** (`trend`) | at least two whole months drawn (`charts[revenue_trend]` with 2+ non-null points) | line (time series) - today's front chart, its part-month and gap sentences under it | `charts[revenue_trend]`, `front.chart_title`, `front.chart_note` | the shown change, `bridge.shown_change` (exact `core.revenue_change` without a bridge): what the line moves between the compared months | T2 |
| **Where the change came from** (`waterfall`) | `front.waterfall` not null | the bridge waterfall (today's; across on a phone) | `front.waterfall` | largest `|bars[].shown|` | B1, B2, P1, P2; rule 4 |
| **Customers: new, back, stopped buying** (`customers`) | a customer column, `tree.customers` and its `previous_transition`, and at least one of the three groups not 0.00 as printed in either month | horizontal bars, this month and last month per group (3 groups: very few, but each group is NOT a part of a whole - they overlap the rest of the shop - so bars, not parts) | `shared.claim_lines.money_terms` for C1, C2, C3 - the checklist's own subjects and figures (Q34); C2 only where both lapsed terms are a loss, as the checklist | largest `|hypotheses[C1..C3].contribution|` | C1, C2, C3 |
| **Products with the most sales this month** (`products`) - as built after step 3's review | `products.top_products` (stage 2) with 2+ products | sorted horizontal bars of this month's sales | `products.top_products[]` (product, revenue) | none (it shows no movement) | - (no product cause is tied) |
| **Sales by category** (`category`) | a column mapped to `category` with 2+ categories in `by_dimension.category` | sorted horizontal bars (this month; last month as a marker); a part-of-whole bar only with 2-3 categories all above 0 in both months (D6) | `by_dimension.category[]` (stage 2: name, revenue_current, revenue_previous) | largest `|delta|` of `localization.dimensions[category]` members (stage 3) | - |
| **Sales by <column>** (`breakdown_1`, `breakdown_2`) | the column chosen in Review (section 5) AND stage 2 wrote its figures (`withheld_reason` null) | as category | **NEW** `by_dimension.breakdowns[]` (stage 2, section 7) | largest `|members[].change|` (**NEW**, stage 2) | - |
| **Returns** (`returns`) | the file has returns (as the return-rate tile) | two horizontal bars: refunds last month, this month | `money_terms("P3")` (the checklist's "Refunds for returned goods") | `|hypotheses[P3].contribution|` | P3 |
| **Summary** (`summary`) | always (blocked: the blocked sentence) | text | `front.summary`, `front.sales_note`, `front.waterfall_note` | none | - |
| **What was checked** (`checklist`) | `front.checklist` not empty | text | `front.checklist`, `front.data_checks` | none | D1 under rule 2 |
| **What to do next** (`next_steps`) | `front.next_steps` not null | text | `front.next_steps` | none | - |
| **Next month** (`next_month`) | always | text | `front.next_month` | none | - |
| **What this report cannot know** (`cannot_know`) | always | text | `front.cannot_know` | none | - |

Details:
- **Not compared** (previous month incomplete, or this month withheld): no
  size exists (no change), so the order is the fallback order; the charts
  that need two months (waterfall, customers, products, returns) are not
  shown; trend, category and breakdowns show this month alone (no "was"
  marker - CONTRACTS 11: never a previous value beside a current one).
- **Blocked**: only the summary (the blocked sentence), next month and what
  this report cannot know - as the front today. No chart is drawn from figures
  the data checks refused.
- **The "(not a product)" bucket and "Other"** are not drawn as product bars
  (they are not products, and "Other" is the rest of the list, not a mover);
  "Other" is printed in the caption. The "(no product name)" gap bucket IS
  drawn under stage 3's label (Thach, 3D: blank keys are visible buckets).
- **Breakdown and category bars**: a blank value is its own bar, "(blank)"
  (stage 3's visible-bucket rule); a value sold in one month only shows 0.00
  in the other (as stage 2's category block does).
- **Charts follow the repo's conventions**: the page draws with Recharts
  (`FrontSalesChart`, `FrontWaterfall`), report.html with inline SVG
  (`html_svg.py`), the design tokens only (FIGMA_DESIGN_NOTES 4) and the
  design exception's rule (no Figma frame: report.html's layout in the
  tokens - recorded at FIGMA_DESIGN_NOTES 3 when built). Bars run across, so
  every label has its own line at 390 px (the waterfall's phone rule).
- **Notes** (3.3a): each widget carries the note codes of the figures it
  draws - revenue's notes beside every sales chart, `returns`/`return_rate`
  notes beside returns, `customers` beside customers, `products` beside
  products - by the front's `_notes` logic (one copy).
- **Front sentences the dashboard makes false** (found on the mocks, fixed in
  stage 5 in step 3, failing tests first): the front points at its parts by
  NUMBER - "The chart in section 2 is the one that adds up", "compare sales
  with the estimate in section 5" - and the order rule moves them, so each
  pointer names its widget instead ("the chart 'Where the change came from'",
  "the estimate under 'Next month'"); and "What this report cannot know" says
  "Sales by channel, payment method or country: this version does not split
  sales that way" beside a drawn breakdown - it then names only what is not
  split (or is left out when a breakdown is drawn and no unused candidate is
  left).
- **Not built (no data or no meaning yet)**: a country widget (`by_dimension.
  country` is always empty in v1: no country field), top products without a
  change (the movers chart covers products), a forecast chart in the front
  (the next-month text stays; the forecast chart stays in Technical details -
  D3 keeps the front as it is).

## 4. The order rule (D3)

Code decides, from report.json's own data:

1. **The widget tied to stage 3's named cause first.** Only under headline
   rules 5 and 6 (a cause named) and rule 4 (the offsetting pair - the
   waterfall draws orders against order value). The cause is
   `headline.named` (the first id that has a shown widget), else
   `headline.hypothesis_id`. The tie table is section 3's last column. Under
   rules 1, 2, 3 and 7 nothing is tied.
2. **Then by size**, largest first: every widget with a size (section 3).
3. **Then the fixed fallback order** - for the widgets with no size, and to
   break equal sizes: summary, trend, waterfall, customers, products,
   category, breakdown 1, breakdown 2, returns, checklist, next steps, next
   month, what this report cannot know.
4. Technical details always last (outside the list).

**Decision made alone (D-1):** the widgets with no size (the text sections)
come after every sized widget - the rule's letter ("then by size, then a
fixed fallback order"). The cost: the summary, which words the named cause,
sits below the charts (see the worked examples). The alternative, for Thach:
pin the summary directly under the tiles (a fixed place outside the rule).
**Q1** in section 9.

**Decision made alone (D-2):** the trend's size is the shown change - "what
the line shows moving" between the two compared months. So it usually comes
right after the named widget; under offsetting moves (rule 4) a part can be
larger than the whole and come first.

Worked examples (the draft rule on the real files; all six in section 6):

- **Kaggle** (rule 6, B1 named): waterfall [named, 4,712.29] > Sales by
  Location [7,765.50] > trend [4,925.00] > category [2,562.50] > Sales by
  Payment Method [2,424.50] > summary > products > checklist >
  next steps > next month > cannot know. (The two breakdowns are the
  illustrative AI choice, section 5; their figures computed by section 7's
  definition.)
- **Online Retail II, classed** (rule 7, nothing tied): trend [141,755.41] >
  waterfall [127,578.73] > customers [36,744.87] > returns [27,123.00] >
  summary > products > ... (no category column; Country is not
  eligible - 38 values, section 5).
- **S4, lapsed customers** (rule 6, C2 named): customers [named, 12,180.85] >
  waterfall [12,777.13] > trend [11,872.60] > category > products > returns >
  text.

## 5. The AI's column choice (D4)

### 5.1 Eligible columns - code, from profile.json and the plan as edited

A column is eligible when ALL hold (checked by stage 1 code; doubtful = not
eligible, Thach's detector principle):

1. the plan maps it to `ignore` and does not drop it (`drop_column`): never a
   mapped field (D4) - a mapped `category` is the category widget already;
2. it is in profile.json (the bounded profile: the first 60 columns);
3. its header is not empty and is not pandas' placeholder ("Unnamed: 3");
4. `unique_count` between 2 and 12 (D4's "2 to about 12");
5. `null_pct` at most 10% ("few blanks");
6. not numbers: profile's `dtype` is not numeric, it has no `number_format`
   measure, and NO top value reads as a number however it is dressed - a
   sign, a currency sign or code, brackets, separators, a percent or a short
   unit ("$4.50", "4,50 EUR", "(1.00)", "10%", "1kg"): an amount, a store
   number, a code - doubtful;
7. not dates: no `date_order` measure, no top value a date by
   `shared.dates.as_dates`, and no top value a period written as text (a
   quarter, a half, a week, a month's name) - two compared months split by a
   period are no split;
8. its schema type is `categorical_nominal`, `categorical_ordinal`, `boolean`
   or `text` (the schema answer the user may have edited,
   `column_actions[].semantic_type`) - never an identifier, a date or a number.

**As built (the step 4 review):** rules 6 and 7 were first "ALL values read as
a number / a date"; the review found Square's "$0.00" amounts, "10%" and
"0, 1, 2, none" offered under a manual plan (every column typed "text"), so
one such value now suffices; its scoped review added "30.000 đ", "R$ 4,90",
"US$4.90", "Rs. 49" and a Unicode minus (any digit beside a currency sign
reads as a number) and narrowed the period test to whole month names (it had
refused "Marketplace", "Declined", "Married"). Weekday names stay eligible (a
weekday split is not a period). Known misses, by "doubtful = not offered":
"POS 1", "VIP 1" (a capital code before a number reads as a currency),
sizes "2XL", "3D", and "W1"/"H1" codes (read as weeks and halves); the
number and date rules read the profile's 10 commonest values, so an 11th or
12th value is not checked. Each eligible column's values are cut as AI_PIPELINE section 1
cuts them (100 characters), and the AI sees the first 12 eligible columns in
the file's order: the input is at most 12 x 10 values x 100 characters.

**Decision made alone (D-3):** 10% for "few blanks", and "no value reading as
a number" (store numbers 1-5 are excluded; a false find would chart an
amount as a category - the costly error).

**The ask (as built, the step 4 review):** the call is counted per run but
never exclusive with execute or the plan's "try again" - Confirm is never
held for it. One ask per run at a time: a second ask (another tab, a column
retyped) waits for the first's answer and its stored file, so the AI is
asked at most once per run. Nothing is stored while no column is eligible, so
an edit that makes one eligible still asks. A stored file this version cannot
read is no suggestion, never a second call. While the question loads,
Review says that confirming now splits sales by no column. The AI's answer
must be exactly `{"breakdowns": [...]}`: any other key makes it no answer.
Generic cleaning refuses a plan that still names breakdowns.

### 5.2 Where the call happens - (2) a separate call (decision made alone, D-4)

| | (1) inside the schema call | (2) a separate call (chosen) |
|---|---|---|
| Cost | +~100-200 output tokens on a call made anyway (~$0.002) | a new call: ~700-1,000 input tokens (instructions + at most 12 columns x 10 values), ~30-60 output: ~$0.002-0.003 at Sonnet 5's $2/$10 per million (estimated, not measured) |
| Latency | +1-2 s on the schema step the user waits for | ~2-5 s (estimated), run while Review is open (the control shows "Looking at your columns..."), never in the user's path to Confirm |
| Risk to the validated schema prompt | changes it: the 18th run's 4 of 4 first answers would need measuring again, and a schema failure spends the run's only retry | none: the schema and plan prompts are untouched |
| Can it choose "from a list code builds"? | **no** - the mapping that decides eligibility is that same call's answer, so the list cannot exist before it | yes - the list is built from the answer the user has reviewed |

(1) is impossible as D4 is written, and (2) leaves the validated prompt alone.

### 5.3 The call

- **Endpoint** `POST /api/runs/{id}/breakdowns` with the plan as edited (the
  currency question's pattern). Read only for the run's state; the one thing
  it writes is the AI's answer, once per run.
- **Input** (AI_PIPELINE 1's bound): for each eligible column, its header and
  its profile top values (at most 10, each already cut to 100 characters) -
  nothing else of the file; no sample rows. At most 12 columns.
- **Prompt** `prompts/breakdowns.md`: choose at most 2 columns a shop owner
  would want sales split by (a payment method, a store or location, a sales
  channel, a product group...), only names from the list as written, or none
  when no column is such a split; JSON only.
- **Output schema** `{"breakdowns": ["<column name>", ...]}`, at most 2,
  strict (no coercion).
- **Validation**: every name exactly one of the list's; no repeat; at most
  2. Anything else is an invalid answer.
- **Model**: `MODEL_REASONING` (ADR-0003: a judgement step, once per run -
  not the bulk model's high-volume case).
- **No retry** (decision made alone, D-5): one attempt; the run's shared
  retry stays for the schema and the plan (the 17th run showed the schema step
  needs it). Invalid, a timeout or any failure: no breakdown suggested.
- **Not called** when no column is eligible (nothing to choose).
- **Stored** `breakdown_suggestion.json` (NEW stage 1 file, never read by a
  later stage): the eligible names, the chosen names, the status
  (`chosen`, `none_eligible`, `ai_unavailable`) and `model_used`. A second
  request reuses it (one call per run), filtering the chosen names by the
  list as it stands then.
- **Budget**: stage 1's third call; with stages 3 and 4 making none, a run
  stays within AI_PIPELINE 2's four.

### 5.4 Review - the user decides (CLAUDE.md 3.3)

A notice on Review (the existing Notice and Dropdown components):

- "Break sales down by" - the chosen columns, each with a remove button, and
  an "Add a column" dropdown of the other eligible columns, at most 2 in all;
  the header of each column as written in the file.
- Its line says where the choice came from: "Suggested from your file's
  columns." / "No column of your file can split sales (each needs 2 to 12
  values and few blanks)." / "No suggestion could be made; you can pick up to
  two."
- The plan sent to execute carries the answer: `plan.breakdowns` (NEW,
  plan_final.json 4.4) - the names as shown. Unchanged, the suggestion is
  what runs (as a found currency: Review shows it, executing confirms it).
- **Decision made alone (D-6):** with no suggestion, the user may still add
  columns from the eligible list (the user's own choice fabricates nothing);
  none is pre-selected.

### 5.5 At execute and after

- Stage 1 checks the answer against the eligibility rules with the FINAL plan
  (a column mapped or dropped since is left out) and writes the kept names to
  `cleaning_report.json` `breakdowns` (NEW, 4.4), each with its name in
  cleaned.csv (a reserved rename followed). A name the file does not hold, or
  more than 2: INVALID_PLAN (never silently changed - the plan is the user's).
- Stage 2 computes the figures (section 7). Stage 5 draws them.
- **Fallback**: AI failure -> no breakdown; stage 2 cannot compute one (more
  than 12 values among the compared months' lines, a column gone) -> the
  breakdown is withheld with its reason and its widget is not shown
  (suppress, never fabricate).

## 6. Diversity check (step 1 f)

Applied with the draft rule to every sales file in the repo's tests and the
real runs. "Tiles" in D2's order; the widget order as section 4 decides it.

### 6.1 The real runs

| File | Shape | Tiles | Widgets, in order | Why |
|---|---|---|---|---|
| Kaggle `ae5e8361` (2024-12 vs 2024-11) | one line per order, order id, customer, category, 3 unmapped text columns | Sales 46,292.50 (+4,925.00, +11.9%); Orders 343 (was 308); Average order value 134.96 (was 134.31); Customers who placed an order 25 (was 25) - no return rate (no return line) | waterfall, Location*, trend, category, Payment Method*, products, then the text | B1 named -> waterfall. *Illustrative AI choice: eligible Payment Method (3 values), Location (2); Discount Applied fails "few blanks" (33% blank in the raw file); Total Spent is numbers. Customers widget not shown: new, back and stopped buying are 0.00 in both months (the same 25 customers) |
| Online Retail II, classed (2011-11 vs 2011-10) | line-level invoices, returns, charges classed | Sales 663,315.58 (+141,755.41, +27.2%); Orders 1,234 (was 904); AOV 537.53 (was 576.95); Customers who placed an order 756 (was 609); Return rate 0.152 (was 0.169) | trend, waterfall, customers, returns, products, text | rule 7: nothing tied. **No breakdown**: Country (the one unmapped column) has 38+ values - not eligible (Q3) |
| Online Retail II, unanswered | the same, no line class | Sales 654,527.09 (+139,466.56, +27.1%); Orders 1,240 (915); AOV 527.84 (562.91); Customers 756 (609); Return rate 0.165 (0.175) | trend, waterfall, customers, returns, products, text | as classed |

### 6.2 The scenario generator (S0-S13, seed 1)

Every scenario has the same columns (Invoice, Date, Product, Category, Qty,
Price, Customer - all mapped): no column is eligible, so no breakdown; all
five tiles (returns are generated). The order:

| Scenario | Headline | Order (size in money) |
|---|---|---|
| S0, S11, S12 (nothing planted) | rule 7 | trend 3,218.40 > waterfall 2,459.66 > category 1,336.61 > products 634.20 > customers 375.11 > returns 42.32 > text |
| S1 (calendar) | rule 7 at seed 1 (the known 23-of-30 criterion) | waterfall 5,713.49 > trend > customers > category > products > returns > text |
| S2 (price cut) | rule 6, P1 | waterfall (named) > trend 7,188.68 > category > products > customers > returns > text |
| S3 (mix shift) | rule 7 | waterfall 5,690.40 > trend > products 3,473.00 > category > customers > returns > text |
| S4 (lapsed) | rule 6, C2 | customers (named) > waterfall > trend > category > products > returns > text |
| S5 (lost week) | rule 2, caution | waterfall > trend > customers > category > products > returns > text; **the caution under the tiles** |
| S6 (masked shift) | rule 4 | waterfall (tied) > customers 16,234.14 > trend > category > products > returns > text |
| S7 (stockout) | rule 7 at seed 1 | category 5,313.53 > products 4,862.20 > trend > waterfall > customers > returns > text |
| S8 (discontinued) | rule 7 | trend > waterfall > products 1,498.68 > category > customers > returns > text |
| S9 (season) | rule 6, B1 | waterfall (named) > trend > category > products > customers > returns > text |
| S10 (x100 prices) | rule 6, P1, caution | waterfall (named) > trend > ... ; **the caution under the tiles** (found here: section 1) |
| S13 (lapsed in a season) | rule 7, shortfall | waterfall 18,932.83 > customers 13,900.33 > trend > category > products > returns > text - the season's shortfall is said by the summary, last (Q1) |

### 6.3 The export shapes (by their published columns; built as test files in step 4)

| Shape | What v1 analyses | Tiles | Breakdown candidates (5.1) |
|---|---|---|---|
| **Shopify orders export** (one row per line item: Name, Created at, Lineitem name/quantity/price/sku, Financial Status, Payment Method, Shipping Method, Source, Vendor, Shipping Country, Currency, ...) | yes (order id = Name, product, quantity, price, date) | Sales, Orders, AOV; Customers when Email is mapped; Return rate only with refund lines | **usually none**: Shopify writes the order-level fields (Financial Status, Payment Method, Shipping Method, Source) on an order's FIRST line only, so on multi-line orders they are mostly blank and fail "few blanks"; Vendor (2-12 values, no blanks) is the likely one. Conservative by design (Q4) |
| **WooCommerce order export** (Order Number, Order Status, Order Date, Payment Method Title, Shipping Method Title, Item Name, Quantity, Item Cost, Billing Country, ...) | yes | Sales, Orders, AOV (+ Customers with an email column) | Payment Method Title, Shipping Method Title, Order Status (when repeated on every line, as the common plugins write it); Billing Country only under 13 countries |
| **Square item sales** (Date, Time, Category, Item, Qty, Gross Sales, Net Sales, Transaction ID, Event Type, Location, Dining Option, Channel, Device Name, Card Brand, Customer ID, ...) | yes | Sales, Orders, AOV, Customers (Customer ID), Return rate (Event Type Refund lines with negative qty) | Location, Channel, Dining Option, Device Name, Card Brand; Event Type (Payment/Refund) is eligible too - the AI may choose it; the user removes it in Review (Q5) |
| **Stripe payments export** (id, Created, Amount, Amount Refunded, Currency, Status, Customer ID, Card Brand, ...) | **no**: no product and no quantity - stage 1's required fields (product_name, transaction_date, quantity) cannot be mapped, so Review cannot confirm a plan | none - no analysis | - |

### 6.4 Date + amount only, and no order id

- **A file of a date and an amount only** (Stripe's shape, a till's Z-report
  totals): v1 cannot analyse it - `product_name` and `quantity` are required
  fields (AI_PIPELINE 6, frozen by CLAUDE.md 3.6), so Review refuses the plan
  and no dashboard exists. **Q2** in section 9 (reopening it would change a
  frozen definition: D5 reopens only the breakdown figures).
- **The minimal analysable shape** (no order id, no customer, no category -
  date, item, quantity, price: the Kaggle file cut to four columns, run
  through stages 1-5 here): Sales 46,292.50 (+4,925.00, +11.9%); **Lines** 343
  (was 308); **Average line value** 134.96 (was 134.31). No customers tile (no
  column), no return rate (none). Widgets: waterfall (rule 6, B2 named; bars
  Lines, Items per line, Average price per item) > trend 4,925.00 > products
  1,148.00 > text. No category, no customers, no breakdown (no other column).
  This is the dashboard of the "date and amount" mock (decision made alone,
  D-7: the closest shape v1 can analyse).

### 6.5 The currency test files

Every currency test frame (`tests/stages/ingest/test_currency.py`) is 1-6
lines in one month: the tiles show this month alone (not compared - no
previous month), the trend needs two months (not shown), no breakdown
(nothing eligible: their extra columns are a Currency column of one value or
a Country). Their dashboard is the Sales tile, Orders/Lines, AOV, and the
text widgets. Nothing in them is a widget's data.

## 7. Stage 2's breakdown figures (D5)

**Definition.** For each column in `cleaning_report.json` `breakdowns`, the
net revenue of the lines counted in revenue (`parse_transactions().counted`,
`revenue_amounts` - exactly what `core.revenue_*` and the category block sum),
grouped by the column's value read as stage 3 reads a category
(`shared.text.category_key`: what no reader can see removed, spaces
collapsed, case folded), shown by its first spelling (`category_text`), for
the current and the previous month.

NEW in metrics.json 16.3 (additive, optional, version-gated):

```
by_dimension.breakdowns: [
  { column: str,                       # the header as written in the file
    members: [ { name: str,            # the first spelling, or "(blank)"
                 is_blank: bool,
                 revenue_current: float,
                 revenue_previous: float,
                 change: float | None } ],   # current - previous; null with
                                              # the previous month incomplete
    change_reason: str | None,         # why every change is null
    withheld_reason: str | None }      # set: no members, the widget not shown
]                                      # [] before 16.3 and with no breakdown
```

Edge cases (each a test, hand-checked figures):
- **Blank values**: their lines form one member, `(blank)`, `is_blank` true -
  never dropped (the members then sum exactly to `core.revenue_*`).
- **Returns**: a return line's negative amount counts in its own row's value
  (net, as the category block); a member can be negative.
- **Lines vs orders**: money only - no count is computed, so the orders basis
  does not enter.
- **A value in one month only**: 0.0 in the other month.
- **More than 12 values** among the two months' counted lines (after the
  plan's cleaning, e.g. a case change undone): withheld, "the column has N
  values in these two months; a split is drawn for 12 at most".
- **The column missing from cleaned.csv** (a hand-edited file): withheld,
  never a 500.
- **Previous month incomplete**: `revenue_previous` kept (as the category
  block keeps it), `change` null with the period's reason.
- **No counted line in the two months**: members empty, withheld with the
  reason.
- Members sorted by name (as the category block); stage 5 sorts for drawing.

Tests: hand-built frames (two months, three values, a blank, a return, a
value in one month only, 13 values, a missing column, an incomplete previous
month, empty df, single row, all-null column); the identity "members sum to
`core.revenue_current` / `_previous`" over the three real runs and the
scenarios; the three real runs re-run with no breakdown: every existing
field identical (step 2's regression); consumer-contract rows (readers 5,
FE).

**As built (step 2, 2026-10-14).** `stages/analyze/metrics_breakdowns.py`;
metrics.json 16.3 (CONTRACTS 6, 10, 11); `cleaning_report.json` `breakdowns`
read by stage 2 (written by stage 1 from step 4; not written while empty, so
stage 1's file is unchanged until then). Method:
`C:\Users\Happy\dashboard-step2-method.txt`. Tests first (all red on the old
code); hand mutation 32 of 34 killed (6 of them after tests were added), 1
equivalent (the empty-list early return), 1 redundant check removed. The review (one cycle, fresh context)
found two crashes reachable once step 4 writes the field - a value written
"(blank)" (an Excel pivot's label) and a column listed twice - and two
risks: a stage 1 column (`line_class`, `__flag_*`) split as the user's, and
float residue in a change. All fixed, tests first, mutated (5 of 6 killed,
the survivor an equivalent `.strip()`, removed); its scoped review found the empty field written into
every cleaning report under 4.3 - now not written while empty. Further
look-alike spellings of "(blank)" and the +4.6 s re-read on Online Retail II
are recorded in 8D. Regression: Thach's Kaggle run and both Online Retail II
demo runs, stages 2-5 on HEAD and on step 2: diagnosis, forecast, report.json
and report.html identical; metrics.json differs only by its version and the
empty list.

Decisions made alone in step 2: a breakdown with fewer than 2 non-blank
values is withheld (it splits nothing); a value written "(blank)" withholds
the whole breakdown (rather than renaming either bucket); a column stage 1
added is never split.

## 8. The dashboard block (D7) and the test plan

report.json 2.10, additive: `dashboard`:

```
dashboard: {
  state: "compared" | "not_compared" | "blocked",
  tiles: [ { id, label, unit, now: str, now_value: float | int | None,
             was: str | None, change: str | None, direction: "up"|"down"|"same"|None,
             reason: str | None, notes: [NoteCode] } ],
  not_shown: [str],                      # why a tile is absent (section 2)
  caution: [str],                        # front.caution, under the tiles
  widgets: [ { id, kind: "chart"|"text", chart: "line"|"waterfall"|"bars"|"diverging"|"parts"|None,
               placed_by: "named"|"size"|"fallback", size: float | None,
               title: str | None, bars: [ {label, now, was, now_text, was_text, is_blank} ],
               caption: [str], notes: [NoteCode] } ]   # text widgets point at front.*
}
```

The contract refuses: a tile not in D2's list or out of order; a tile with no
figure (but Sales); a "was" beside an incomplete previous month; a widget id
twice; a chart widget whose bars are not its source's figures; a size that is
not its source's contribution; an order the rule does not give (the rule is
one function in `contracts/`, read by stage 5 and the contract).

**Symptom tests first** (each must fail on today's code):

| Test | Fails today because |
|---|---|
| a date+amount-only file: Review refuses the plan (required fields) - pinned as the known limit | (passes - a guard) |
| the minimal shape's tiles are Sales, Lines, Average line value - never Customers, never Return rate | no tiles |
| no tile is empty or zero-filled; AOV null -> no tile, its reason under the row | no tiles |
| the previous month incomplete -> no "was", no change, the reason | no tiles |
| Kaggle: the waterfall comes first (B1), the summary after every chart | no order |
| S4: the customers widget first (C2); S6: the waterfall first (rule 4); ORII: the trend first (rule 7) | no order |
| the caution lines stand under the tiles (S10) | the caution is inside the summary |
| products: never "(not a product)" or "Other" as a bar | no widget |
| a breakdown with 13 values is withheld and not drawn | no field |
| breakdown members sum to core revenue (Kaggle Location: 25,469.50 + 20,823.00 = 46,292.50) | no field |
| the AI's answer naming a column off the list -> no breakdown; a timeout -> no breakdown; never a retry | no step |
| Shopify shape: order-level fields on first lines only -> not eligible | no eligibility |
| a mapped category is never offered; a numeric column with 3 values never offered | no eligibility |
| report.html and the page draw the same tiles and widget order from report.json; the page formats no tile figure | no block |
| no FRONT_BANNED word in any tile, widget title or caption | no block |
| no front sentence points at "section N" | "section 2", "section 5" today |
| with a breakdown drawn, "cannot know" never says sales are not split by it | the line is fixed text today |

Process (CLAUDE.md 3.6): stage 2's figures and the eligibility + AI step are
logic producing conclusions - method first, tests first, mutation, doubt
review (step 2, step 4); stage 5's assembly and the page are display -
failing tests first, one review cycle, mutation on the order rule and the
tile rules (steps 3, 5).

**As built (step 3, 2026-10-14).** `contracts/report_dashboard.py` (the
order rule `order_widgets`, the tile and widget rules - one copy for stage 5
and the contract), `stages/report/dashboard.py` (tiles, the tie, the order),
`dashboard_widgets.py` (each chart widget's condition, size and bars),
`html_dashboard.py` and `html_bars.py` (report.html); report.json 2.10
(CONTRACTS 9, 10). The sales tile prints sentence A's own figures
(`front_summary.sales_change`, one copy with sentence A). The front's
number pointers became names ("the chart "Where the change came from"",
"the estimate under "Next month"", the appendix's "under "What to do next""),
and "What this report cannot know" names the columns sales are split by when
a breakdown is drawn. report.html keeps the front's section ids for its parts
(`summary`, `change`, `checked`, ...). Step 3's review (one cycle) found the products widget false on the Kaggle demo
file - stage 3's members are the LARGER products only (2% of the previous
month or 30 orders), so "Products whose sales moved most" left out bigger
moves (Item_19_MILK +1,280) - and six more: a negative value drawn like a sale,
a blocked report naming a split, the category chart as parts of a whole (its
blank lines are out), the sales figure cut at 390 px with a currency, SVG
charts unreadable on a phone and silent to a screen reader, and a loose
contract. Fixed: the products widget is now stage 2's own list,
`products.top_products` ("Products with the most sales in <month>", no
movement, no size, no tie - no product cause is tied); ties read what a widget
draws; the bar charts are HTML on one scale holding zero; the category chart
is always bars; a blocked report names no split; a withheld breakdown says why
under the tiles; the contract holds every printed figure to its value, the
arrow to the printed pair, tile notes, the sizes and the tie's rules.
**Hidden by the stop rule:** the scoped review of those fixes found the new
products widget (stage 2's top products) naming DOTCOM POSTAGE - a suggested
charge, unanswered - as Online Retail II's top product without its
"(suggested: charge, not confirmed)" mark (LINE_TAXONOMY 4.5): a fabrication
on a demo file, so the products widget is not shown at all (a test proves it
absent on the three runs); the appendix keeps the product tables. Recorded,
not fixed (no further cycle): a blocked report's split line ("This version
does not split sales that way" while a split was chosen); the customers line
when no split is drawn; the link colour rule's scope; contract checks still
open (bars and sizes against their sources, the customers and sales tiles
against the bridge and sentence A, widget notes). Tests
first (19 symptom tests red before
the block existed); 23 older stage 5 assertions moved to the new layout or
wording, none removed (the list is in the overnight report, for Thach's F2
sign-off); the frontend fixtures regenerated.

## 9. Decisions made alone and open questions

Decisions made alone (each open to Thach's veto):
- **D-1** the text widgets come after every sized widget (the rule's letter).
- **D-2** the trend's size is the shown change.
- **D-3** "few blanks" = at most 10%; a column whose values read as numbers or
  dates is never eligible.
- **D-4** a separate AI call, not inside the schema call (5.2).
- **D-5** no retry for the breakdown call.
- **D-6** with no suggestion the user may still add columns.
- **D-7** the date+amount mock shows the closest shape v1 can analyse.
- **D-8** the caution lines move under the tiles (3.3a; S10).
- **D-9** the customers tile only from the bridge's count (Q4), so not
  shown when the change is not split.
- **D-10** tile arrows in the neutral colour (no verdict colour).
- **D-11** products widget: named product members only; "Other" in the
  caption; "(not a product)" not drawn.
- **D-12** the new plan item is numbered 9D as Thach asked; the existing 9D
  ("What I learned") becomes 9E.

Open questions:
- **Q1** keep the summary where the rule puts it (after the charts), or pin it
  under the tiles?
- **Q2** a date+amount-only file (Stripe, Z-reports) cannot be analysed in
  v1 (required fields, frozen). Accept as a known limit, or reopen?
- **Q3** columns with more than 12 values (Online Retail II's Country: 38) are
  never a breakdown, so the demo gets none. Allow "the 8 largest + all
  others" for such a column?
- **Q4** Shopify's first-line-only order fields fail "few blanks" - correct
  by the rule; fill them down the order in stage 2 (a new definition)?
- **Q5** a transaction-type-like column (Square's Event Type: Payment /
  Refund) is eligible; keep it eligible (the user removes it), or exclude
  headers naming a status/type?
