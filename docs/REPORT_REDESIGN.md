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
`core.revenue_change_pct`, **NEW `core.revenue_change`** (stage 2; today the
+4,925.00 exists only inside `headline.message` text, which is never
parsed), `headline.movement.singled_out`, `.factor`, `.typical_pct`,
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
they do not add up to the change ({core.revenue_change}). The chart in
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

The structured recommendations of section 4 (D4). Each item shows **the
action** (AI), **why** (AI), **the figure it rests on** (code) and **what to
watch next month** (code). Under headline rules 1-4 and 7, a blocked
diagnosis, or an incomplete previous month, no claim is selected and the
AI is not asked (Thach, Q10); the section reads: "No action is suggested:
no single reason stands out in these figures. Next month, compare sales
with the estimate in section 5." Both demo runs (rule 7) read so. The
Kaggle mock shows the claims code would select, with the AI's two fields
marked as placeholders.

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
report.json keeps `narration` null and its status: whether that status
gains a value saying the step does not exist (an additive vocabulary
change) is **Q21**.

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

Step 1's shapes (proposed here, final as built - section 12):

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

## 4. Structured recommendations (D4; 3F closed)

The design Thach set on 2026-10-01 (PROJECT_PLAN 4B): code selects the
claims and writes every sentence of fact or figure; the AI writes only the
action and the reason for each pre-selected claim, with no number and no
choice of claims. It was designed to be shared with 3F. 3F closes (Q14),
so this is now the only AI step after stage 1.

### 4.1 The input code builds

```
{
  "shop": {"orders_basis": "order_id", "currency": "not_stated"},
  "claims": [                       # 0 to 3, ranked by code
    {"id": "K1",
     "kind": "B1",                  # the hypothesis it rests on
     "fact": "Customers ordered more often: 343 orders, up from 308 - worth about +4,712.29.",
     "direction": "up",             # up | down (with the change), against
     "subject": "how often customers order"}
  ],
  "rules": [...]                    # the forbidden-words list, as text
}
```

