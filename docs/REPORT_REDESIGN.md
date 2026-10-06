# Report redesign for a shop owner

Status: **design approved by Thach with his answers of 2026-10-05**
(section 10). The build follows section 11, one step a session; step 1
(stages 2 and 3's new fields) approved the same day. Phase 9's deploy waits
for the redesign.

Why: Thach's manual test found report.html accurate but unreadable for its
real audience, a shop owner with no analytics background. His decisions
D1-D7 are recorded with their reasons in PROJECT_PLAN Phase 9 (item 9R),
and his answers to this file's questions in section 10 and in 9R. Nothing
in this file is a decision Claude made alone unless it says so: every
other choice was made by Thach or is forced by an existing rule (named
beside it).

## 0. Sources and what was checked

| Run | How it was obtained | Compared months |
|---|---|---|
| Kaggle `retail_store_sales.csv` | Thach's manual run `cd4d3c8f-53de-4332-8044-85f68f981e01`, read as written (copied to the scratchpad first: run files are deleted 24 h after upload) | 2024-11 -> 2024-12 |
| Online Retail II, classed | the demo sample (`scripts/demo/online_retail_ii.py`) re-run through stages 1-5 with the tenth run's stored user-confirmed plan `0a...0001` (Thach's line classes), no AI call (stage 1 executes the stored plan; strategy step off) | 2011-10 -> 2011-11 |
| Online Retail II, unanswered | the same, with the stored plan `0a...0002` (no line-class answer) | 2011-10 -> 2011-11 |

The two demo runs ran one after the other, nothing else heavy beside them
(memory guard: 4.7 and 5.5 GB free at start; peaks 718 MB and 731 MB).

**Thach's residual arithmetic, verified.** On the Kaggle run stage 3
already writes the price-per-unit lever: `tree.lever.level2` has
`units_per_order` +2,858.84 and `price_per_unit` **-2,646.13**, which sum to
the AOV lever's +212.71. With level 1 (customers 0.00, frequency +4,712.29)
the four bars sum to **+4,925.00**, exactly the change (46,292.50 -
41,367.50). Today's report shows only the hypotheses B1 (96%) and B2 (58%),
so the price lever never appears and the shares add to 154%.

**Thach's Q20 arithmetic, verified.** The Kaggle checklist's "Matches the
figures" amounts add to 4,712.29 + 2,858.84 + 1,274.15 = 8,845.28, more
than the change of 4,925.00: the calendar (T1) and the levers (B1, B2) are
different splits of the same change and overlap. The price effect appears
twice with two numbers: the waterfall's average price per item -2,646.13
(the lever: net sales over items, every product) and the checklist's
cheaper products -1,479.65 (P2: the product lens's mix effect over the 118
products sold in both months, on sale lines). Section 1.3 words both.

## 1. The front section, in Thach's approved order

Conventions used in every wording below:

- `{x}` is a field rendered by stage 5. Money is formatted as today (two
  decimals, thousands separators); a month `2024-12` is written "December
  2024". **Stage 5 computes no figure** (CONTRACTS 11). Every number below
  is a field of a contract file, and a field that does not exist yet is
  marked **NEW** with the stage that writes it (section 2).
- Amounts carry the confirmed currency as its ISO code, "AUD 46,292.50"
  (D6, Q8; section 6). Both runs here are "Not stated" (neither file names
  a currency: section 6.6), so amounts are shown bare, with the one
  sentence "Amounts are in your file's currency."
- **No adjective verdict on a month or a change in the front section**
  (Thach, Q3): never "usual", "unusual", "normal", "abnormal", "ordinary",
  "bigger than usual". A comparison is stated as a fact with its figure.
  Why: ADR-0007 forbids unusualness verdicts in v1, and a lay reader reads
  "bigger than usual" as one. ("Typical month-to-month change" names a
  figure - stage 3's median movement - as in Thach's own wording, and is
  allowed. "Ordinary" joins the list as the same kind of word: a decision
  made alone, applying Q3's reason; section 10.)
- When `period.previous_complete` is false, sections 1-4 show this month's
  figures and `previous_incomplete_reason` only, with no comparison, change
  or bar (CONTRACTS 11's standing rule). When `trust.verdict` is `caution`,
  one line opens section 1: "Some of this month's data may be missing or
  wrong - read these figures with care." It is followed by the check's own
  message. When `blocked`, sections 1-4 are replaced by: "The data cannot
  support conclusions: {trust.checks[blocked].message}".

### 1.1 Section 1 - The 30-second summary (three sentences, then the chart)

**Rule (Thach):** sentence A = this month's sales and change; sentence B =
the comparison with the shop's own history, as a fact with its figure;
sentence C = the main reason in words like "matches the figures", never
"caused by". When the change is inside the history's range, B opens the
summary (Q3).

"Inside" is decided by stage 3, never by stage 5:

- inside = `headline.movement.season.band == "consistent"`, or
  `headline.movement.singled_out == false` (under `factor` x the median
  month-to-month movement);
- outside = `singled_out == true` with no consistent season;
- cannot say = `singled_out == null` (history too short).

Sentence B, one wording per case (Q3b: one wording for every consistent
band, no new field):

| Case | Sentence B |
|---|---|
| season `consistent` | "This change is in line with last year's: {season.expected_change_pct}% last year, {change_pct}% this year (one earlier year to compare with)." - "years" > 1 says "({years} earlier years to compare with)" |
| `singled_out` false | "That is less than {factor} times this shop's typical month-to-month change (about {typical_pct}%)." - factor 2 written "twice" |
| `singled_out` true | "That is more than {factor} times this shop's typical month-to-month change (about {typical_pct}%)." |
| `singled_out` null | "The file's history is too short to compare this change with this shop's earlier month-to-month changes." (after A) |
| season `shortfall` / `excess` | stage 3's own season sentence, unchanged (it states the gap as a fact) |

The signals (`signals[]`, yoy limits) are NOT used for this sentence:
CONTRACTS 11 says none is a verdict in v1.

Sentence C by `headline.rule`:

| rule | sentence C (code-written) |
|---|---|
| 6 or 5 (a cause named) | "The figures match {plain statement of the named hypothesis}: {its own figures}." |
| 7, season consistent | "Nothing else stands out: the change is in line with last year's, so none of the checks below is named as the reason." |
| 7, size test (not singled out) | "No single reason stands out." |
| 7, history too short | "With this little history, no single reason can be picked out." |
| 7, season shortfall/excess | (B already says it) "No single reason is named." |
| 4 (offsetting moves) | "Underneath, {orders} and {average order value} moved a lot in opposite directions and largely cancelled out." + by NEW `headline.hedge`: `seasonal` -> "This may be seasonal: treat it as a pointer, not a finding."; `plain` -> "A shift like this can happen in any month: treat it as a pointer, not a finding." |
| 2 (missing days) | "The change matches days with no sales at all - missing data, or days the shop was closed (the file cannot tell which)." |
| 1 | (the blocked line above replaces the section) |

D5's sentence follows the summary, once: **"Sales here means the money
customers paid (before any costs). It is not profit: the file has no cost
data."** When the file maps no cost column (always in v1), the second half
is fixed. When currency is "Not stated", it adds: "Amounts are in your
file's currency."

**Kaggle (rule 6, B1; outside, so A then B then C):**

> Sales in December 2024 were 46,292.50, up 4,925.00 (+11.9%) on November
> 2024 (41,367.50). That is more than twice this shop's typical
> month-to-month change (about 4.9%). The figures match customers ordering
> more often: 25 customers placed an order in each month, and together
> they placed 343 orders, up from 308.

Fields: `core.revenue_current`, `core.revenue_previous`,
`core.revenue_change_pct`, **`tree.lever.bridge.shown_change`** (Thach,
Q22: every front number agrees with the chart to the cent; the exact
`core.revenue_change` is the appendix's; with no bridge drawn, Q24), `headline.movement.singled_out`, `.factor`, `.typical_pct`,
`headline.rule`, `headline.hypothesis_id`; for B1 the customers who placed
an order from `bridge` (Q4: the front never shows the active-customer
count) and `core.orders_*`. For each other id the template names its own
fields (section 3).

**Online Retail II, classed (rule 7, season consistent; inside, so B first):**

> This change is in line with last year's: 27.1% last year, 27.2% this year
> (one earlier year to compare with). Sales in November 2011 were
> 663,315.58, up 141,755.41 (+27.2%) on October 2011 (521,560.17). Nothing
> else stands out: the change is in line with last year's, so none of the
> checks below is named as the reason.

Fields: `headline.movement.season.expected_change_pct` (27.10),
`.change_pct` (27.18), `.years` (1), `.band`; the rest as Kaggle.

**Online Retail II, unanswered (the same wording, Q3b):**

> This change is in line with last year's: 39.1% last year, 27.1% this year
> (one earlier year to compare with). Sales in November 2011 were
> 654,527.09, up 139,466.56 (+27.1%) on October 2011 (515,060.53). Nothing
> else stands out: ...

**The chart, directly under the summary** (Q15): title **"Sales by month
(before any costs)"**. Whole months only, as today. **D7's sentence
directly under it** (section 7).

### 1.2 Section 2 - Where the change came from (the waterfall)

**Rule (Thach):** a waterfall from last month to this month; every lever
drawn, including price per unit; the bars sum exactly to the change.

Bars, left to right: start = last month's sales; then customers who placed
an order; orders per customer; items per order; average price per item;
end = this month's sales. With `orders_basis == "lines"` the labels say
lines (as `DecompositionCard.tsx` and headline rule 4 already do). With the
two-factor level 1 (`orders*aov`, no customer column) the bars are Orders
and the order-value pair.

**Kaggle (all four levers):**

| Bar | Was -> is | Adds |
|---|---|---|
| November 2024 sales | | 41,367.50 |
| Customers who placed an order | 25 -> 25 | 0.00 |
| Orders per customer | 12.32 -> 13.72 | +4,712.29 |
| Items per order | 5.44 -> 5.80 | +2,858.84 |
| Average price per item | 24.70 -> 23.25 | -2,646.13 |
| **December 2024 sales** | | **46,292.50 (+4,925.00)** |

Caption: "Read left to right: November's sales, then what each part added
or took away, ending at December's sales. The bars add up exactly to the
change. 'Worth' amounts split the effect of things that moved
together, so read them as sizes, not exact causes."

**Where B2 is refused, the order value is one bar** (Thach, Q1). On both
Online Retail II runs stage 3 still writes `level2` (units per order
-82,344.30, price per unit +40,353.31, classed), but it REFUSES the
basket-size hypothesis B2 (`inconclusive`, `refund_lines_prev` 579 /
`_cur` 482): "level 2 counts refunded units against the basket, so basket
size cannot be separated from return lines ... until level 2 has a refund
factor of its own" (`hypothesis_evidence_lever.py`, Thach 2E). Drawing
"items per order: -82,344.30" would state, as a fact, the very reading
stage 3 refuses, on the demo dataset - the FABRICATE shape (CLAUDE.md 3.6).

**Online Retail II, classed (three bars; the split withheld):**

| Bar | Was -> is | Adds |
|---|---|---|
| October 2011 sales | | 521,560.17 |
| Customers who placed an order | 609 -> 756 | +127,578.73 |
| Orders per customer | 1.48 -> 1.63 | +56,167.67 |
| Average order value | 576.95 -> 537.53 | -41,990.99 |
| **November 2011 sales** | | **663,315.58 (+141,755.41)** |

Under it: "Average order value is shown as one bar. Both months had
returns, and returns make the split into items per order and price per
item unreliable, so it is not drawn."

**Online Retail II, unanswered:** customers 609 -> 756 +125,915.39; orders
per customer 1.50 -> 1.64 +51,213.50; average order value 562.91 -> 527.84
-37,662.33; = +139,466.56.

**Rounding: largest remainder in stage 3** (Thach, Q2). Rounded to cents,
the unanswered run's four level-1+2 terms add to 139,466.57, against a
change of 139,466.56. A bar shown to the cent is a rounding of an exact
Shapley term, and stage 5 may not adjust a figure. So stage 3 writes the
bars it draws, each rounded to the cent by the largest-remainder rule so
the shown bars sum exactly to the shown change. The exact terms stay in
`tree.lever.level1/level2` and the appendix.

**Customers (Thach, Q4).** The bar's customers are those who placed an
order (609 -> 756: customers with a sale line, `lever.period_totals`). The
KPI's active customers (634 -> 779; a customer who only returned goods
counts) stay in the appendix's KPI table with their definition. The front
section names only "customers who placed an order".

Fields: **NEW `tree.lever.bridge`** and `tree.lever.bridge_withheld`
(stage 3; shape in section 2). `bridge.revenue_previous` /
`revenue_current` are the end bars; their shown cents are the start and end
the bars sum between.

### 1.3 Section 3 - What was checked (a plain checklist)

Groups, each written by stage 5 from `hypotheses[].id`, `.verdict`,
`.contribution` and `.against_the_change` (vocabularies and figures in the
contract: no figure computed). The words per id are in section 3:

- **Matches the figures** - `supported` (and `partial`: "a small part")
  moving with the change;
- **Pulled the other way** - `against_the_change` true, |share| >= the
  partial bar;
- **Checked - not the reason** - `ruled_out`;
- **This file cannot show it** - `not_testable`, and B2 when refused
  (inconclusive for refund lines).

T3 and C4 are inconclusive in every v1 run by design (ADR-0007; C4 off).
They appear only in the appendix, which keeps them true without asking a
shop owner to read a v1 switch.

Under headline rule 7 (no cause named), the first group is titled **"Moved
this month, but not singled out"** (Thach, Q16), with stage 3's
`hypotheses_note` in plain words: "Because the change is in line with last
year's, none of these is called the reason; each line says what moved."

**The amounts overlap, and the list says so** (Thach, Q20). Directly under
the first group's lines, one fixed sentence (no figure but the change
field): **"These amounts are measured in different ways and overlap, so
they do not add up to the change ({bridge.shown_change}). The chart in
section 2 is the one that adds up."**

**Prices are worded as part of the chart's price bar** (Q20). P1 and P2
never stand as separate amounts beside the waterfall's average-price-per-
item bar. Where the split is drawn they name that bar and its figure. Where
B2 is refused they name the average-order-value bar, which holds the
price per item. P2's amount is said to be measured product by product, so
it is not read as a part to add.

**Kaggle:**

> Matches the figures
> - Customers ordered more often: 343 orders, up from 308 - worth about
>   +4,712.29.
> - Bigger baskets: 5.80 items per order, up from 5.44 - worth about
>   +2,858.84.
> - The calendar: December's length and mix of weekdays - worth about
>   +1,274.15.
> - Last year, sales also rose between November and December (34,900.00 to
>   41,046.00). That is last year only - one earlier year - so it does not
>   show a regular pattern.
> - A small part: products sold in only one of the two months. Sales of
>   products sold in December but not in November (+9,101.00) and the other
>   way round (-8,835.50) nearly balanced.
>
> These amounts are measured in different ways and overlap, so they do
> not add up to the change (4,925.00). The chart in section 2 is the one
> that adds up.
>
> Pulled the other way
> - Inside the chart's average price per item (-2,646.13): customers chose
>   cheaper products among those sold in both months. Measured product by
>   product, that shift is about -1,479.65 - a different measure, not an
>   amount to add to the chart.
>
> Checked - not the reason
> - Data: no days without sales, no prices recorded at the wrong scale, no
>   rows flagged during cleaning.
> - Customers: no new customers, none stopped buying, none came back after
>   a break - the same customers placed orders in both months.
> - Prices: products sold in both months kept their prices, so the chart's
>   average price per item (-2,646.13) moved with what customers bought,
>   not with price changes.
> - Returns: none in either month. Discounts: none booked as separate
>   lines (a discount already taken off a price cannot be seen - the file's
>   "Discount Applied" column is not read in this version).
> - One product or category: the change was not concentrated in one.
> - Stockouts: no best-selling product stopped selling in a way that
>   suggests it ran out.
>
> This file cannot show it
> - Charges such as postage: no line was marked as a charge in Review.

(The P1 line's "so ... moved with what customers bought" is written only
when P1's contribution prints as 0.00: with every price unchanged, the
average price per item can move only through which items were bought. A
P1 that is ruled out but not zero gets the line without that clause.)

Fields: `hypotheses[]` (id, verdict, contribution, against_the_change -
the last read today by stage 5 only: its row gains **FE**),
`tree.customers.new/lapsed/resurrected`, `tree.returns.*`,
`tree.products.new_products/discontinued_products`, the bars from
`bridge`, `core.revenue_change`, and **NEW `year_ago`** (stage 3; today
T2's 34,900.00 and 41,046.00 exist only in `hypotheses[T2].evidence`, whose
keys CONTRACTS 11 says no consumer relies on). T2's wording is fixed: "last
year only - one earlier year" (Thach; scope freeze 8D: no new statistic).
R2 never says "launched" or "discontinued" (Thach): a product with no sale
in one month is "sold in only one of the two months".

**Online Retail II, classed (rule 7):**

> Moved this month, but not singled out (because the change is in line
> with last year's, none of these is called the reason)
> - More customers placed an order: 756, up from 609 (see section 2).
> - Customers ordered more often - worth about +56,167.67.
> - Inside the chart's average order value: prices of products sold in
>   both months went up. Measured product by product, about +36,878.80 - a
>   different measure, not an amount to add to the chart.
> - More customers came back after a break - worth about +36,744.87.
> - Fewer returns: 13,951.29 returned, down from 41,074.29 - worth about
>   +27,123.00.
> - The calendar - worth about +12,069.22.
> - Postage and other charges paid by customers rose - worth about
>   +11,500.70.
> - Last year, sales also rose between October and November (518,318.50
>   to 658,764.09) - last year only, one earlier year.
>
> These amounts are measured in different ways and overlap, so they do
> not add up to the change (141,755.41). The chart in section 2 is the one
> that adds up.
>
> Checked - not the reason
> - Data checks, new customers, customers who stopped buying, a shift
>   to cheaper products, discounts, products sold in only one of the two
>   months, one product or category, stockouts.
>
> This file cannot show it
> - Basket size (items per order): returns make it unreliable this month.

**Online Retail II, unanswered:** the same, except prices +19,443.98 and a
shift to pricier products +9,246.49 (both partial: "a small part", both
worded inside the order-value bar), fewer returns +24,535.13, and charges
"This file cannot show it: no line was marked as a charge in Review".

### 1.4 Section 4 - What to do next

The suggested actions of section 4 (D4), every sentence code-written
since Thach's option (d) (section 4): each item shows **the figure it rests
on**, **the action**, **why** and **what to watch next month**. Under
headline rules 1-4 and 7, a blocked diagnosis, or an incomplete previous
month, no claim is selected (Thach, Q10); the section reads: "No action is
suggested: no single reason stands out in these figures. Next month,
compare sales with the estimate in section 5." Both demo runs (rule 7) read
so. On the Kaggle run three actions are listed (section 4.1).

### 1.5 Section 5 - Next month

Front wording (Thach, Q12, Q13): "likely between X and Y (the real figure
should land in this range about 8 months in 10)". The sentence on how the
range is built moves to the appendix. The part-month is named by its dates
only.

> **Kaggle:** Next month (January 2025): about 43,835.33, likely between
> 38,893.14 and 49,405.54 (the real figure should land in this range about
> 8 months in 10). It is based on the last three full months, the latest
> counting most, and assumes no seasonal pattern. Your file already has
> sales for 1 to 18 January 2025; that part-month is not compared with
> this estimate.

> **Online Retail II, classed:** December 2011: about 401,224.73, likely
> between 313,360.52 and 513,725.48 (the real figure should land in this
> range about 8 months in 10). It follows the seasonal pattern of the last
> two years - the fewest years that can show one - so the shape is less
> certain than more years would make it. [Notes beside the forecast, as
> today: the unconfirmed-suggestions note.] Your file already has sales for
> 1 to 9 December 2011; that part-month is not compared with this estimate.
> **Unanswered:** about 384,784.50, between 305,880.67 and 484,042.07.

Appendix sentence (Q12): "The range is an 80% interval worked out from
how far off this method's past estimates were: their root mean square
times Student's t." (`stages/predict/forecast.py` `band`.)

Fields: `forecast.revenue[0]` (point, low, high, confidence),
`forecast.method` (worded by its shape: weighted average / with a season),
`season_years`, `season_note` (reworded once in plain words; one copy
in stage 5), `history_note`, the revenue notes beside it (CONTRACTS 11's
standing rule), and NEW report.json `partial_months` (section 7). "8 months
in 10" words `confidence` 0.8.

### 1.6 Section 6 - What this report cannot know

> - **Profit.** The file has no costs, so these figures are sales, not
>   profit.
> - **Marketing and promotions.** The file has no campaign data.
> - **Competitors, weather and events.** Nothing outside the file is used.
> - **How many people visited or browsed.** The file records only
>   purchases.
> - **Stock.** This version analyses sales, not stock levels.
> - **Sales by channel, payment method or country.** This version does
>   not split sales that way. [Kaggle: the file has "Payment Method" and
>   "Location" columns; they were not used.]
> - **Rows left out.** [Kaggle] 12,575 rows were read and 11,362 used:
>   1,213 rows with no value in "Item" were left out during cleaning, as
>   the plan you approved in Review said. Rows left out are in no figure,
>   and a gap they leave cannot be seen. [Online Retail II: 460,859 rows
>   read and used; no row was left out. The lines classed in Review as fees
>   or adjustments are left out of sales - the appendix lists them.]

The "why" is worded from the cleaning report's own fields, one line per
change entry that dropped rows (`changes[]` with `rows_affected` > 0), by
its action (the transform table in `stages/ingest/transforms.py`):

| Action | Line |
|---|---|
| `drop_rows_missing` | "{rows_affected} rows with no value in "{column}" were left out" |
| `remove_exact_duplicates` | "{rows_affected} rows that repeated another row exactly were left out" |
| `fix_negative` with `strategy` "drop" | "{rows_affected} rows with a negative value in "{column}" were left out" |

Flagging and marking actions drop nothing and get no line.

Fields: `not_testable[]` (by id, reworded in plain words: X1-X7; the code
reasons "not canonical", "the 2D finding", "P4" move to the appendix),
`data_quality.rows_in/rows_out`, cleaning_report `changes[]` (action,
column, params, rows_affected) - **NEW report.json `rows_left_out`**
(stage 5 copies the dropping entries, so the page reads one copy),
`products.velocity_reason`, `trust.limitations`, `non_product[]`.

### 1.7 Section 7 - Technical appendix (collapsed)

One `<details>` element, closed by default: "Technical details (for an
analyst)". It keeps, unchanged in substance (D3: moved, never deleted):
the file's row counts and cleaning changes; the trust badge and its three
check messages and limitation; the KPI table (orders, active customers
with their definition, average order value, return rate) with their
notes; the monthly table with the partial month and its sales so far (the
only place that figure is shown: Q13); "How to read these figures"; **every
hypothesis tested, today's full table** (id, statement, verdict,
contribution, share, rule, evidence) with `hypotheses_note`; the
not-testable list with today's reasons; **"Where this month sits" (the
limits table) with its method text**; the lines in no figure; the
forecast's method, table and band, with the range's construction (Q12);
the exact lever terms (levels 1 and 2 and the orders x AOV pair - so the
demo's withheld split stays visible to an analyst, with B2's refusal beside
it); provenance. The appendix keeps today's labels ("Revenue" in a field's
own name included) and adds one line at its top: "In this appendix,
'revenue' is the same figure as 'sales' above."

**The "AI narration is unavailable" line is removed** (Thach, Q14: 3F
closes). The code-written front section is the narration, so nothing is
missing. Today the line reads an AI step that failed. diagnosis.json keeps
`ai_findings` and `model_used` null, as every v1 run writes them now.
report.json keeps `narration` null, its status `not_in_v1` (2.8; Thach,
Q21), and report.html and the page show nothing for it. The appendix's KPI
table prints revenue's exact change (`core.revenue_change`, 2.8's KPI
`change`) beside the percentage (Q22).

## 2. New fields (all additive; CLAUDE.md 3.7)

| Field | Writer | Why no consumer can do without it |
|---|---|---|
| `metrics.core.revenue_change` | stage 2 (step 1) | the change amount in sentence A and the checklist's overlap sentence; today only inside `headline.message` text |
| `diagnosis.tree.lever.bridge` + `bridge_withheld` | stage 3 (step 1) | the waterfall: which bars (B2's refusal is stage 3's rule), cent amounts that sum exactly |
| `diagnosis.year_ago` | stage 3 (step 1) | T2's two figures; today only in evidence keys no consumer relies on |
| `diagnosis.headline.hedge` | stage 3 (step 1) | rule 4's seasonal or plain hedge, chosen by stage 3; today only in message text |
| `cleaning_report.currency` (+ `confirmations.currency`, `profile` measure) | stage 1 | D6 (section 6) |
| `report.json`: `currency`, `layer_1_numbers.partial_months`, `rows_left_out`, `front` (the front section's code-written sentences and bars, so report.html and the page print one copy) | stage 5 | D6, D7, section 1.6, one wording for both readers |
| `forecast.json`: `actions` (+ `actions_status`) | stage 4 | D4 (section 4) |

Step 1's shapes as first proposed (the final ones, with `shown_previous`,
`shown_current` and `not_to_the_cent`, are in section 12):