The `fact` is code-written (section 1.3's sentence, the same copy). The AI
sees no file content, no free-text field of the file (no product name, no
customer value) and no other figure. Kinds with a product (R3, R1's top
member) send the product name only as a quoted string the checks treat as
input text, as 4B does today.

### 4.2 Which claims (code, deterministic; Thach, Q10, Q11)

- Only when `headline.rule` is 5 or 6 (a cause named). Under rules 1-4
  and 7, a blocked diagnosis, or `previous_complete` false: **no claim**.
  The AI is not asked, and the code line of 1.4 is shown.
- From `supported`/`partial` hypotheses moving with the change, plus
  `against_the_change` ones at |share| >= the supported bar, excluding the
  data family (D1-D3: a data problem is fixed, not acted on in the shop)
  and time (T1, T2: the calendar is not a lever). Ranked: the headline's
  hypothesis first, then by |contribution|. At most 3.
- Kaggle: K1 = B1 (+4,712.29), K2 = B2 (+2,858.84), K3 = P2 (pulled the
  other way, -1,479.65; its fact sentence is section 1.3's "inside the
  chart's average price per item" line).

### 4.3 What code writes, and what the AI writes

| Part | Writer | Kaggle K1 |
|---|---|---|
| The figure it rests on | code | "Customers ordered more often: 343 orders, up from 308 - worth about +4,712.29." |
| What to watch next month | code, by kind | "Next month, check: orders per customer (13.72 this month; 12.32 the month before)." |
| The action | AI | one sentence, <= 30 words, no digit |
| Why | AI | one sentence, <= 30 words, no digit |
| The notes beside them | code | every not-always-on note (CONTRACTS 11's standing rule) |

The watch line per kind reads the same lever value the claim rests on
(`bridge.bars[].value_cur/value_prev`; for C1-C3 the bridge terms; for P1
and P2 the product terms). No new figure is needed.

### 4.4 Output schema and checks (code)

```
{"actions": [{"claim": "K1", "action": "...", "why": "..."}]}   # exactly one per claim, same order
```

Refused, each problem named for the one retry (4B's checks reused,
`strategy_checks.py`, the rendering moved to `shared/` as AI_PIPELINE 8
plans):

1. invalid JSON or schema; a claim id missing, repeated or not given;
2. **any digit** (0-9, any script: `str.isdigit` on every character), `%`,
   a currency symbol (Unicode Sc), a number word (one ... twenty, dozen,
   hundred, thousand, million, half, double, twice, triple, percent);
3. stock words (`_STOCK`), a verdict on a period (`_VERDICT` with
   `_PERIOD`), "orders"/"AOV" when `orders_basis` is lines (`_ORDERS`);
4. certainty words: caused, causes, proves, proof, definitely, certainly,
   guarantee(d), will increase, will grow;
5. over 30 words, an empty field;
6. any word the claims did not give that names a product, a customer or a
   month (the input's own texts are the allow-list, as 4B's `input_texts`).

**Retry:** one, with the problems listed (AI_PIPELINE 9's shared budget).
**On a second failure, an API error, or a timeout: the whole section is
suppressed** (never a partial list): "Suggested actions are not shown for
this report: the AI's answer did not pass our checks, so nothing was shown
rather than something unchecked. Every figure above is unaffected." Switched
off (`STRATEGY_AI_ENABLED=false`): "Suggested actions are switched off for
this report." Never fabricated: no fallback text pretends to be advice.

### 4.5 Cost and model

`MODEL_REASONING`, Sonnet 5 (Thach, Q19; ADR-0003), at $2 / $10 per
million tokens (the eighteenth run's smoke test used the same rates).
Estimated: system prompt and rules ~1,200 tokens, claims ~150 each ->
~1,700 input; output ~300 tokens of JSON plus thinking, ~1,000 at most ->
**about $0.01 to $0.014 a call; about $0.03 with the retry**. Today's 4B
input is 8,000 to 9,000 tokens. **Estimated, not measured**: the first
approved real call measures it (a real call needs Thach's approval).

### 4.6 3F closes (Thach, Q14 (a))

The code-written front section is the narration; the AI writes only the
recommendations. Stage 3 makes no AI call: `ai_findings` and `model_used`
stay null (as every v1 run writes them today), the narration prompt
(`prompts/root_cause.md`) is not built, and AI_PIPELINE 7.9 records the
closure. The appendix's "AI narration is unavailable" line goes (1.7, Q21).

## 5. What does not change

- No JSON field is renamed or removed; `revenue_*` keeps its name (D5,
  CLAUDE.md 3.7). Every change in section 2 is a new field.
- No stage 3 rule changes: the verdicts, the headline rules, the size test,
  the season bands and B2's refusal stand as they are. The redesign only
  words them and adds fields that carry what stage 3 already decides.
- No consumer computes a figure; the AI writes no number (CLAUDE.md 3.2).
- Every note keeps its place by its code (CONTRACTS 11).

## 6. Currency (D6)

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
| recommendations: a digit / a number word / a currency symbol / "caused" in the AI's text is refused; an extra or missing claim id is refused; one retry then the suppression notice; no AI call under rules 1-4 and 7, blocked, or an incomplete previous month; every fact sentence's figures equal the contract's | the step is off and unstructured |
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

**Open:**

21. **Q21** - with 3F closed, report.json's `narration_status` keeps
    today's value (the page simply stops printing the line), or gains a
    value saying the step does not exist in v1 (an additive vocabulary
    change, a major bump where a reader validates it closed)?

## 11. The build, step by step

1. **Stage 2 `revenue_change`; stage 3 `bridge`, `year_ago`, `hedge`**
   (full process) - **approved 2026-10-05; as built in section 12.**
2. Stage 1 currency (6; Q5-Q9 answered).
3. Stage 5: the front section, the appendix, the partial month, the rows
   left out, the currency (failing tests first, one review cycle).
4. Stage 4 structured actions (full process; a real call only with
   Thach's approval).
5. The frontend (section 8), including the deploy blocker of Q17.

Each is its own session, grouped for commits as CLAUDE.md says.

## 12. As built

(Filled in by each step's session.)