```
metrics.core.revenue_change: float          # revenue_current - revenue_previous, written as revenue is

diagnosis.tree.lever.bridge: {
  revenue_previous: float, revenue_current: float,   # the lever's own month totals
  change: float,                                      # their difference, exact
  shown_change: float,                                # cents: printed current - printed previous
  bars: [{factor, value_prev, value_cur, contribution, shown}],
                                                      # shown: cents by largest remainder; sum(shown) == shown_change
  aov_split: bool,                                    # items/price drawn
  aov_split_withheld: Literal["refund_lines", "aov_unchanged",
                              "net_units_not_positive"] | None
} | None
diagnosis.tree.lever.bridge_withheld: Literal["zero_orders", "month_not_positive"] | None
                                                      # exactly one of bridge / bridge_withheld is null

diagnosis.year_ago: {previous: YYYY-MM, current: YYYY-MM,
                     revenue_previous: float, revenue_current: float} | None
diagnosis.year_ago_reason: str | None                 # null exactly when year_ago is not

diagnosis.headline.hedge: Literal["seasonal", "plain"] | None   # set exactly under rule 4
```

`month_not_positive`: a compared month that nets zero or below makes the
multiplicative split's terms change sign. Stage 3's masked-shift alert
already refuses such a month for this reason (`lever._masked_shift`). The
bridge follows the same reading rather than drawing "more customers pulled
sales down" - see section 12.

Each new metrics/diagnosis field gets its CONTRACTS 11 row in the session
that adds it. `hypotheses[].against_the_change` gains reader FE. Schema
versions bump as section 10 of CONTRACTS says.

## 3. Old-to-new wording glossary

Front section words (the appendix keeps the old ones, defined there).

| Today | Front section | Note |
|---|---|---|
| Revenue | Sales (before any costs) | D5; JSON names unchanged |
| Revenue by month | Sales by month (before any costs) | D5 |
| Hypothesis | (a line in "What was checked") | |
| Verdict | (the group the line sits in) | |
| supported | matches the figures | |
| partial | a small part | |
| ruled out | checked - not the reason | |
| moved against the change | pulled the other way | |
| inconclusive / not testable | this file cannot show it | |
| lever lens / lens / lever | (removed) | the waterfall shows the levers |
| share = contribution / D, "96% of the change" | "worth about +4,712.29" | money, never a share: shares overlap |
| contribution | worth about | the list says the amounts overlap (Q20) |
| AOV | average order value (what an order brought in) | |
| frequency | orders per customer | |
| units per order | items per order | |
| price per unit | average price per item | |
| active customers | customers who placed an order (the bridge's count) | Q4; active customers in the appendix only |
| yoy | compared with the same month last year | |
| limits, within the limits, centre | (appendix only) | ADR-0006/0007 |
| "within this shop's usual range", "bigger than usual", normal, ordinary | the comparison as a fact: "more than twice this shop's typical month-to-month change (about 4.9%)"; "in line with last year's: X% last year, Y% this year" | Q3; ADR-0007 |
| headline | (the summary) | |
| Data trust: trusted / caution / blocked | (nothing) / "Some of this month's data may be missing or wrong - read with care" / "The data cannot support conclusions" | |
| Days with no sales explain the change (D1) | days without sales | |
| Prices shifted uniformly (D2) | prices recorded at the wrong scale (for example pence for pounds) | |
| Flagged rows concentrated (D3) | rows flagged during cleaning | |
| The calendar explains the change (T1) | the calendar: the month's length and mix of weekdays | |
| Last year's change between the same two months (T2) | last year, sales also rose/fell between the same months - last year only, one earlier year | Thach: no new statistics |
| The change is routine variation (T3) | (appendix only) | dormant in v1 |
| New-customer revenue changed (C1) | new customers | |
| Revenue lost to lapsed customers (C2) | customers who stopped buying | |
| Returning-customer revenue (C3) | customers who came back after a break | |
| Customers moved between segments (C4) | (appendix only) | off in v1 |
| Customers bought more often (B1) | customers ordered more/less often | |
| Baskets got bigger (B2) | bigger/smaller baskets (items per order) | |
| Like-for-like prices changed (P1) | prices of products sold in both months, worded inside the chart's price bar | Q20 |
| Sales mix shifted (P2) | customers chose cheaper/pricier products, worded inside the chart's price bar, "measured product by product" | Q20 |
| Returns changed (P3) | returns | |
| Discounts and other deductions (P4) | discounts | |
| Charges paid by customers (P5) | postage and other charges paid by customers | |
| Concentrated in one product or category (R1) | one product or category | |
| Products were launched or discontinued (R2) | products sold in only one of the two months | Thach: no "launched/discontinued" |
| A top product may have run out of stock (R3) | a best-seller that may have run out - check the shelf | stage 3's own wording kept |
| Marketing and promotions (X1) ... Sales channel (X7) | section 6's plain list | code reasons to the appendix |
| "(the 2D finding)", "not canonical", "P4" in reasons | (appendix only) | |
| weighted moving average ... weights 1, 2, 3 | based on the last three full months, the latest counting most | |
| the 80% band, from the method's own past errors | likely between X and Y (the real figure should land in this range about 8 months in 10) | Q12; construction in the appendix |
| The AI narration is unavailable | (removed) | Q14 |

A test (section 9) fails if any of these words is in the front section:
hypothesis, verdict, supported, ruled out, lens, lever, share,
contribution, AOV, yoy, year-over-year, limits, inconclusive, revenue,
caused, launched, discontinued, usual, unusual, normal, abnormal,
ordinary, "bigger than usual".

## 4. Suggested actions, written by code (D4; Thach's option (d), 2026-10-06)

**No AI in v1's recommendations** (Thach, Q50 (d)). Five review cycles
over two designs - 4B's three, step 4's two - found the same thing: free
text written by the AI cannot be closed by a banned-word list ("every
fourth visit", "a fiver off" passed; 9 of 38 sound sentences were refused).
So code selects the claims, picks each one's action from the catalog below
by the claim's kind and the direction its own figure moved, and writes the
why and the watch line. Every sentence is code-written and tested. The AI
recommendation step moves to v2 (PROJECT_PLAN Backlog), starting from this
measured finding. Stage 4 makes no AI call; `STRATEGY_AI_ENABLED` and the
strategy AI path are removed (Q53).

### 4.1 Which claims (code, deterministic; Thach Q10, Q11, Q52, Q54)

- Only when `headline.rule` is 5 or 6 (a cause named), the diagnosis is not
  blocked and the previous month is complete. Otherwise no claim, and
  section 4 says why (1.4).
- From the hypotheses `supported`/`partial` moving with the change, plus
  those against the change (`against_the_change`) at |share| >= the
  supported bar (0.20); never the data checks (D1-D3: a data problem is
  fixed, not acted on in the shop), the time checks (T1-T3: the calendar is
  no lever), C4 (dormant), or R2 (Q52: no watch line next month can follow
  products sold in only one of two closed months).
- Ranked: the headline's causes (`named`) first, then by |contribution|,
  the catalog's order on a tie. A claim whose catalog has no entry for the
  way its figure moved (the figure unchanged as printed, or a lost-customer
  term that is no loss) is dropped before the ranking is cut to three, and
  the rest are numbered K1, K2, K3.
- Kaggle: K1 = P2 (customers chose cheaper products - pulled the other
  way). B1 and B2, which the headline names, are no claims since step 4's
  scoped review (section 12).

### 4.2 What each claim carries

| Part | Writer | Kaggle K1 (P2) |
|---|---|---|
| The figure it rests on (`fact`) | code: the checklist's own line (`shared/claim_lines`) | "Inside the chart's average price per item (-2,646.13): customers chose cheaper products among those sold in both months. Measured product by product, that shift is about -1,479.65 - a different measure, not an amount to add to the chart." |
| The action | code: the catalog, by kind and direction | "Show a pricier alternative next to the cheaper products customers chose." |
| Why | code: the catalog | "Customers chose cheaper products among those sold in both months; offering a step up may win some of them back." |
| What to watch next month | code, by kind (the value the claim rests on) | "Next month, check: the average price per item (23.25 this month; 24.70 the month before)." |

**The direction** is the way the claim's own figure moved, read from the
two figures' order (never a new figure): the money terms (C1-C3, P3, P5)
this month against the month before; the sign of the measured amount for
P1 (prices went up or down) and P2 (pricier or cheaper); for R1, which
stage 3 writes with no amount, the sales change's. A refund that fell is
"down" whatever it did to sales. R3 has one entry. **B1, B2 and P4 are no
claims** (moved out by step 4's scoped review, Thach's stop rule: section
12).

### 4.3 The catalog (the exact sentences)

No sentence holds a digit, a word of `FRONT_BANNED`, "order", "visit" or
"basket" (so it reads true on a file with no order id - the orders-basis
rule), or a movement word against its direction.

| Kind and direction | Action | Why |
|---|---|---|
| P1 up | Watch whether customers keep buying at the new prices. | Prices of products sold in both months went up; how customers respond shows whether the new prices hold. |
| P1 down | Check that the price cuts were intended and are bringing in extra buyers. | Prices of products sold in both months went down; a price cut pays only when it brings extra buyers. |
| P2 up | Keep the pricier products customers chose easy to find. | Customers chose pricier products among those sold in both months; keeping them easy to find may keep that going. |
| P2 down | Show a pricier alternative next to the cheaper products customers chose. | Customers chose cheaper products among those sold in both months; offering a step up may win some of them back. |
| C1 up | Welcome new customers and give them a reason to come back. | Sales from new customers rose this month; a welcome may turn some of them into regular customers. |
| C1 down | Look at how new customers find the shop, and make that easier. | Sales from new customers fell this month; an easier way in may help them find you. |
| C2 up | Contact customers who have not bought for a while, with a reason to come back. | Sales lost to customers who stopped buying rose this month; a reminder may bring some of them back. |
| C2 down | Keep in touch with customers who have not bought for a while. | Sales lost to customers who stopped buying fell this month; keeping in touch may keep it that way. |
| C3 up | Thank customers who came back after a break. | Sales from customers who came back after a break rose this month; a thank-you may keep them coming. |
| C3 down | Contact customers who have not bought for a while. | Sales from customers who came back after a break fell this month; a reminder may bring some of them back. |
| P3 up | Check the most returned products for faults, sizing or how they are described. | Refunds for returned goods rose this month; a common reason behind them may be one the shop can fix. |
| P3 down | Keep an eye on returns to see whether the lower level holds. | Refunds for returned goods fell this month; watching them shows whether that lasts. |
| P5 up | Check that postage and other charges are clear before customers pay. | Postage and other charges paid by customers rose this month; clear charges avoid surprises when customers pay. |
| P5 down | Check that postage and other charges are still collected where they should be. | Postage and other charges paid by customers fell this month; a missed charge may mean the shop pays it itself. |
| R1 up | Look at the product or category named in the technical section and see what changed there. | The change was concentrated in one product or category, so that is where to look first. |
| R1 down | Look at the product or category named in the technical section and see what changed there. | The change was concentrated in one product or category, so that is where to look first. |
| R3 down | Check the shelf and the stock records for the products listed under the stockout check in the technical section. | Their sales stopped in a way consistent with a stockout - verify on the shelf. |

R3's fact, the checklist's line, is worded with stage 3's own words (Q54):
"At least one best-selling product stopped selling - consistent with a
stockout, verify on the shelf - worth about ..." (stage 3 may find more than
one). R1 has no measured amount (stage 3 writes none): its direction is the
sales change's. A why never re-reads a figure as a behaviour it does not
measure (orders per customer is no "regular customers bought more"; items
per line is no "bought together"); B1, B2 and P4, for which no such wording
held in every case, are no claims (section 12).

### 4.4 forecast.json 2.1's three states (Thach)

- **"list"**: the code-written actions - or empty when no claim is
  selected (section 4 then says why, 1.4).
- **"suppressed"**: claims were selected but none has a catalog entry for
  the way its figure moved - nothing to act on. Section 4: "No action is
  suggested: the figures above that moved have no action this report can
  suggest."
- **"off"**: only for a run where stage 4 did not produce actions (the new
  stage 4 never writes it). Section 4: "Suggested actions are not available
  for this report: run the forecast again." (A forecast before 2.1: "...its
  forecast was made before they existed - run the forecast again to see
  them.")
- `actions_model` is null: code writes every action. 4B's `model_used`,
  `recommendations`, `do_not_do` stay null (Q42, Q53).

### 4.5 Cost and model

None: stage 4 makes no AI call, so no smoke test is needed (Thach, Q50).

### 4.6 3F closes (Thach, Q14 (a))

The code-written front section is the narration, and since Q50 (d) the
suggested actions are code-written too. Stage 3 makes no AI call:
`ai_findings` and `model_used` stay null (as every v1 run writes them
today), the narration prompt (`prompts/root_cause.md`) is not built, and
AI_PIPELINE 7.9 records the closure. The appendix's "AI narration is
unavailable" line goes (1.7, Q21).

## 5. What does not change

- No JSON field is renamed or removed; `revenue_*` keeps its name (D5,
  CLAUDE.md 3.7). Every change in section 2 is a new field.
- No stage 3 rule changes: the verdicts, the headline rules, the size test,
  the season bands and B2's refusal stand as they are. The redesign only
  words them and adds fields that carry what stage 3 already decides.
- No consumer computes a figure; the AI writes no number (CLAUDE.md 3.2).
- Every note keeps its place by its code (CONTRACTS 11).

## 6. Currency (D6)

**The principle (Thach, 2026-10-05).** The two errors are not equal.
Reading a currency that is not there (a SKU "TOP-001" as the Tongan pa'anga)
fabricates a label or blocks a correct file. Finding nothing only means
Review asks the user, which is harmless. So: detect only on strong
evidence; anything doubtful is "not found" and the user is asked. Blocking
mixed currencies uses one simple rule, not lists. Nothing is ever summed
across two currencies silently. Thach's Q26-Q31 (section 10) apply it; where
6.1-6.5 below differ, they and section 12 (as built) win.

### 6.1 Rules (stage 1 code only, on the RAW file, in profiling)

**Code only, no AI step in v1** (Thach, Q7b). The rules below cover every
evidence type D6 lists, and an AI guess could not be verified beyond them.
This narrows D6's "the AI may propose": in v1 it does not.

Evidence that **counts** (one is enough, all must agree):

| Kind | Rule | Shown in Review |
|---|---|---|
| A currency column | a column whose HEADER names a currency (`currency`, `ccy`, `curr`, `cur`, `devise`, `moneda`, `waehrung`/`währung`, `valuta`, `tien te`/`tiền tệ`, case-insensitive, as a whole word) and whose every non-blank cell is an ISO 4217 code (closed list, upper-cased after trimming) | "AUD, from column Currency" |
| A symbol in amount cells | the amount columns (mapped `unit_price`, and any numeric column the plan reads as money) carry one unambiguous Unicode Sc symbol (£ GBP, € EUR, ₹ INR, ₩ KRW, ₫ VND, ₺ TRY, ₽ RUB, ₴ UAH, ₪ ILS, ₱ PHP, ฿ THB, ₦ NGN, ...), counted by today's `_strip_currency` reading | "GBP, from the £ in column Price" |
| A currency in an amount header | a token of an amount column's header equal to an ISO code: `Price (AUD)`, `amount_gbp`, `TotalEUR`; split on non-letters and case changes. Codes that are English words (ALL, TOP, CUP, PEN, MOP, BOB, SOS, GEL, BAM, LAK, MAD, PAB ...) count only when written upper case | "AUD, from the header Price (AUD)" |

Evidence that **does not count**:

- a Country column, or any country value (Online Retail II sells to France
  and Germany in GBP);
- a bare `$`: it narrows to the dollar currencies. Review offers them first
  (USD, AUD, CAD, NZD, SGD, HKD, ...), then the full list, where the pesos
  are (Thach, Q9); nothing pre-selected;
- `¥` (yen and yuan): asked like a bare `$`, narrowed to JPY and CNY,
  nothing pre-selected (Thach, Q5);
- a column of ISO codes whose header does not name a currency ("CAD" could
  be a product code) (Thach, Q6);
- any AI guess (Q7b).

### 6.2 Review (always shown, D6)

- Found: pre-selected, with where it was found; the user can change it.
- Not found: the user picks from a closed list - ISO 4217 active codes,
  the common ones first (GBP, EUR, USD, AUD, CAD, ...), and **"Not stated"**.
  **Default: "Not stated"** (never assumed): the run proceeds when the
  question is left unanswered, and the report says so.
- Narrowed (`$`, `¥`): the narrowed list first, then the full list and
  "Not stated".

### 6.3 More than one currency: block, option A (Thach, Q7)

Detected as: a currency column with more than one code; more than one
unambiguous symbol across the amount cells; a header code that disagrees
with a symbol; a `$` or `¥` beside another symbol. **v1 blocks**: Review
shows "Your file has amounts in more than one currency ({code} on {n}
lines, {code} on {n} lines). DataClarity cannot add different currencies
together. Split the file by currency and upload each part." The plan does
not run. Never summed silently.

The options not taken, kept for the record: B (analyse one currency, the
other lines dropped in stage 1 with a change-log line) goes to 8D and the
Backlog. C (convert with exchange rates: an outside data source) and D
(one report per currency: the run model changes) were not proposed for v1.

### 6.4 Where it is stored, and who reads it

- `profile.json` (stage 1 profiling): a NEW `currency` measure - the
  evidence found (kind, column, code or narrowed list, example cell), or
  mixed with the codes and line counts.
- `plan_final.json` `confirmations.currency`: the user's answer (an ISO
  code or `"not_stated"`), recorded like `number_formats`.
- `cleaning_report.json` `currency`: `{code: str | None, source:
  "column" | "symbol" | "header" | "user" | "not_stated", evidence:
  str | None}`.
- Stage 5 already reads `cleaning_report.json`. It writes report.json's
  NEW `currency` block, and report.html and the page format amounts from
  it. Stages 2, 3 and 4 do not read it (amounts are amounts).
- **Display: the ISO code everywhere, "AUD 46,292.50"** (Thach, Q8: one
  rule, never ambiguous). With "Not stated": no code on any amount, and
  the one sentence "Amounts are in your file's currency."

### 6.5 Test files (one per case; built in code, tiny, under tests/)

| File | Content | Expected |
|---|---|---|
| `cur_column_aud.csv` | `Currency` = AUD on every row | AUD, from column Currency |
| `cur_column_lower.csv` | `currency` = " aud " | AUD (trimmed, upper-cased) |
| `cur_symbol_gbp.csv` | Price `£2.50` | GBP, from the £ in Price |
| `cur_symbol_eur_suffix.csv` | Price `2,50 €` | EUR |
| `cur_header_paren.csv` | header `Price (AUD)` | AUD, from the header |
| `cur_header_snake.csv` | header `amount_gbp` | GBP, from the header |
| `cur_bare_dollar.csv` | Price `$2.50` | not found; dollars offered first; **never AUD or USD pre-selected** |
| `cur_yen.csv` | Price `¥300` | not found; JPY and CNY offered first; nothing pre-selected |
| `cur_country_only.csv` | Country = France, Germany, United Kingdom | **not found** |
| `cur_country_codes.csv` | Country = FR, DE, GB | **not found** |
| `cur_word_header.csv` | headers `all_prices`, `Top Price` | **not found** (ALL, TOP not read) |
| `cur_code_column_no_header.csv` | column `Code` = CAD, CAD | **not found** |
| `cur_mixed_column.csv` | Currency = GBP, EUR | blocked, the message names both with their line counts |
| `cur_mixed_symbols.csv` | Price `£2.50`, `€3.00` | blocked |
| `cur_header_symbol_conflict.csv` | `Price (EUR)` with `£` cells | blocked |
| `cur_none.csv` | the Kaggle shape | not found |
| Online Retail II sample (slow suite) | Country column, plain prices | not found |

### 6.6 The two demo files

Kaggle: no currency column, no symbol, headers "Price Per Unit" and "Total
Spent" - **not found**. Online Retail II: a Country column (not evidence),
plain prices - **not found**. Both default to "Not stated" unless the user
picks one.

## 7. The partial month (D7)

The chart keeps whole months only (it already does: both charts end on the
last complete month). The NEW sentence directly under it, written by stage
5 from `period` through `shared/periods` (the one definition of a complete
month: CONTRACTS 11 "Months"), into report.json's NEW
`layer_1_numbers.partial_months` (`[{period, covers_from, covers_to,
position: "first" | "last"}]`). **Dates only** (Thach, Q13): the
part-month's figure stays in the appendix's monthly table, because printing
it beside full months invites the comparison the sentence warns against.

> **Kaggle:** January 2025 is not in the chart: the file covers only 1 to
> 18 January 2025. Comparing part of a month with full months would
> mislead, so it is left out.

> **Online Retail II (both runs):** December 2011 is not in the chart: the
> file covers only 1 to 9 December 2011. Comparing part of a month with
> full months would mislead, so it is left out.

`covers_from` is the later of the month's first day and `data_start`;
`covers_to` the earlier of its last day and `data_end`. A file that starts
mid-month gets the same sentence for its first month. A file inside one
month has no chart (as today). Section 5's forecast line names the same
dates, also without the figure.

## 8. The frontend screens

Nothing on the page changes before its own step (section 11, step 5).

| Screen | Same jargon or content today | Proposal |
|---|---|---|
| Insights, KPI cards | "Revenue", "Average order value", "Return rate"; trust badge "Data trust: trusted" | open with the same front section, from report.json's NEW `front` block (one copy of the wording, as notes already work: CONTRACTS 11 "Notes by code"); the KPI cards move under the appendix toggle |
| Insights, "Where the revenue change came from" (`DecompositionCard.tsx`) | **draws level 2 where stage 3 refuses B2** (the demo: "Units per order -82,344.30"); the orders x AOV pair beside it | draw `bridge` instead. **A blocker for deploy** (Thach, Q17): fixed with the redesign, kept on 9R until then |
| Insights, causes (`CausesSection.tsx`) | the Hypothesis / Verdict table, "About these verdicts", "What this data cannot test" with code reasons ("not canonical", "the 2D finding") | the checklist; the table behind a "Technical details" toggle |
| Insights, "Revenue by month" (`RevenueChartCard.tsx`) | title; no partial-month sentence | "Sales by month (before any costs)" and D7's sentence |
| Insights, forecast and recommendations | "80% band", method text; "The AI recommendations are switched off" | section 5's sentence; section 4 |
| Results (stage 1) | no analysis jargon; "Rows in / Rows out", "What ran" | unchanged, plus the currency answer shown with the other answers (6.2) |
| Review (stage 1) | - | the currency question (6.2) and the mixed-currency block (6.3) |

## 9. Test plan (symptom tests first; each fails on today's code)

Run on the Kaggle run's files (fixtures copied from this run, as the real
answers were) and on small built frames. Each new test is run on today's
code before the code is written, and must fail there.

| Test | Fails today because |
|---|---|
| **Step 1 (stages 2 and 3)** | |
| metrics `core.revenue_change` == revenue_current - revenue_previous (Kaggle 4,925.00) | no field |
| the bridge's shown bars sum to `shown_change`, to the cent (Kaggle: 0.00 + 4,712.29 + 2,858.84 - 2,646.13 = 4,925.00) | no bridge |
| the price-per-item bar is in the bridge when the split is allowed (Kaggle -2,646.13) | no bridge |
| the split is withheld, one order-value bar, `aov_split_withheld` "refund_lines", when B2 is refused for refund lines (demo shape) | no bridge |
| largest-remainder cents: the unanswered run's terms (sum to the cent 139,466.57) give shown bars summing to 139,466.56 | no field |
| `bridge_withheld` "zero_orders" when level 1 is null; "month_not_positive" when a compared month nets zero or below | no field |
| `year_ago` holds T2's pair (Kaggle 2023-11 34,900.00 -> 2023-12 41,046.00); null with its reason when T2 has no year ago | no field |
| `headline.hedge` "seasonal"/"plain" under rule 4, matching the message's sentence; null under every other rule | no field |
| the consumer contract: the new rows, types and vocabularies | rows not yet added |
| **Later steps** | |
| no jargon word (section 3's list, Q3's verdict words included) in the front section, outside `<details>` | today's page has them |
| the appendix is one closed `<details>` and holds all 20 hypothesis ids, the limits table and the method text (nothing deleted) | no appendix |
| "Sales (before any costs)" in the front, chart titled "Sales by month (before any costs)", D5's not-profit sentence present; report.json field names unchanged | "Revenue" |
| no currency code on any amount when "Not stated", and "Amounts are in your file's currency" present | the sentence fails |
| with GBP confirmed, amounts read "GBP 1,234.00" | no currency |
| partial-month sentence under the chart naming the month and its dates; **no part-month figure anywhere in the front section** | absent |
| the chart holds whole months only | passes today: a regression guard |
| summary order: inside -> B first (demo); outside -> A first (Kaggle); B states the factor and the typical change as figures | no summary |
| the checklist's overlap sentence is present under its first group with the change figure; P1/P2 lines name the chart's price bar | absent |
| the summary never says "caused", "because of", "explains" | today's headline says "explanation" |
| T2's line says "last year only"; R2's never says "launched" or "discontinued" | absent / today's statement |
| "Rows left out" names the dropping action and column (Kaggle: 1,213 rows with no value in "Item") | absent |
| no "AI narration is unavailable" line | today's page prints it |
| stage 1: one test per file of 6.5 - "a bare $ is not read as AUD", "a Country column is not read as a currency", mixed currencies block | no detection |
| recommendations (option (d)): every catalog sentence passes the front's banned words, holds no digit, no "order", "visit" or "basket", and no movement word against its direction; a refund that fell is never "rose"; no claim under rules 1-4 and 7, blocked, or an incomplete previous month; every fact sentence is the checklist's own line | the step is off and unstructured |
| frontend: the same no-jargon and bridge tests in Vitest; the page never draws a refused split | the page draws it today |

Process per CLAUDE.md 3.6: the new stage 3 fields and the claim selection
are conclusion-producing code - method first, tests first, mutation,
doubt-review cycles. Stage 5's assembly and the page: failing tests first
and one review cycle, mutation on logic. Stage 1's currency detection is
logic: full process.

## 10. Questions and Thach's answers

**Answered by Thach, 2026-10-05:**

1. **Q1 Waterfall on refund months** - one order-value bar with its
   sentence where B2 is refused. Accepted.
2. **Q2 Rounding** - largest remainder in stage 3. Accepted.
3. **Q3 Summary** - when inside, the range sentence opens the summary. But
   no adjective verdict in the front section ("usual", "unusual", "normal",
   "abnormal", "bigger than usual"): the comparison is stated as a fact
   with its figure. Reason: ADR-0007 forbids unusualness verdicts in v1,
   and a lay reader reads "bigger than usual" as one. Those words join the
   jargon test. **Q3b** - one wording for every consistent band, no new
   field.
4. **Q4** - the front section names only "customers who placed an order";
   active customers stay in the appendix's KPI table with their
   definition.
5. **Q5** - the yen/yuan sign is asked like a bare `$` (JPY/CNY, nothing
   pre-selected).
6. **Q6** - an ISO-code column whose header does not name a currency is
   not evidence. Accepted.
7. **Q7** - option A (block with the clear message) for v1; option B to
   8D and the Backlog. **Q7b** - code only, no AI step for currency in v1:
   the code rules cover every evidence type in D6, and an AI guess could
   not be verified beyond them. This narrows D6's "the AI may propose".
8. **Q8** - the ISO code everywhere ("AUD 46,292.50"): one rule, never
   ambiguous.
9. **Q9** - dollar currencies first, then the full list (the pesos are in
   the full list).
10. **Q10** - no action under rules 1-4 and 7, blocked, or an incomplete
    previous month, with the code line. Accepted.
11. **Q11** - at most 3 claims, no D or T, "pulled the other way"
    included. Accepted.
12. **Q12** - the front says "likely between X and Y (the real figure
    should land in this range about 8 months in 10)"; how the range is
    built moves to the appendix.
13. **Q13** - dates only in the front section, in the chart sentence and
    in section 5; the part-month figure stays in the appendix's monthly
    table only. Reason: printing it beside full months invites the
    comparison the sentence warns against.
14. **Q14** - (a): 3F closes. The code-written front section is the
    narration; the AI writes only the recommendations.
15. **Q15** - the chart directly under the summary. Accepted.
16. **Q16** - "Moved this month, but not singled out" stays in the front
    section. Accepted.
17. **Q17** - the page's refused split is fixed with the redesign (the
    bridge replaces it), kept on 9R as a blocker: fixed before deploy.
18. **Q18** - the new field homes. Agreed.
19. **Q19** - Sonnet 5 (`MODEL_REASONING`, ADR-0003).
20. **Q20** (Thach's own finding) - the checklist's amounts overlap and a
    reader will add them (Kaggle: 4,712.29 + 2,858.84 + 1,274.15 =
    8,845.28 against a change of 4,925.00), and the price effect appears
    twice with two numbers (-2,646.13 and -1,479.65). Designed in 1.3 with
    no new figure: the overlap sentence under the first group, and P1/P2
    worded as part of the chart's price bar. Arithmetic verified (section
    0). Also from his review: section 6's "Rows left out" says why rows were
    left out, from the cleaning report's own fields (1.6).

**Decisions made alone in applying these answers** (each open to Thach's
veto):

- "Ordinary" joins Q3's banned words (the same kind of verdict), so rule
  4's plain hedge reads "A shift like this can happen in any month" in the
  front section. Stage 3's own message keeps its wording for the appendix.
- "Typical month-to-month change" stays (Thach's own wording; it names
  stage 3's median movement, a figure).
- The P1 line's "moved with what customers bought" clause is written only
  when P1's contribution prints as 0.00 (1.3).

**Answered by Thach, 2026-10-05 (second round):**

21. **Q21** - `narration_status` gains `not_in_v1` (the vocabulary grows,
    additive - report.json 2.8); report.html and the page show no line for
    it. Reason: "unavailable" reads as a failure, but the step was removed
    by design.
22. **Q22** - the front section prints `bridge.shown_change` everywhere,
    sentence A included, so every front number agrees with the chart to the
    cent; the exact `core.revenue_change` goes to the appendix (report.json
    2.8: the revenue KPI's `change`, printed in the KPI table).
23. **Q23** - no cross-model review. Instead: the bridge must never take
    the diagnosis down (item 1, section 12), then a scoped fresh-context
    review of the cycle-3 fix that had not been reviewed.
- Step 1's five decisions made alone: accepted. The file sizes
  (contracts/diagnosis.py ~1,050 lines, stages/diagnose/lever.py ~490): debt
  in 8D, split after deploy, not now.

**Answered by Thach, 2026-10-05 (third round):**

24. **Q24** - with the bridge withheld, sentence A prints the exact
    `core.revenue_change`. Reason: with no chart drawn there is nothing for
    the sentence to agree with to the cent.
25. **Q25** - yes, permanently: a value added to a closed vocabulary bumps
    the MINOR version only (CONTRACTS 10, amended). Reason: every consumer
    is updated in the same session, and a file of the earlier minor
    carrying the new value is refused, so no reader meets an unknown value
    silently.
26. **Q26** - yes: currency evidence is read only from the plan's money
    columns and a column whose header names a currency (6.1's first
    wording), at execute. Reason: three review cycles each found a new kind
    of column misread when every column was read.
27. **Q27** - do not refuse an untied "$" beside one dollar code found
    elsewhere: pre-select that code with where it was found; Review always
    asks the user to confirm. Reason: refusing a common layout (the
    currency written on an order's first line only) blocks a correct file;
    a pre-selection the user confirms fabricates nothing.
28. **Q28** - no alias list. In a currency-named column, blanks and "-",
    "none", "n/a" (trimmed, any case) are empty; two or more distinct text
    values (trimmed, upper-cased) block, the message listing each value
    with its lines ("Euro: 300 lines, US Dollar: 20 lines"); exactly one
    value that is an ISO code is pre-selected; one that is not ("Euro") is
    no evidence - Review asks and shows it as a hint. Reason: one simple
    rule, not lists; a name the user wrote is shown back, never translated.
29. **Q29** - a cell of that column that reads as a number or a date is
    "unreadable", not a value: GBP plus one "0" pre-selects GBP and Review
    says "1 cell could not be read"; GBP plus EUR (with or without the "0")
    blocks. Reason: nothing is ever summed across two currencies silently.
30. **Q30** - no text-symbol list (kr, zł, Rs, ...) in v1: not detected
    means the user is asked. Mixed text symbols inside amount cells: a known
    limit in 8D (not a common export shape).
31. **Q31** - yes, one fourth review, scoped to what changes for Q26-Q30
    and the seven fixes. Safety valve, decided now: if it still finds a
    fabrication on a common export shape, cut the scope instead of a fifth
    cycle - no automatic detection at all, Review always asks the currency,
    only the Q28/Q29 block rule on a currency-named column kept.

**Open:** none from this round.

**Thach, 2026-10-05 (fourth round):** step 2's nine decisions made alone
(section 12) - all accepted. Steps 3 and 4 approved, in that order, each its
own commit group.

**Answered by Thach, 2026-10-05 (fifth round):**

32. **Q32** - apply every listed fix, then ONE more review scoped to the
    fixes only; if it finds a fabrication on a demo file or a common export
    shape, stop again and report. The stop rule from now on: within a step,
    a review's findings are fixed and the fixes get one scoped review; a
    fabrication on a demo file or a common export shape found there stops
    the step uncommitted. Never further cycles alone.
33. **Q33** - a new additive diagnosis field, written by stage 3, naming the
    hypothesis ids behind rule 5 and rule 6's offsetting case; stage 5 words
    sentence C from it. No generic sentence; no parsing of stage 3's text.
    Reason: the figures match something named - the reader is owed which.
34. **Q34** - C3 and P3 worded as money, because their fields are money:
    "Sales from customers who came back after a break rose: X, up from Y";
    "Refunds for returned goods fell: X, down from Y". Every other checklist
    line checked the same way: the words match the field's unit.
35. **Q35** - yes, required by CLAUDE.md 3.3a: a note's link appears
    wherever its figure is shown (sections 2, 3 and 5 included).
36. **Q36** - "Suggested actions are not available for this report."
    ("switched off" is untrue there).
37. **Q37** - caution and blocked lines worded by each check's id and status
    in plain words; stage 3's message as written goes to the appendix
    (CLAUDE.md 3.7: read by code, never by sentence).
38. **Q38** - yes, without the word "median" in the front: "In the N earlier
    years, sales typically rose X% between these months." The median stays
    in the appendix.
- **Root cause (Thach's addition):** every figure the report renders carries
  its unit (money / count / ratio) from its field's contract, never guessed
  by the formatter; the currency code goes on money alone. A test over the
  whole front block and the appendix of the three real runs, GBP set: no
  count or ratio carries a code, every money figure does.

**Open:** none from this round.

**Thach's pattern (2026-10-06):** every fabrication found in step 3 had one
cause - stage 5 guessed what a stage 3 result means (which month a check is
about, what a check proves, orders or lines, how many years a season reads).
The fix is the unit fix's: the meaning is DATA written by stage 3, never
inferred by stage 5; where wording a result needs meaning the data does not
carry, the front says less (suppress, never fabricate).

**Answered by Thach, 2026-10-06 (sixth round):**

39. **Q39** - yes: stage 3 writes, for each check that cautions or blocks,
    which month it is about (`trust.checks[].month`: current / previous /
    coverage), additive (diagnosis 18.7). Stage 5 words the check from it;
    a file without it (before 18.7) gets the check without a month, never
    this month. *Why:* the message said which month, but a message is read
    by code only (CLAUDE.md 3.7).
40. **Q40** - yes: stage 3 writes `headline.offsetting`; `named` becomes
    required for a tie. *Why:* stage 5 inferred the case from signs and read
    a one-sided case as "the figures match".
41. **Q41** - drop "no regular pattern" entirely: it is a judgement, and it
    contradicts sentence B when the season reads several years. T2's line
    states the fact only: "Last year alone, sales rose X% between these
    months." (Built with the two amounts instead of X%: `year_ago` holds no
    percentage, and stage 5 computes none - section 12.)
42. **Q42** - keep "not available". Never show the old-format (pre-2.1) AI
    suggestions anywhere, the appendix included. *Why:* that is the
    unchecked free-text format v1 switched off because it fabricated
    numbers.
43. **Q43** - yes: the banned words are enforced only in stage 4's checks
    (the AI's text is refused and retried there); stage 5 checks only
    code-written text, in tests. "median" is added to the banned list.
- **D2:** word what D2 tests ("No sudden price jump across all products."),
  never "wrong scale".
- **Orders or lines:** every "orders" in the front section reads
  `orders_basis` (the existing rule).
- **D1-D3 in the front:** all three ok - ONE line, "Data checks: no problem
  found (details in the technical section)"; one cautions or blocks - its
  line as in Q37; the per-check detail lives in the appendix.
- **Safety valve (decided now):** if the scoped review of these changes still
  finds a fabrication on a demo file or a common export shape, do not fix
  and review again: move the kind of line that fabricates to the appendix
  only, test that it is absent from the front, and commit.

**Open:** none from this round (decisions made alone: section 12).

**Open (step 4, stopped by its scoped review - section 12):**

49. **Q49** - a claim's `direction` is the sign of its effect on SALES
    (refunds falling adds to sales: "up"), not the way its own measure moved
    (the refunds fell). The direction check and the prompt read it as the
    measure's movement, so "Refunds rose" passed beside "Refunds ... fell"
    (the scoped review's fabrication on a common shape: returns). (a) drop
    the direction check and the field from the AI's input, refusing every
    movement word (the prompt already says "do not restate how anything
    moved"); (b) give the AI the measure's own movement as a separate field
    stage 4 reads from the two figures' order (no new figure); (c) other?
50. **Q50** - the AI's free text is checked against closed word lists; each
    review finds more that slip through ("visiting more often" on a file
    with no order id, "every fourth visit", "a fiver off", "a pair", ordinals,
    synonyms of certainty and of a verdict on a month). A list cannot close
    this. (a) **the AI picks, per claim, one action from a short code-written
    catalogue by kind and writes only why** - the action can then never
    fabricate; (b) keep free text but accept only words from an allow-list
    (a small plain vocabulary); (c) keep the lists, add the review's words,
    and rely on the smoke test and Thach's reading. Recommendation: (a) for
    the action; the why under (c) or dropped.
51. **Q51** - the checks also refuse sound answers (in a hand-written set of
    38 Kaggle answers, 9 refused - "busy weeks", "a couple of add-ons",
    "always", "keep a record") and the retry message does not name the word
    that matched, so a retry can repeat it and the list is suppressed. If
    the lists stay (Q50 (b) or (c)), name the matched word in each problem
    and narrow the verdict and certainty lists?
52. **Q52** - R2's watch line names the two compared months ("sold in
    December but not in November"), a closed figure next month cannot
    change. Word it "sales of products sold in one month and not the other,
    month on month", without figures?
53. **Q53** - stage 4's free-text step (4B: `ai_strategy.recommend`,
    `strategy_checks`, `strategy_render`, `strategy_impact`,
    `prompts/strategy.md`) is no longer called (Q42). Remove it, with its
    tests, in its own session, or keep it?
54. **Q54** - R3 (a best-seller that may have run out) as a claim: its
    natural action is a reorder, which the stock rule refuses (v1 has no
    stock). Leave R3 out of the claims (as D and T are)?

**Answered by Thach, 2026-10-06 (seventh round, step 3's follow-up):**

44. **Q44** - fix both figure-and-word mismatches this session, failing
    tests first, then one scoped review. *Why:* a printed figure and the word
    beside it must agree, however rare the case.
45. **Q45** - "Data checks passed (details in the technical section)".
    *Why:* "no problem found" stood beside days with no sales that a season
    explains.
46. **Q46** - yes: "The change a year earlier between the same months".
47. **Q47** - confirmed (it is Q43).
48. **Q48** - no generic opening line: each caution line names its own month
    from `trust.checks[].month`.

**Open (step 3's follow-up, its scoped review - section 12; none on a demo
file or a common shape):**

55. **Q55** - figure-and-word disagreements left (contrived values only): a
    near-zero change printed with more decimals than were checked ("0.03%
    ... 10.0% ... at least 4 times ... about 2.5 points": printed 9.97); no
    precision up to 4 agreeing, the bound word still said (stage 3's own
    `season_headline._places` searches to 10 places and drops the bound);
    a typical printed "0.0"; the month-to-month typical 0.049 printed "0.05"
    beside "+0.1%" and "more than twice". Share stage 3's decimals function
    through `shared/` and drop the bound word where no precision agrees?
56. **Q56** - one change printed two ways: with a season stated, sentence A
    takes the month-to-month test's decimals ("+12.05%") while sentence B
    prints the season's ("12.0%"); and the KPI table prints one decimal
    ("+12.0%") beside A's "+12.05%". Print A at the season's decimals when B
    is the season's, and the KPI table's percentage as A prints it?
57. **Q57** - a season "in line" with no yardstick (demo_unanswered as
    shipped): "This change is in line with last year's: 39.1% last year,
    27.1% this year" - stage 3's band (a 12-point gap under twice the
    typical 8.6) but the reader sees only the gap. Add the yardstick ("within
    twice this shop's typical year-on-year difference, about 8.6 points")?
58. **Q58** - "at least" printed where the printed gap is strictly more (the
    stored gap exactly on the bound, the printed one above it): true, but
    not Q44's pairing. Say "at least" whenever stage 3's gap is on the
    bound, whatever the print?
59. **Q59** - where a data check could not run (inconclusive, not
    applicable): "Data checks passed, except those this file cannot run
    (details in the technical section)" - a decision made alone; "passed ...
    except" can read as those having failed. Your wording?

**Answered by Thach, 2026-10-06 (eighth round, step 4 - Q49-Q54):**

50. **Q50** - option (d): **no AI in v1's recommendations.** *Why:* five
    review cycles over two designs (4B's three, step 4's two) found the same
    thing: free text written by the AI cannot be closed by a banned-word
    list ("every fourth visit", "a fiver off" pass; 9 of 38 sound sentences
    are refused). Option (a) still leaves the why as free text. In (d) code
    selects the claims (as built), picks the action from a code-written
    catalog by claim kind and direction, and writes the why and the watch
    line: every sentence code-written and tested. The AI recommendation step
    moves to v2 (PROJECT_PLAN Backlog), with this measured finding as its
    starting point. Consequences: forecast.json 2.1 keeps its three states -
    "list" code-written, "off" only for a run where stage 4 did not produce
    actions, "suppressed" for a claim selection that yields nothing to act
    on; `STRATEGY_AI_ENABLED` and the strategy AI path removed (Q53); no
    smoke test for step 4.
49. **Q49** - void under (d): no AI sentence is checked for its direction.
    The catalog is keyed by the direction the claim's own figure moved, so a
    refund that fell is worded "fell" by construction (tested). *Why void:*
    the question was how to check an AI's movement words.
51. **Q51** - void under (d): no AI answer is refused or retried. *Why
    void:* the false refusals and retry messages belonged to the AI checks,
    which are removed.
52. **Q52** - R2 out of the claims. *Why:* no watch line next month can
    follow products sold in only one of two closed months.
53. **Q53** - yes: the old free-text 4B code and its prompt are deleted (git
    history keeps them). *Why:* its known fabrication paths must not stay in
    a portfolio repo.
54. **Q54** - keep R3, worded with stage 3's own words ("consistent with a
    stockout, verify on the shelf"), code-written.

## 11. The build, step by step

1. **Stage 2 `revenue_change`; stage 3 `bridge`, `year_ago`, `hedge`**
   (full process) - **approved and DONE 2026-10-05; as built in section 12.**
2. Stage 1 currency (6; Q5-Q9, Q26-Q31 answered) - **approved and DONE
   2026-10-05; as built in section 12.**
3. Stage 5: the front section, the appendix, the partial month, the rows
   left out, the currency (failing tests first, one review cycle) -
   **approved 2026-10-05; built, reviewed, fixed (Q33-Q38), stopped
   twice; Thach's pattern applied (Q39-Q43), the scoped review's one
   fabrication on a common shape moved to the appendix (safety valve):
   committed (section 12).**
4. Stage 4 structured actions (full process; a real call only with
   Thach's approval). **First built with the AI; stopped by its scoped
   review (Q49-Q54); rebuilt as Thach's option (d) - code-written actions,
   no AI; its scoped review moved B1, B2 and P4 out of the claims (stop
   rule); committed (section 12).**
5. The frontend (section 8), including the deploy blocker of Q17.

Each is its own session, grouped for commits as CLAUDE.md says.

## 12. As built

### Item 1 - the bridge never takes the diagnosis down (2026-10-05)

Thach's item 1: every review cycle of step 1 had found a rounding edge that
crashed stage 3 and lost the whole diagnosis.json. Checked first, on step
1's code: a bridge failing to build (an exception), refused by its own
model, a helper raising, or valid on its own but refused by the whole
file's checks (the refund-split tie) - all four lost the diagnosis (the
tests in `tests/stages/diagnose/test_bridge_never_fails_the_diagnosis.py`,
run red on 4fe249f). Fixed - suppress, never fabricate:

- `lever.lever_from_totals` builds the Lever with its bridge inside one
  handler: any exception there (logged) gives the Lever without it,
  `bridge_withheld: "failed_checks"` (diagnosis.json 18.5; the vocabulary
  grown, minor by Thach's ruling, Q25). The Lever without the bridge is
  built outside the handler, so a failure that is not the bridge's still
  raises.
- `assemble.diagnose`: a DiagnosisContract refused while it carries a
  bridge is built again without it (`failed_checks`, logged); refused again,
  the FIRST refusal is raised - the bridge was not its cause. So the
  contract's own validators never turn a bridge problem into a whole-file
  rejection of stage 3's output.
- Every other field of diagnosis.json is written exactly as without the
  failure (each test compares the whole file, the bridge aside). A failure
  elsewhere (a hypothesis step) and a file refused for something else (a
  mark on a product the file never names) still raise. An 18.4 file
  carrying `failed_checks` is refused.
- Tests first (4 red); 5 mutants, all killed.

**1c - the scoped review of step 1's cycle-3 fix** (fresh context, only the
unreviewed fix). It found no stage-3 output the fix refuses, and eight
weaknesses around it, each handled with tests first and mutation:
1. rule A's tolerance was pinned by no test - now pinned on the case that
   splits the two readings (revenue 0.004999999999999999 prints 0.00, level
   1's product 0.005 prints 0.01): `month_not_positive`, never a refusal;
2. with the bridge and another rule both broken, the fallback raised the
   bridge's refusal - now the one that remains without the bridge, the
   real cause, the bridge's chained to it;
3. `year_ago` matched T2 by two separate computations - now written from
   T2's own evidence, equal by construction;
4. the fallback lever was copied, never validated - now validated (an
   equivalent mutant today: no reachable state differs; kept as a guard);
5. beside a huge term, residue could swallow a real 9 cents - residue is
   now also under half a cent;
6. a numpy float crashed `allocate_cents` - converted first;
7. tests pinning their rule only in part - tightened (each new field alone
   in an 18.3 file; year_ago's current month; a blocked run WITH a pair;
   the residue boundary; a residue term's bar);
8. the other withholding codes beside a month at zero or below were
   accepted - refused. Left as a trade-off (hand-built files only, never
   stage 3's): a file missing B2 or T2, or with duplicate ids, escapes the
   ties that read them.

### Item 2 - Q21 and Q22 in code (2026-10-05)

report.json 2.8 (CONTRACTS 9, 10): `narration_status` "not_in_v1" for v1's
absent narration - report.html and the Insights page print no line for it;
"unavailable" keeps its line in a report from before. The revenue KPI
carries `change`, the exact `core.revenue_change` (the appendix's figure),
printed beside the percentage in the KPI table ("-140,000.00 (-10.9%)");
null where the change is withheld and before metrics 16.2. The front
section's use of `bridge.shown_change` is step 3's (with Q24 open). Tests
first (9 red, and the page's 1); two tests that pinned "unavailable" for a
v1 report updated to the decided rule.

### Step 1 - stages 2 and 3's new fields (2026-10-05)

Method fixed before the code: `C:\Users\Happy\redesign-step1-method.txt`.
Shapes as built (CONTRACTS 6, 7, 10, 11 hold the rules):

```
metrics.json 16.2   core.revenue_change, core.revenue_change_reason
diagnosis.json 18.4 tree.lever.bridge {revenue_previous, revenue_current, change,
                      shown_previous, shown_current, shown_change,
                      bars[{factor, value_prev, value_cur, contribution, shown}],
                      aov_split, aov_split_withheld}
                    tree.lever.bridge_withheld: zero_orders | month_not_positive | not_to_the_cent
                    year_ago {previous, current, revenue_previous, revenue_current}, year_ago_reason
                    headline.hedge: seasonal | plain
report.json 2.7     carries headline.hedge
```

- **Stage 2** (`metrics_core.py`): the change, null with the period's
  reason exactly beside an incomplete previous month; version-gated
  (`contracts._base.minor_version`).
- **The rounding rule, one copy** (`contracts/lever_bridge.py`, new, out of
  contracts/diagnosis.py for size): `allocate_cents` (largest remainder; a
  cent given back where the printed difference sits a cent under the terms;
  a term of 0 or float residue never moves; a positive term never shown
  below zero; null when it cannot reach), `printed_cents`, `as_shown`.
  Stage 3 allocates with it; the contract recomputes it.
- **The ends a reader draws** are `shown_previous` / `shown_current`, the
  months as stage 5 prints them: the frontend's `Intl.NumberFormat` rounds a
  half cent up where Python prints to even, so no reader formats revenue
  for the chart itself.
- **Stage 3** (`lever.py`): `lever_from_totals`, `_bridge`, `refund_lines`
  (B2's count, moved here: one copy, B2 unchanged); `_level2` returns its
  null cause, the reason texts in `LEVEL2_NULL_REASONS`. `assemble._year_ago`;
  `headline._masked_hedge` returns the code, the sentences in
  `contracts.diagnosis.HEDGE_SENTENCES`; T2's no-pair words in
  `NO_YEAR_AGO_PAIR`. 4B's input leaves every new field out.
- **The contract** refuses: bars that are not the lever's terms or not the
  allocation; ends other than the printed months; a split withheld for
  refunds where B2 did not refuse on them, or drawn where it did; a level-2
  cause other than its reason; `month_not_positive` beside months level 1
  shows at a cent or more; year_ago other than the frame's months and T2's
  pair, or a reason the frame and trust do not give; a hedge off rule 4 or
  off its message's sentence; any new field in a file before its minor.

**Verification.** Tests first (22 failing on the old code, then 96 in the
three new files). Hand mutation: 72 mutants over five rounds, every one
killed after the tests they exposed were tightened, two equivalent
(redundant checks, removed). Three doubt-review cycles (fresh-context
adversarial subagents; cross-model not run - offered to Thach): cycle 1 a
crash on half-cent months and at large amounts, and contract gaps; cycle 2
a crash past 15 significant digits, the frontend's half-up rounding, a cent
on a factor that did not move, gaps; cycle 3 a crash near half a cent
between stage 3's and the contract's readings, version gating, the B2 and
T2 ties. All fixed; the cycle-3 fixes are tested and mutated but, the
skill's bound of three cycles reached, not re-reviewed by a fourth.
Regression on real files: Thach's Kaggle run (stages 2-5 again on its
stage 1 output) and both Online Retail II demo runs - every existing field
of metrics, diagnosis, report and forecast.json IDENTICAL; only the new
fields and the version stamps differ. Kaggle's bridge: 0.00 / +4,712.29 /
+2,858.84 / -2,646.13 = 4,925.00; both demo runs one order-value bar
(`refund_lines`), the unanswered 125,915.39 / 51,213.50 / -37,662.33 =
139,466.56.

Decisions made alone (Thach's veto open):
- `revenue_change` is null only beside an incomplete previous month, not
  for a non-positive base (an amount needs no base).
- `month_not_positive`: no waterfall beside a month that prints 0.00 or
  below (the masked-shift alert refuses the same months; printed cents, so
  residue cannot decide); `not_to_the_cent` where the cents cannot be
  allocated or printed back (very large amounts).
- A term of exactly 0, or residue, never takes or gives a cent; a positive
  term is never shown below zero.
- `year_ago` is written whatever T2's verdict (the front reads T2's
  verdict for the line's group).
- The Kaggle cases in the tests are its month totals, not its rows (uploaded
  data is never committed).
- The name `bridge` (Thach's) sits beside stage 3's customer "bridge" terms
  (`tree.customers`); the docstrings say which is which.

### Step 2 - stage 1 reads the file's currency (2026-10-05)

Built on Thach's principle (section 6) and his Q26-Q31; the method fixed
first: `C:\Users\Happy\redesign-step2b-method.txt` (the first method,
`redesign-step2-method.txt`, read every column and was replaced).

**Where.** At execute, on the RAW file, from two places only (Q26): the
plan's money column (the columns mapped to `unit_price`, the only money
field of the canonical vocabulary) and a currency column (a column whose
header, letters only, is a currency's name alone or with one word around
it: "Currency", "currency_code", "TransactionCurrency", "币种"; a header
that only mentions one - "Amount in Local Currency", "Currency Rate" - is
none). No other column is read: a SKU "TOP-001", a weight "2.5 kgs", a
country. `profile.json` is unchanged (1.2): it is written before any
mapping exists. The function, `stages.ingest.currency.currency_finding(frame,
money_columns)`, is the one step 5's Review calls with the plan as edited.
It runs after the plan's own checks (a refused plan says why first) and
before anything is written. Generic cleaning reads nothing.

**The money column.** A currency sign on its cells or in its header is
evidence: a named sign is its code (£ GBP, € EUR, ...); "$" and "¥" narrow
(Q5, Q9); a sign this version does not name (₨) is a currency of its own;
the full-width forms read as their usual sign; a cent is part of a dollar.
A code in its header counts only written in capitals, in brackets or as the
header's last word in a header not all in capitals ("Price (AUD)", "Price
AUD", "TotalAUD"), the only such code in it, and never a code that is also
a word or a unit (ALL, TOP, CUP, PEN, BOB, SOS, MAD, MOP, GEL, KGS, WST).
Anything else is doubtful: "amount_gbp", "PRICE_AUD", "Price per Cup".

**The currency column (Q28, Q29), each judged on its own.** Empty: blanks,
"-", "none", "n/a", a long dash, what stage 1 reads as missing anywhere
(profiling's NA tokens), zero-width characters, and a repeated header line.
Unreadable (counted, never a value): a cell that reads as a number or a
date ("0", "36", "05-Jan-2024"; shared.dates with a digit). Two or more
distinct values (trimmed, upper-cased) block, each listed as first written
with its lines ("Euro: 2 lines, US Dollar: 1 line"). One value that is an
ISO code is evidence; one that is not ("Euro") is a hint for Review. Two
columns of one value each that disagree (Currency EUR, Settlement Currency
USD) are doubtful: a hint ("EUR, USD"), never evidence, never a block.

**The one block rule.** Two or more distinct currencies among the evidence
(the currency column's code, the money column's signs and header code)
block, whatever the answer (Q7 = A): INVALID_PLAN, `details.reason`
"currency", "Your file has amounts in more than one currency (GBP: 3 lines,
EUR: 1 line). DataClarity cannot add different currencies together. Split
the file by currency and upload each part." - the file's lines, a line
once, largest first (a tie in the file's column order), at most 10 and
"and N more", no thousands separator. A "$" beside exactly one dollar or
peso code (the pesos, BRL for "R$") is that code (Q27: pre-selected with
where it was found; never refused).

**The finding:** found (code, source column | symbol | header, evidence),
narrowed, mixed, or none; `hint` and `unreadable` beside any but mixed.
Unanswered, a found code applies, anything else is "not stated"; an answer
stands (equal to the found code, it keeps where it was found).

**Stored** (6.4 as amended by Q26): `plan_final.json` 4.3
`confirmations.currency` (the answer), `cleaning_report.json` 4.3 `currency`
(`{code, source, evidence}`); CONTRACTS 4, 5 and 10 (Q25's rule written
there too).

**Decisions made alone (Thach's veto open):**
- The profile carries no currency (Q26 reads at execute); Review gets the
  finding from the same function (step 5).
- The check runs after the plan's own checks, not before them.
- Empty also covers a long dash, stage 1's NA tokens, zero-width
  characters and a repeated header line (each means "no value" already).
- A date with words ("05-Jan-2024") is unreadable through stage 1's own
  date reading (shared.dates), a digit required (so "May" is no date).
- Unreadable cells are counted even when the column holds no value (Q29
  to the letter: a "Currency Code" of 840/978 is "3 cells could not be
  read", not silence).
- The hint stands beside a found code too ("Pound" beside "€" prices:
  EUR pre-selected, and Review shows "Pound").
- Two currency columns of one value each that disagree: a hint, not a
  block (the rule is per column, Q28's "a currency-named column").
- Codes that are also words or units are never read in a header (the list
  above); "R$" joins the "$" family as BRL.
- A tie between parts is listed in the file's column order.

**What step 5 (the frontend's Review) needs** - not built here:
- the question always shown (D6), from `currency_finding(raw frame, the
  plan's unit_price columns)` through an endpoint (the plan or preview
  call): found - the code pre-selected with `evidence`; narrowed -
  `candidates` first, then the full list, nothing pre-selected; none - the
  closed ISO list, the common ones first, "Not stated" the default; `hint`
  shown ("Your Currency column says: Euro"); `unreadable` shown ("1 cell
  could not be read"); `evidence` and `hint` escaped (they hold the file's
  text);
- mixed: the block - `parts` and `more_parts`, no answer offered; execute
  answers 422 INVALID_PLAN, `details.reason` "currency", the sentence in
  `details.problems` - a dead end (split the file), never "edit the plan";
- the answer goes to `confirmations.currency` (an ISO code or
  "not_stated"); `frontend/src/types/contracts.ts` has the answer and
  `AppliedCurrency`; the finding's type is added with its endpoint.

**Known limits (8D):** text symbols (kr, zł, Rs, RM ...) and codes written
inside amount cells are not read (Q30); a sign this version does not name
beside its own code blocks (₨ with PKR); "EUR" beside "€", or "USD" beside
"US$", in a currency column block (two text values, Q28's letter); currency
columns whose header is a currency's name with another word than the listed
ones ("Presentment Currency") are not read; two values whose first 40
characters agree are listed alike.

**Process.** Tests first: Thach's eight cases failed on the work in
progress (TOP-001, "2.5 kgs", one SVC-100 line, Euro/US Dollar, GBP plus
"0", GBP plus EUR plus "0", "-" and "none", a single "Euro"), then the
fourth review's. Hand mutation: 50 of 50 killed on the final rules.
Doubt-review: four cycles (single model, Q23). Cycles 1-3 reviewed the
earlier versions, which read every column; their findings led to Q26-Q31.
The fourth (Q31), scoped: 12 findings, nine
"fabricate", none on a common export shape (Shopify, WooCommerce, Square,
Stripe's Amount column, Online Retail II and Kaggle all correct) - so the
safety valve did NOT trigger. Its findings were fixed (each more
conservative, or a signal for Review) or recorded as the known limits
above; those fixes were tested and mutated, not reviewed again (no fifth
cycle, Q31).

**Cost:** Kaggle 0.00 s, Online Retail II 0.02 s (460,859 rows, the money
column only); worst cases at 460,859 rows: a currency column of 667 extra
names 2.4 s, a currency-named column of 460,859 distinct date-times 3.1 s.

**Regression** (on HEAD a335789 and on step 2, one process at a time, no AI
call): both Online Retail II demo runs, stages 1-5 (peaks 705-737 MB), and
Thach's Kaggle run, stages 1-5 from its raw file - every file IDENTICAL
except the new fields (`confirmations.currency` null, `currency` not
stated) and the 4.2 -> 4.3 stamps; neither file blocked.

### Step 3 - stage 5's front section (2026-10-05) - built, STOPPED, not committed

Built (the working tree; a copy at `C:\Users\Happy\step3-front-wip\`):
report.json 2.9 (`front`, `currency`, `rows_left_out`,
`layer_1_numbers.partial_months`, `layer_2_causes.lever_levels`;
`contracts/report_front.py`), forecast.json 2.1's actions contract (three
states; `contracts/forecast_actions.py`) with a section 11 table, the front
builder (`stages/report/front*.py`, `wording.py`), report.html's front with
inline SVG charts and the old report in one closed appendix
(`html_front.py`, `html_svg.py`), the share bars moved to
`shared/share_bars.py` (unchanged). Tests first on the three real runs
(their contract files as fixtures, product names replaced); mutation 41 of
41; the old tests updated (versions, the appendix's script, the front's
note link). Rendered on the three real runs at 390 px and 1440 px: no
horizontal overflow, closed or open, no console message; the waterfall
matches the mock.

**The review (one cycle, display code) - findings:**
- FABRICATES, common shape: a confirmed currency prints counts as money in
  the appendix ("customers GBP 609.00") - `html_parts.number()` routes floats
  over 100 through `money()`. Fix: counts and evidence plain; money alone
  coded.
- FABRICATES, demo files: C3 "More customers came back after a break" and P3
  "Fewer returns" read money fields as counts (the design's wording) - Q34.
- Rule 5 (and rule 6's offsetting case) has no hypothesis id: sentence C
  prints "several checks match equally" - false - Q33.
- A forecast before 2.1 with the AI on reads "switched off" - Q36.
- Stage 3's trust messages and reasons bring banned words and an uncoded
  amount into the front - Q37.
- A season of 2+ years called "last year" - Q38.
- Sentence C's "more/less often" read from the order count, not orders per
  customer; sentence C garbled for P1/T2 named; shortfall/excess with the
  size test inside not put first; one-decimal rounding beside stage 3's
  multiple ("+10.0%" beside "less than twice ... about 5.0%"), "more than"
  at equality.
- Notes not beside sections 2, 3 and 5 (Q35); the chart's gap note, the
  forecast's history and season notes not in the front; the blocked state
  still draws the chart.
- The sales chart's top point and its label fall outside the drawing on
  both demo runs (the axis stops under the maximum); axis ticks carry no
  currency code; the caution colour's contrast on the dark card; the range
  sentence wrong when the band uses the history's spread; the banned-word
  test misses plurals.
- Stage 4 (step 4) must also keep the front's banned words out of the AI's
  sentences, and the report must not list actions under rule 7.

Fixes without a question (ready to apply on Q32): the counts' format, the
direction of B1 from orders per customer, sentence C by its own phrase for
every id, the order for shortfall/excess inside, stage 3's decimal places
and "at least" at the bound, the blocked chart, the chart's axis above its
maximum, coded axis ticks, the contrast, the range sentence's two cases,
plural-safe banned-word tests, the chart's gap note and the forecast's notes
in the front.

**Stopped** under Thach's rule (a fabrication on a common shape and on the
demo files after the step's last review cycle): nothing committed; step 4
not started (it builds on step 3's actions contract and fact sentences).

**Step 3 - fixes, the scoped review, stopped again (2026-10-06).** Applied
on Thach's answers: diagnosis.json 18.6 `headline.named` (stage 3, additive;
its rules and messages unchanged, verified on the three real runs - only
the new field and the stamp differ); sentence C from it; every line worded
in its field's unit (C1-C3, P3-P5 as money; section 11 lists
`tree.customers.previous_transition`); the root-cause unit fix with its test
over the three real runs (GBP: no count or ratio coded, every money figure
coded; evidence and quoted sentences marked and named in the appendix);
notes per section; "not available"; the checks by id and status; the
season of several years; decimals that agree with stage 3's tests; the
chart's axis, the blocked chart, gaps and the forecast's notes under the
chart and next month; the range sentence; the AI's sentences refused when
they hold a front word. Tests first (22 red); mutation 35 of 35 on the
fixes; the old tests updated to the decided wording. Re-rendered at 390 and
1440 px: no overflow, no console message.

The scoped review (Q32) found fabrications again - on common export shapes:
a D1 block or caution about the previous month (or a file covering only
part of it) worded as the current month (Q39); D2's caution choosing "the
wrong scale" where stage 3 cannot tell a unit change from a repricing; B1/B2
called orders on a file with no order id (lines); the checklist note "last
year's" beside a season of several years - and on both demo files: the
summary's figures (sentences B and C come from the diagnosis) without the
note that names them. Also: a one-sided offsetting case read as a match
(Q40), a lapsed term worded as a loss when positive, "this diagnosis was
made before" on an 18.6 tie with no ids, the season gap printed from the
field beside rounded changes, "+0.0%" for a change that moved, "more than"
beside equal printed figures, "median" missing from the banned words (Q43),
T2's line beside a season of several years (Q41), "not available" beside
the appendix's recommendations (Q42), the P1/P2 sentence C without Q20's
caveat, the appendix's plotly charts uncoded.

**Stopped** under the stop rule: not committed; step 4 not started (it runs
only once step 3 is pushed). The work: the working tree, copied to
`C:\Users\Happy\step3-front-wip\`.

**Step 3 - Thach's pattern applied, the scoped review, the safety valve
(2026-10-06).** Applied Q39-Q43 and the decisions of section 10's sixth
round: diagnosis.json 18.7 (`trust.checks[].month`, `headline.offsetting`;
`named` required for a rule 6 tie) - stage 3's rules and messages
unchanged, the three real runs re-run: every existing field identical, only
the two new fields and the stamp differ; the checks worded by id, status and
month (a file before 18.7: no month, never this month); sentence C from
`offsetting` (before 18.7, a rule 6 naming no single cause gets no sentence
C); D2 by what it tests; every "order" by `orders_basis`; a season of
several years never "last year's"; T2 the fact only; D1-D3 one line
(`front.data_checks`); the summary's notes include the diagnosis's; no
free-text recommendation anywhere (Q42), report.html included for an older
report.json; the banned words a stage 4 check (`front_word_problems`) and
"median" banned (Q43); the appendix charts coded; "more than" only beside a
printed figure that is more; a change that moved never prints as zero; a
positive lapsed term never worded as a loss; Q20's caveat in sentence C.
Tests first (18 red); mutation 37 of 37 (7 survivors first, each given a
test - one was a real gap: stage 3 copied the headline without its
validator, now validated); the full suite green.

Decisions made alone (Thach's pattern applied, none guessing a meaning):
- T2's line (Q41) prints the two amounts, not "X%": `year_ago` holds no
  percentage and stage 5 computes none.
- D2's caution: "A sudden price jump or fall across most products ...: a
  change in the data's units or currency, or a deliberate repricing (the
  file cannot tell which)" - "or fall" because D2 flags a factor below its
  band too; "most" because both of D2's rules need 80 percent of products.
  "No sudden price jump across all products" (the ok wording) is not shown:
  the one data-checks line replaced every per-check ok line.
- D1's block on the previous month's coverage: "the file does not show
  sales across the whole of <previous month>" - stage 3 blocks a month cut
  short AND one with no sale at all, and "covers only part" fits one.
- D1's block on the current month: "at least half the days" (stage 3 blocks
  at unexplained empty days >= half the month), not "most".
- A check that could not run (inconclusive, not applicable) and none
  cautioning: "Data checks: no problem found in the checks this file allows
  (details in the technical section)".
- The report fixtures stay diagnosis 18.6: they stand for a file written
  before 18.7, which stage 5 must still read; 18.7 is tested by setting its
  fields on them.

**The scoped review (Q32's rule)** found one fabrication on a common export
shape: with a caution on the PREVIOUS month, the caution box still opened
"Some of this month's data may be missing or wrong" ("this month" is the
current one). **Safety valve triggered** (no fix-and-review cycle): that
kind of line - the general caution opener - left the front section; the
caution now opens with each check's own line, and the appendix keeps the
trust verdict ("Data trust: caution") and every check's message as written.
A test holds it absent from report.json's front and report.html outside the
appendix. This also settled the review's finding 4 (stage 3 cautions when a
check is inconclusive: the front showed the opener with nothing after it and
hid the data-checks line; now the data-checks line says it).

Not fixed (recorded, under Thach's rules - none on a demo file or a common
export shape; open questions Q44-Q48 in section 10):
- FABRICATES, neither (Q44): beside a season, "more than N times" is decided
  on stage 3's unprinted difference while the two changes print at one
  decimal - near the band edge the printed changes differ by exactly N times
  the typical difference.
- FABRICATES, neither, introduced this session (Q44): the decimals test
  reads `round(value * 10**d)`, which can differ from the printed text when
  a typical change is exactly x.x5 ("less than twice ... about 4.3%" beside
  "+8.7%"). The fix is one line (decide on the printed text); not applied
  without a review, per the safety valve.
- OTHER (Q45): an annual closure the season explains - D1's check "ok" while
  the D1 hypothesis matches the change - reads "Data checks: no problem
  found" beside "days with no sales ... missing data, or closed".
- OTHER (Q46): T2's subject "Last year's change between the same months"
  (checked - not the reason, or cannot show) beside a season of several
  years - true of T2 (one year), but the letter of "never last year's".
- OTHER (Q47): `front_word_problems` is called by no stage yet - stage 4
  writes no actions until step 4, which wires it.

### Step 4 - stage 4's suggested actions (2026-10-06) - built, reviewed, fixed, STOPPED, not committed

**Built (design section 4, full process; the AI faked, no real call):**
`stages/predict/claims.py` (the claims: rules 5 and 6 only, never D/T/C4,
the headline's causes first then by amount, at most three; each fact the
checklist's own sentence - the wording moved to `shared/claim_lines.py`
and `shared/wording.py` unchanged, one copy for stages 4 and 5 - in the
file's confirmed currency read from cleaning_report.json; a watch line by
kind from the bridge's bar or the money terms); `actions_checks.py` (design
4.4's checks); `ai_actions.py` and `prompts/actions.md` (the input: the
claims and the shop alone; one retry, then AIUnavailable); `assemble.py`
writes forecast.json 2.1 (list / off / suppressed; 4B's blocks null - Q42;
an answer reused only for the same claims); the backend builds the step
when `STRATEGY_AI_ENABLED` is on; stage 5 counts the listed actions in the
provenance and points the appendix to section 4. On the three real runs
(the AI off): forecast.json's existing fields identical; Kaggle "off" (K1
B1, K2 B2, K3 P2 selected - as design 4.2 says); both demo runs "list" with
none (rule 7): "No action is suggested: no single reason stands out...".
Tests first; mutation 32 of 33 (the survivor equivalent: the claim ids
also cap the list at three).

**Its review** found four fabrications - number words the list missed
("forty", "a quarter", "½", "a pound"); "ordered" on a file with no order
id; R2's watch line calling products "new"; every suppression said as "the
AI's answer did not pass our checks" (a timeout too) - and five other
findings (customer groups refused as names; "will", "ensures", "record
month", holidays, abbreviated months, two sentences, a movement said the
wrong way let through; no notes beside section 4; "AI" lowercased in the
notices). All fixed, tests first (22 red); mutation 23 of 23; the full
suite 5132 passed. Decisions made alone in the fixes: the suppressed
sentence became "the AI gave no answer that passed our checks" (true of a
timeout and of the attempts used; design 4.4's sentence was not);
`front.notes.next_steps` added to report.json 2.9 (unreleased, in place).

**The scoped review of the fixes found fabrications on common export
shapes**: the direction check reads `claim.direction` - the sign of the
effect on sales - as the measure's movement, so on falling refunds "Refunds
rose" passed and "Refunds fell" was refused (returns; discounts and lost
customers alike); "Customers are visiting more often" on a file with no
order id; "every fourth visit", "a fiver off", "a pair" (ordinals and
quantity words); and, on neither shape, a verdict on a named month ("After
an exceptional December") that the narrowed period list stopped catching,
and movements said without a listed verb. Other: holidays in capitals
("Summer"), "May" opening a sentence; certainty synonyms; sound answers
refused (9 of 38 hand-written) with retry messages that do not name the
matched word; R2's watch line naming closed months; the design's 4.4 text
not updated.

**Stopped** under the stop rule for step 4: not committed; no further
cycle. The work: the working tree, copied to
`C:\Users\Happy\step4-actions-wip\` (working-tree.patch against a0ea4f0,
untracked.tar). Open: Q49-Q54 (section 10). No real AI call was made;
`STRATEGY_AI_ENABLED` stays false.

**Step 3's follow-up (2026-10-06, Q44-Q48).** Q44: the decimals are decided
on the text printed (`f"{value:.{d}f}"`, never `round(value * 10**d)`);
beside a season the two changes and the typical difference are printed at
the decimals where the printed changes' gap agrees with stage 3's band and
its word ("more than" only where it is more; "at least" where equal), and
sentence A prints the change at those decimals. Q45: "Data checks passed
(details in the technical section)"; where a check could not run, "Data
checks passed, except those this file cannot run (details in the technical
section)" - a decision made alone, the same correction applied to the other
line. Q46: T2's subject reworded. Q48: already so since the safety valve
(each caution line names its month; no opener), now pinned by a test.
Tests first (4 red, 2 already holding); mutation 6 of 6. The scoped review
found no fabrication on a demo file or a common shape; its findings are
Q55-Q59 (recorded, not fixed: the one review the round allows), except Q46's
sentence in a second place (T2 with no year_ago pair, a diagnosis before
18.4), applied with a test - Thach's own answer, completed.

### Step 4 rebuilt as Thach's option (d) (2026-10-06) - code-written actions, no AI

**Built** (section 4; full process): the claims as before (R2 out: Q52);
each action and why picked from the catalog (`stages/predict/catalog.py`)
by the claim's kind and the direction its own figure moved
(`claims.own_direction`: the bars and money terms by their two figures'
order; P1 and P2 by the measured amount's sign; R1 by the sales change -
stage 3 writes R1 no amount; R3 "down"); R3 in stage 3's own words (Q54);
forecast.json 2.1 "list" / "suppressed" (never "off"), `actions_model`
null, a 2.1 file holding 4B's blocks refused; the strategy AI path deleted
field by field (Q53): stage 4's `ai_strategy`, `strategy_*` modules and
prompt, the AI actions and checks never committed, the backend's AI step
and attempt count for stage 4, `STRATEGY_AI_ENABLED` (settings,
`.env.example`, the report CLI, tests), stage 5's `include_recommendations`
and the recommendations' confidence label; report.json keeps its fields
(`recommendations_status` "switched_off", both null); CONTRACTS section 11:
reader 4B dropped (no row lost its last reader), reader 4A added to the 41
fields the claims read; the frontend's recommendations place says "No AI
writes recommendations in this version." and lists nothing. Tests first;
mutation 21 of 22 (the survivor equivalent: no reachable claim has a
direction but no entry) plus a test for a calendar or R2 cause reading "no
cause" rather than "nothing to act on".

**Its review** found fabrications on common shapes - B1's why read orders
per customer as "regular customers bought more / less" (false with new
customers, or fewer bigger purchases); B2's "at a time" and "buy together"
on a file with no order id; P4's action and why calling the deduction lines
discounts (CLAUDE.md 3.3a: they may be coupons, refunds, write-offs) - and
R3 worded as one product where stage 3 lists several; and: R1 never a claim
(stage 3 writes it no amount); tests that did not guard `NOT_A_LEVER`; docs
contradicting the code (CONTRACTS 9 and 11, SPECS, this design's 1.4 and
test plan, CLAUDE.md's folder list, ADR-0002); the claims' fields without
reader 4A; the frontend saying "switched off"; "made before" said of "off"
and of a file out of step; an older report pointed to a section 4 it does not
render. All fixed, tests first (8 red); mutation 8 of 8; the B1, B2 and P4
whys point to "the figure above" and say only what is true.

**Open (recorded, not fixed):**
60. **Q60** - a drop that the calendar or the season also matches (T1/T2
    supported beside a named B1) gets customer advice ("a reminder may help
    bring it back"); the figures are true, but the advice treats a seasonal
    or calendar drop as something to act on. Leave B1 out of the claims when
    T1 or T2 is supported at the supported bar, or keep it?

**The scoped review of the fixes (Thach's stop rule)** still found
fabrications on common export shapes: B1's new why ("the figure above
rose") under a fact line that prints the order count, which fell (new or
lapsed customers); P4's fact and watch line still calling the deduction
lines discounts beside a why that says the file cannot tell - and, where
Review confirmed them as discounts, a why saying the file cannot tell; B2's
"show a related item" on a file with no order id, where a related item is
its own line and cannot move items per line. **Moved out of the claims, as
the stop rule says: B1, B2 and P4** (`claims.MOVED_OUT`; their catalog
entries removed; tests prove them absent - never a claim even when named,
none in Kaggle's section 4). Kaggle now lists one action, P2 (customers
chose cheaper products). The docs the review found contradicting the code
were corrected (this design's 4.2 and 4.4, CONTRACTS' log and `year_ago`
row, the API schema's notes, PROJECT_PLAN's folder list, LINE_TAXONOMY).
No further cycle.

**Open (recorded, not fixed):**
61. **Q61** - R3's action points to "the products listed under the stockout
    check in the technical section", a label the technical section does not
    use (its row reads "A top product may have run out of stock"; the
    products appear in its evidence). Name that row instead?
62. **Q62** - R1's action points to "the product or category named in the
    technical section", but stage 3's R1 is products only and its member
    appears only as "top_member" in the evidence cell. Word it "the product
    named in the technical section's row for this check"?
