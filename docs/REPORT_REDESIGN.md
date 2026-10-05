# Report redesign for a shop owner (Phase 1: design only)

Status: **design, awaiting Thach's approval. No production code is written
from this file until he approves it** (Thach, 2026-10-05). Phase 9's deploy
waits for the redesign.

Why: Thach's manual test found report.html accurate but unreadable for its
real audience, a shop owner with no analytics background. His decisions
D1-D7 are recorded with their reasons in PROJECT_PLAN Phase 9 (item 9R).
This file answers the session's (a) to (g); the open questions are in
section 10. Nothing in it is a decision Claude made alone: every choice not
already made by Thach is either forced by an existing rule (named beside it)
or listed as a question.

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
so the price lever never appears and the shares add to 154%. Both level-2
fields are already in the consumer contract (CONTRACTS 11, read by 5 and
FE), so no new stage 3 *figure* is needed for the Kaggle waterfall. Two
findings below (1.2) still need new stage 3 fields.

## 1. The front section, in Thach's approved order

Conventions used in every wording below:

- `{x}` is a field rendered by stage 5. Money is formatted as today (two
  decimals, thousands separators); a month `2024-12` is written "December
  2024". **Stage 5 computes no figure** (CONTRACTS 11). Every number below
  is a field of a contract file, and a field that does not exist yet is
  marked **NEW** with the stage that would write it (section 2).
- Amounts carry the confirmed currency (D6, section 6). Both runs here are
  "Not stated" (neither file names a currency: section 6.6), so amounts are
  shown bare, with the one sentence "Amounts are in your file's currency."
- Plain words only (section 3's glossary). The word "usual" is stage 3's
  own for the size test (`headline.movement`). "Normal" is never used:
  ADR-0006/0007 forbid calling a month normal from the signals.
- When `period.previous_complete` is false, sections 1-4 show this month's
  figures and `previous_incomplete_reason` only, with no comparison, change
  or bar (CONTRACTS 11's standing rule). When `trust.verdict` is `caution`,
  one line opens section 1: "Some of this month's data may be missing or
  wrong - read these figures with care." It is followed by the check's own
  message. When `blocked`, sections 1-4 are replaced by: "The data cannot
  support conclusions: {trust.checks[blocked].message}".

### 1.1 Section 1 - The 30-second summary (three sentences, then the chart)

**Rule (Thach):** sentence A = this month's sales and change; sentence B =
whether the change is inside the history's usual range; sentence C = the
main reason in words like "matches the figures", never "caused by". When the
change IS inside the usual range, B comes FIRST (open question Q3 checks this
reading).

"Inside the usual range" is decided by stage 3, never by stage 5:

- inside = `headline.movement.season.band == "consistent"` (the season
  explains it), or `headline.movement.singled_out == false` (under
  `factor` x the median month-to-month move);
- outside = `singled_out == true` with no consistent season;
- cannot say = `singled_out == null` (history too short):
  B = "The file's history is too short to say whether a change this size is
  usual for this shop.", placed after A.

The signals (`signals[]`, yoy limits) are NOT used for this sentence:
CONTRACTS 11 says none is a verdict in v1.

Sentence C by `headline.rule`:

| rule | sentence C (code-written) |
|---|---|
| 6 or 5 (a cause named) | "The figures match {plain statement of the named hypothesis}: {its own figures}." |
| 7, season consistent | "Nothing else stands out: the change matches last year's, so none of the checks below is named as the reason." |
| 7, size test (not singled out) | "No single reason stands out." |
| 7, history too short | "With this little history, no single reason can be picked out." |
| 7, season shortfall/excess | stage 3's own season sentence, unchanged (it is already plain) |
| 4 (offsetting moves) | "Underneath, {orders} and {average order value} moved a lot in opposite directions and largely cancelled out. This may be seasonal, or an ordinary month's shift: treat it as a pointer, not a finding." (stage 3's hedge, `_masked_hedge`, chosen by stage 3 - a NEW field `headline.hedge` carries which one; today it lives only in the message text) |
| 2 (missing days) | "The change matches days with no sales at all - missing data, or days the shop was closed (the file cannot tell which)." |
| 1 | (the blocked line above replaces the section) |

D5's sentence follows the summary, once: **"Sales here means the money
customers paid (before any costs). It is not profit: the file has no cost
data."** When the file maps no cost column (always in v1), the second half
is fixed. When currency is "Not stated", it adds: "Amounts are in your
file's currency."

**Kaggle (rule 6, B1; singled out, so A then B then C):**

> Sales in December 2024 were 46,292.50, up 4,925.00 (+11.9%) on November
> 2024 (41,367.50). That is a bigger change than usual for this shop: more
> than twice its typical month-to-month move of about 4.9%. The figures
> match customers ordering more often: 25 customers bought in each month,
> and together they placed 343 orders, up from 308.

Fields: `core.revenue_current`, `core.revenue_previous`,
`core.revenue_change_pct`, **NEW `core.revenue_change`** (stage 2; today the
+4,925.00 exists only inside `headline.message` text, which is never
parsed), `headline.movement.singled_out`, `.factor`, `.typical_pct`,
`headline.rule`, `headline.hypothesis_id`, `core.active_customers_*`,
`core.orders_*` (for B1 the sentence names customers and orders; for each
other id the template names its own fields, section 3).

**Online Retail II, classed (rule 7, season consistent; inside, so B first):**

> This change matches last year's: between October and November sales rose
> 27.1% last year and 27.2% this year (the file has one earlier year to
> compare with). Sales in November 2011 were 663,315.58, up 141,755.41
> (+27.2%) on October 2011 (521,560.17). Nothing else stands out: the
> change matches last year's, so none of the checks below is named as the
> reason.

Fields: `headline.movement.season.expected_change_pct` (27.10),
`.change_pct` (27.18), `.years` (1), `.band`; the rest as Kaggle.

**Online Retail II, unanswered:** the same shape, with its own figures:

> This change is within this shop's usual range for the season: between
> October and November sales rose 39.1% last year and 27.1% this year, a
> gap this shop's history shows often (the file has one earlier year to
> compare with). Sales in November 2011 were 654,527.09, up 139,466.56
> (+27.1%) on October 2011 (515,060.53). Nothing else stands out: ...

(A consistent band with a gap stated: `season.difference_pct` -12.1 points
against twice its `typical_pct` 8.5. B says "a gap this shop's history
shows often" because the band is `consistent`. The 0.1-point case above
says "matches" because both are the same band. **Q3b:** one wording for
every consistent band, or two by the size of the gap? Two would need a
NEW stage 3 field, because stage 5 may not compare the gap itself.)

**The chart, directly under the summary** (D5, D7; the outline does not
place the chart, so Q15 asks): title **"Sales by month (before any
costs)"**. Whole months only, as today. **D7's sentence directly under it**
(section 7).

### 1.2 Section 2 - Where the change came from (the waterfall)

**Rule (Thach):** a waterfall from last month to this month; every lever
drawn, including price per unit; the bars sum exactly to the change.

Bars, left to right: start = last month's sales; then customers who
bought; orders per customer; items per order; average price per item; end =
this month's sales. With `orders_basis == "lines"` the labels say lines
(as `DecompositionCard.tsx` and headline rule 4 already do). With the
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
change. 'Worth' amounts share out the effect of things that moved
together, so read them as sizes, not exact causes."

**Finding 1 - the demo months must NOT draw the items/price split.** On
both Online Retail II runs stage 3 still writes `level2` (units per order
-82,344.30, price per unit +40,353.31, classed), but it REFUSES the
basket-size hypothesis B2 (`inconclusive`, `refund_lines_prev` 579 /
`_cur` 482): "level 2 counts refunded units against the basket, so basket
size cannot be separated from return lines ... until level 2 has a refund
factor of its own" (`hypothesis_evidence_lever.py`, Thach 2E). Drawing
"items per order: -82,344.30" would state, as a fact, the very reading
stage 3 refuses, on the demo dataset. That is the FABRICATE shape (CLAUDE.md
3.6). So the waterfall follows stage 3: where B2 is refused, the order
value is ONE bar, with a sentence saying why. **Q1** asks Thach to confirm,
since D-text says "every lever is drawn".

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

**Finding 2 - rounding breaks "sum exactly" on the demo.** Rounded to
cents, the unanswered run's four level-1+2 terms add to 139,466.57, against
a change of 139,466.56. Its three bars happen to add correctly, and so do
Kaggle's four. A bar shown to the cent is a rounding of an exact Shapley
term, so the shown bars and the shown change can differ by a cent. Stage 5
may not adjust a figure. **Proposal (Q2):** stage 3 writes the bars it
draws, each rounded to the cent by the largest-remainder rule so the shown
bars sum to the shown change exactly. The exact terms stay in
`tree.lever.level1/level2` and the appendix.

**Finding 3 - two customer counts.** The bar's customers are BUYERS (609
-> 756: customers with a sale line, `lever.period_totals`). The KPI's
active customers are 634 -> 779 (a customer who only returned goods counts
as active). Today the Insights page labels the bar "Customers who bought"
for this reason. The front section never shows the active count beside the
bar. **Q4** asks whether the appendix KPI keeps "Active customers" with
its definition, or whether both counts get plain names.

Fields: **NEW `tree.lever.bridge`** (stage 3, additive), shape proposed:

```
bridge: {
  bars: [{factor, value_prev, value_cur, contribution, shown}]  # shown: cents, largest remainder
  shown_change: float            # == round(revenue change, 2) == sum(bars.shown)
  aov_split: bool                # false where B2 is refused or level 2 is null
  aov_split_withheld: Literal["refund_lines", "aov_unchanged",
                              "net_units_not_positive"] | None
} | None
bridge_withheld: Literal["zero_orders", "previous_incomplete"] | None
```

Today the reasons live in `tree.lever.reasons`, which CONTRACTS 11 lists as
"not in the contract". The decision to split is stage 3's (one copy of the
B2 rule), and the frontend draws the same bridge. `core.revenue_previous`
and `_current` are the end bars.

### 1.3 Section 3 - What was checked (a plain checklist)

Groups, each written by stage 5 from `hypotheses[].id`, `.verdict`,
`.contribution` and `.against_the_change` (vocabularies and figures in the
contract: no figure computed). The words per id are in section 3:

- **Matches the figures** - `supported` (and `partial`: "matches a small
  part") moving with the change;
- **Pulled the other way** - `against_the_change` true, |share| >= the
  partial bar;
- **Checked - not the reason** - `ruled_out`;
- **This file cannot show it** - `not_testable`, and B2 when refused
  (inconclusive for refund lines).

T3 and C4 are inconclusive in every v1 run by design (ADR-0007; C4 off).
They appear only in the appendix, which keeps them true without asking a
shop owner to read a v1 switch.

Under headline rule 7 (no cause named), the first group is titled **"Moved
this month, but not singled out"**, with stage 3's `hypotheses_note` in
plain words: "Because the change matches last year's, none of these is
called the reason; each line says what moved." (**Q16**).

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
> Pulled the other way
> - Customers chose cheaper products on average - worth about -1,479.65.
>
> Checked - not the reason
> - Data: no days without sales, no prices recorded at the wrong scale, no
>   rows flagged during cleaning.
> - Customers: no new customers, none stopped buying, none came back after
>   a break - the same customers bought in both months.
> - Prices: products sold in both months kept their prices.
> - Returns: none in either month. Discounts: none booked as separate
>   lines (a discount already taken off a price cannot be seen - the file's
>   "Discount Applied" column is not read in this version).
> - One product or category: the change was not concentrated in one.
> - Stockouts: no best-selling product stopped selling in a way that
>   suggests it ran out.
>
> This file cannot show it
> - Charges such as postage: no line was marked as a charge in Review.

Fields: `hypotheses[]` (id, verdict, contribution, against_the_change -
the last read today by stage 5 only: its row gains **FE**),
`tree.customers.new/lapsed/resurrected`, `tree.returns.*`,
`tree.products.new_products/discontinued_products`, the lever values from
`bridge`, and **NEW `year_ago`** (stage 3: `{previous, current,
revenue_previous, revenue_current, years_compared}` - today T2's 34,900.00
and 41,046.00 exist only in `hypotheses[T2].evidence`, whose keys
CONTRACTS 11 says no consumer relies on). T2's wording is fixed: "last
year only - one earlier year" (Thach; scope freeze 8D: no new statistic).
R2 never says "launched" or "discontinued" (Thach): a product with no sale
in one month is "sold in only one of the two months".

**Online Retail II, classed (rule 7):**

> Moved this month, but not singled out (because the change matches last
> year's, none of these is called the reason)
> - More customers placed an order: 756, up from 609 (see section 2).
> - Customers ordered more often - worth about +56,167.67.
> - Prices of products sold in both months went up - worth about
>   +36,878.80.
> - More customers came back after a break - worth about +36,744.87.
> - Fewer returns: 13,951.29 returned, down from 41,074.29 - worth about
>   +27,123.00.
> - The calendar - worth about +12,069.22.
> - Postage and other charges paid by customers rose - worth about
>   +11,500.70.
> - Last year, sales also rose between October and November (518,318.50
>   to 658,764.09) - last year only, one earlier year.
>
> Checked - not the reason
> - Data checks, new customers, customers who stopped buying, a shift
>   to cheaper products, discounts, products sold in only one of the two
>   months, one product or category, stockouts.
>
> This file cannot show it
> - Basket size (items per order): returns make it unreliable this month.

**Online Retail II, unanswered:** the same, except prices +19,443.98 and a
shift to pricier products +9,246.49 (both partial: "a small part"), fewer
returns +24,535.13, and charges "This file cannot show it: no line was
marked as a charge in Review".

### 1.4 Section 4 - What to do next

The structured recommendations of section 4 (D4). Each item shows
**the action** (AI), **why** (AI), **the figure it rests on** (code) and
**what to watch next month** (code). On the two demo runs (rule 7) no
claim is selected (4.2), so the section reads: "No action is suggested:
no single reason stands out beyond the season. Next month, compare sales
with the estimate in section 5." The Kaggle mock shows the claims code
would select, with the AI's two fields marked as placeholders. No AI call
was made in this session.

### 1.5 Section 5 - Next month

> **Kaggle:** Next month (January 2025): about 43,835.33, likely between
> 38,893.14 and 49,405.54 - a range meant to hold the real figure about 8
> times in 10, worked out from how far off this method's past estimates
> were. It is based on the last three full months, the
> latest counting most, and assumes no seasonal pattern. Your file already
> has sales for 1 to 18 January 2025 (24,211.50 so far); that part-month is
> not compared with this estimate.

> **Online Retail II, classed:** December 2011: about 401,224.73, likely
> between 313,360.52 and 513,725.48. It follows the seasonal pattern of
> the last two years - the fewest years that can show one - so the shape is
> less certain than more years would make it. [Notes beside the forecast,
> as today: the unconfirmed-suggestions note.] Your file already has sales
> for 1 to 9 December 2011 (182,218.63 so far); that part-month is not
> compared with this estimate.
> **Unanswered:** about 384,784.50, between 305,880.67 and 484,042.07
> (170,647.13 so far for 1 to 9 December).

Fields: `forecast.revenue[0]` (point, low, high, confidence),
`forecast.method` (worded by its shape: weighted average / with a season),
`season_years`, `season_note` (reworded once in plain words; one copy
in stage 5), `history_note`, the revenue notes beside it (CONTRACTS 11's
standing rule), and report.json's `forecast.first_month_in_file` /
`partial_first_month_until` plus the NEW `partial_months` (section 7). "8
times in 10" words `confidence` 0.8: the band is the past errors' root
mean square times Student's t (`stages/predict/forecast.py` `band`), an
80% interval by construction, not a count of past misses. **Q12** asks
whether the wording is acceptable.

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
> - **Rows left out.** 12,575 rows were read and 11,362 used; rows left
>   out during cleaning are in no figure, and a gap they leave cannot be
>   seen. [Kaggle. Online Retail II: 460,859 read and used; the lines
>   classed in Review as fees or adjustments are left out of sales - the
>   appendix lists them.]

Fields: `not_testable[]` (by id, reworded in plain words: X1-X7; the code
reasons "not canonical", "the 2D finding", "P4" move to the appendix),
`data_quality.rows_in/rows_out`, `products.velocity_reason`,
`trust.limitations`, `non_product[]`.

### 1.7 Section 7 - Technical appendix (collapsed)

One `<details>` element, closed by default: "Technical details (for an
analyst)". It keeps, unchanged in substance (D3: moved, never deleted):
the file's row counts and cleaning changes; the trust badge and its three
check messages and limitation; the KPI table (orders, active customers,
average order value, return rate) with their notes; the monthly table with
the partial month; "How to read these figures"; the AI narration, or "the
AI narration is unavailable"; **every hypothesis tested, today's full
table** (id, statement, verdict, contribution, share, rule, evidence) with
`hypotheses_note`; the not-testable list with today's reasons; **"Where
this month sits" (the limits table) with its method text**; the lines in no
figure; the forecast's method, table and band; the exact lever terms
(levels 1 and 2 and the orders x AOV pair - so the demo's withheld split
stays visible to an analyst, with B2's refusal beside it); provenance. The
appendix keeps today's labels ("Revenue" in a field's own name included)
and adds one line at its top: "In this appendix, 'revenue' is the same
figure as 'sales' above."

## 2. New fields (all additive; CLAUDE.md 3.7)

| Field | Writer | Why no consumer can do without it |
|---|---|---|
| `metrics.core.revenue_change` | stage 2 | the change amount in sentence A; today only inside `headline.message` text |
| `diagnosis.tree.lever.bridge` (+ `bridge_withheld`) | stage 3 | the waterfall: which bars (B2's refusal is stage 3's rule), cent amounts that sum exactly |
| `diagnosis.year_ago` | stage 3 | T2's two figures; today only in evidence keys no consumer relies on |
| `diagnosis.headline.hedge` | stage 3 | rule 4's seasonal or plain hedge, chosen by stage 3; today only in message text |
| `cleaning_report.currency` (+ `confirmations.currency`, `profile` measure) | stage 1 | D6 (section 6) |
| `report.json`: `currency`, `layer_1_numbers.partial_months`, `front` (the front section's code-written sentences and bars, so report.html and the page print one copy) | stage 5 | D6, D7, one wording for both readers |
| `forecast.json`: `actions` (+ `actions_status`) | stage 4 | D4 (section 4) |

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
| partial | matches a small part | |
| ruled out | checked - not the reason | |
| moved against the change | pulled the other way | |
| inconclusive / not testable | this file cannot show it | |
| lever lens / lens / lever | (removed) | the waterfall shows the levers |
| share = contribution / D, "96% of the change" | "worth about +4,712.29" | money, never a share: shares overlap |
| contribution | worth about | |
| AOV | average order value (what an order brought in) | |
| frequency | orders per customer | |
| units per order | items per order | |
| price per unit | average price per item | |
| yoy | compared with the same month last year | |
| limits, within the limits, centre | (appendix only) | ADR-0006/0007 |
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
| Like-for-like prices changed (P1) | prices of products sold in both months | |
| Sales mix shifted (P2) | customers chose cheaper/pricier products | |
| Returns changed (P3) | returns | |
| Discounts and other deductions (P4) | discounts | |
| Charges paid by customers (P5) | postage and other charges paid by customers | |
| Concentrated in one product or category (R1) | one product or category | |
| Products were launched or discontinued (R2) | products sold in only one of the two months | Thach: no "launched/discontinued" |
| A top product may have run out of stock (R3) | a best-seller that may have run out - check the shelf | stage 3's own wording kept |
| Marketing and promotions (X1) ... Sales channel (X7) | section 6's plain list | code reasons to the appendix |
| "(the 2D finding)", "not canonical", "P4" in reasons | (appendix only) | |
| weighted moving average ... weights 1, 2, 3 | based on the last three full months, the latest counting most | |
| the 80% band, from the method's own past errors | likely between ... (meant to hold the real figure about 8 times in 10) | Q12 |

A test (section 9) fails if any of these words is in the front section:
hypothesis, verdict, supported, ruled out, lens, lever, share,
contribution, AOV, yoy, year-over-year, limits, inconclusive, revenue,
"caused", "launched", "discontinued".

## 4. Structured recommendations (D4; the same design for 3F)

The design Thach set on 2026-10-01 (PROJECT_PLAN 4B): code selects the
claims and writes every sentence of fact or figure; the AI writes only the
action and the reason for each pre-selected claim, with no number and no
choice of claims.

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

### 4.2 Which claims (code, deterministic)

- Only when `headline.rule` is 5 or 6 (a cause named). Under rules 1, 2, 3,
  4 and 7, or with `trust.verdict` blocked or `previous_complete` false,
  **no claim** - the AI is not asked, and the code line of 1.4 is shown.
  Acting on a cause the headline refuses to name would undo the size test
  and the season rule (Q10).
- From `supported`/`partial` hypotheses moving with the change, plus
  `against_the_change` ones at |share| >= the supported bar, excluding the
  data family (D1-D3: a data problem is fixed, not acted on in the shop)
  and time (T1, T2: the calendar is not a lever). Ranked: the headline's
  hypothesis first, then by |contribution|. At most 3 (Q11).
- Kaggle: K1 = B1 (+4,712.29), K2 = B2 (+2,858.84), K3 = P2 (pulled the
  other way, -1,479.65).

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
already plans for 3F):

1. invalid JSON or schema; a claim id missing, repeated or not given;
2. **any digit** (0-9, any script: `str.isdigit` on every character), `%`,
   a currency symbol (Unicode Sc), a number word (one ... twenty, dozen,
   hundred, thousand, million, half, double, twice, triple, percent),
   "x" between words ("2x" is caught by the digit);
3. stock words (`_STOCK`), a verdict on a period (`_VERDICT` with `_PERIOD`),
   "orders"/"AOV" when `orders_basis` is lines (`_ORDERS`);
4. certainty words: caused, causes, proves, proof, definitely, certainly,
   guarantee(d), will increase, will grow;
5. over 30 words, an empty field, or a sentence that restates the fact (a
   figure-free restatement is allowed; the fact is shown anyway);
6. any word the claims did not give that names a product, a customer or a
   month (the input's own texts are the allow-list, as 4B's `input_texts`).

**Retry:** one, with the problems listed (AI_PIPELINE 9's shared budget).
**On a second failure, an API error, or a timeout: the whole section is
suppressed** (never a partial list): "Suggested actions are not shown for
this report: the AI's answer did not pass our checks, so nothing was shown
rather than something unchecked. Every figure above is unaffected." Switched
off (`STRATEGY_AI_ENABLED=false`): "Suggested actions are switched off for
this report." Never fabricated: no fallback text pretends to be advice.

### 4.5 Cost

The model is `MODEL_REASONING` (ADR-0003), Sonnet 5 at $2 / $10 per million
tokens (the eighteenth run's smoke test used the same rates). Estimated:
system prompt and rules ~1,200 tokens, claims ~150 each -> ~1,700 input;
output ~300 tokens of JSON plus thinking, ~1,000 at most -> **about $0.01
to $0.014 a call; about $0.03 with the retry**. Today's 4B input is 8,000
to 9,000 tokens. **Estimated, not measured**: the first approved real call
measures it (Phase 4's manual review still needs Thach's approval).

### 4.6 3F, the same design

The diagnosis narration (`ai_findings`) uses the same machinery: code
selects the claims (the headline's hypothesis and the checklist's "matches"
group, at most 3) and writes every sentence with a figure - which the front
section now does entirely in code. **What is left for the AI in 3F is an
open question (Q14):** (a) nothing, and 3F closes (the front section is
the narration); (b) one "what this means for the shop" sentence per
claim, with the same checks; (c) the plain rewording of stage 3's
sentences, with the same checks.

## 5. What does not change

- No JSON field is renamed or removed; `revenue_*` keeps its name (D5,
  CLAUDE.md 3.7). Every change in section 2 is a new field.
- No stage 3 rule changes: the verdicts, the headline rules, the size test,
  the season bands and B2's refusal stand as they are. The redesign only
  words them and adds fields that carry what stage 3 already decides.
- No consumer computes a figure; the AI writes no number (CLAUDE.md 3.2).
- Every note keeps its place by its code (CONTRACTS 11).

## 6. Currency (D6)

### 6.1 Rules (stage 1 code, on the RAW file, in profiling)

Evidence that **counts** (one is enough, all must agree):

| Kind | Rule | Shown in Review |
|---|---|---|
| A currency column | a column whose HEADER names a currency (`currency`, `ccy`, `curr`, `cur`, `devise`, `moneda`, `waehrung`/`währung`, `valuta`, `tien te`/`tiền tệ`, case-insensitive, as a whole word) and whose every non-blank cell is an ISO 4217 code (closed list, upper-cased after trimming) | "AUD, from column Currency" |
| A symbol in amount cells | the amount columns (mapped `unit_price`, and any numeric column the plan reads as money) carry one unambiguous Unicode Sc symbol (£ GBP, € EUR, ₹ INR, ₩ KRW, ₫ VND, ₺ TRY, ₽ RUB, ₴ UAH, ₪ ILS, ₱ PHP, ฿ THB, ₦ NGN, ...), counted by today's `_strip_currency` reading | "GBP, from the £ in column Price" |
| A currency in an amount header | a token of an amount column's header equal to an ISO code: `Price (AUD)`, `amount_gbp`, `TotalEUR`; split on non-letters and case changes. Codes that are English words (ALL, TOP, CUP, PEN, MOP, BOB, SOS, GEL, BAM, LAK, MAD, PAB, TOP...) count only when written upper case | "AUD, from the header Price (AUD)" |

Evidence that **does not count**:

- a Country column, or any country value (Online Retail II sells to France
  and Germany in GBP);
- a bare `$`: it narrows to the dollar currencies. Review asks which,
  offering them first (Q9: which list), nothing pre-selected;
- `¥` - **Q5**: it is the yen's AND the yuan's symbol, so Claude reads it
  as `$` is read (narrowed to JPY/CNY, asked), unless Thach decides it
  means JPY;
- a code-like value in a column whose header does not name a currency
  (**Q6**: Claude proposes it is NOT evidence - "CAD" could be a product
  code), the AI's guess alone (**Q7b**).

**The AI's part:** D6 says the AI MAY propose. Pandas verifies any proposal
by the same three rules on the actual cells. A proposal the rules do not
confirm is not used. **Q7b** asks whether v1 asks the AI at all: the rules
above find every kind D6 lists, and an AI proposal adds a prompt change
and a schema field.

### 6.2 Review (always shown, D6)

- Found: pre-selected, with where it was found; the user can change it.
- Not found: the user picks from a closed list - ISO 4217 active codes,
  the common ones first (GBP, EUR, USD, AUD, CAD, ...), and **"Not stated"**.
  **Default: "Not stated"** (never assumed): the run proceeds when the
  question is left unanswered, and the report says so.
- Narrowed (`$`, `¥`): the narrowed list first, then the full list and
  "Not stated".

### 6.3 More than one currency (Thach decides; Claude does not pick)

Detected as: a currency column with more than one code; more than one
unambiguous symbol across the amount cells; a header code that disagrees
with a symbol; a `$` beside a `£` or `€`. Never summed silently in any
option.

| Option | What the user sees | What it costs |
|---|---|---|
| A. Block | Review: "Your file has amounts in more than one currency (for example: GBP on 9,412 lines, EUR on 311). DataClarity cannot add different currencies together. Split the file by currency and upload each part." The plan does not run. | Smallest: detection, one message, tests. No change to stages 2-5. The user does the splitting. |
| B. Analyse one currency | Review asks which currency to analyse (default: the one on most lines, never applied unanswered - the plan waits). The other lines are dropped in stage 1 with a change-log line ("left out 311 lines in EUR") and the report's section 6 says so. | Medium: a new stage 1 row filter tied to the answer, its change log, a Review question, tests. Stages 2-5 unchanged. Cost to the reader: the dropped lines are in no figure, and stage 3 cannot see a gap they leave (`trust.limitations` already says so for dropped rows). |
| C. Convert with rates | not proposed for v1 | needs exchange rates per date from outside the file: a new data source and a number no stage computes from the file. |
| D. One report per currency | not proposed for v1 | a run per currency: the run model, Review and the report all change. |

### 6.4 Where it is stored, and who reads it

- `profile.json` (stage 1 profiling): a NEW `currency` measure - the
  evidence found (kind, column, code or narrowed list, example cell),
  or mixed with the codes and line counts.
- `plan_final.json` `confirmations.currency`: the user's answer (an ISO
  code or `"not_stated"`), recorded like `number_formats`.
- `cleaning_report.json` `currency`: `{code: str | None, source:
  "column" | "symbol" | "header" | "user" | "not_stated", evidence:
  str | None}`.
- Stage 5 already reads `cleaning_report.json`. It writes report.json's
  NEW `currency` block, and report.html and the page format amounts from
  it. Stages 2, 3 and 4 do not read it (amounts are amounts).
- Display with a code: **Q8** - the symbol when unambiguous (£46,292.50)
  or the code (GBP 46,292.50) everywhere. With "Not stated": no symbol and
  no code on any amount, and the one sentence "Amounts are in your file's
  currency."

### 6.5 Test files (one per case; built in code, tiny, under tests/)

| File | Content | Expected |
|---|---|---|
| `cur_column_aud.csv` | `Currency` = AUD on every row | AUD, from column Currency |
| `cur_column_lower.csv` | `currency` = " aud " | AUD (trimmed, upper-cased) |
| `cur_symbol_gbp.csv` | Price `£2.50` | GBP, from the £ in Price |
| `cur_symbol_eur_suffix.csv` | Price `2,50 €` | EUR |
| `cur_header_paren.csv` | header `Price (AUD)` | AUD, from the header |
| `cur_header_snake.csv` | header `amount_gbp` | GBP, from the header |
| `cur_bare_dollar.csv` | Price `$2.50` | not found; narrowed to dollars; **never AUD or USD pre-selected** |
| `cur_country_only.csv` | Country = France, Germany, United Kingdom | **not found** |
| `cur_country_codes.csv` | Country = FR, DE, GB | **not found** |
| `cur_word_header.csv` | headers `all_prices`, `Top Price` | **not found** (ALL, TOP not read) |
| `cur_code_column_no_header.csv` | column `Code` = CAD, CAD | not found (pending Q6) |
| `cur_yen.csv` | Price `¥300` | pending Q5 |
| `cur_mixed_column.csv` | Currency = GBP, EUR | mixed (option per 6.3) |
| `cur_mixed_symbols.csv` | Price `£2.50`, `€3.00` | mixed |
| `cur_header_symbol_conflict.csv` | `Price (EUR)` with `£` cells | mixed |
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
revenue, position: "first" | "last"}]`):

> **Kaggle:** January 2025 is not in the chart: the file covers only 1 to
> 18 January 2025 (24,211.50 so far). Comparing part of a month with full
> months would mislead, so it is left out.

> **Online Retail II (both runs):** December 2011 is not in the chart: the
> file covers only 1 to 9 December 2011 (182,218.63 so far; unanswered:
> 170,647.13). Comparing part of a month with full months would mislead, so
> it is left out.

`covers_from` is the later of the month's first day and `data_start`;
`covers_to` the earlier of its last day and `data_end`. A file that starts
mid-month gets the same sentence for its first month. A file inside one
month has no chart (as today). The figure "so far" is
`revenue_by_month[].revenue` as written. **Q13** asks whether to show it.

## 8. The frontend screens (proposal only; nothing changes without approval)

| Screen | Same jargon or content today | Proposal |
|---|---|---|
| Insights, KPI cards | "Revenue", "Average order value", "Return rate"; trust badge "Data trust: trusted" | open with the same front section, from report.json's NEW `front` block (one copy of the wording, as notes already work: CONTRACTS 11 "Notes by code"); the KPI cards move under the appendix toggle |
| Insights, "Where the revenue change came from" (`DecompositionCard.tsx`) | draws level 2 even where stage 3 refuses B2 (the demo: "Units per order -82,344.30"); the orders x AOV pair beside it | draw `bridge` instead (finding 1 applies to the page today) |
| Insights, causes (`CausesSection.tsx`) | the Hypothesis / Verdict table, "About these verdicts", "What this data cannot test" with code reasons ("not canonical", "the 2D finding") | the checklist; the table behind a "Technical details" toggle |
| Insights, "Revenue by month" (`RevenueChartCard.tsx`) | title; no partial-month sentence | "Sales by month (before any costs)" and D7's sentence |
| Insights, forecast and recommendations | "80% band", method text; "The AI recommendations are switched off" | section 5's sentence; section 4 |
| Results (stage 1) | no analysis jargon; "Rows in / Rows out", "What ran" | unchanged, plus the currency answer shown with the other answers (6.2) |
| Review (stage 1) | - | the currency question (6.2): needed by D6 itself |

Finding 1 is live on the page today, independent of this redesign: it
shows the demo's refused basket split as figures. **Q17** asks whether to
fix that first, separately.

## 9. Test plan (symptom tests first; each fails on today's code)

Run on the Kaggle run's files (fixtures copied from this run, as the real
answers were) and on small built frames. "Fails today" was checked by
reading today's code and report.json, not by running the new tests.

| Test | Fails today because |
|---|---|
| waterfall bars sum to the change, to the cent (Kaggle: 0.00 + 4,712.29 + 2,858.84 - 2,646.13 = 4,925.00) | no waterfall in report.json/html |
| the price-per-item bar is drawn when the split is allowed (Kaggle -2,646.13) | never shown |
| the split is withheld, one order-value bar and its sentence, when B2 is refused for refund lines (demo shape) | no bridge; the page draws level 2 |
| largest-remainder cents: the unanswered run's terms (sum 139,466.57) give shown bars summing to 139,466.56 | no field |
| no jargon word (section 3's list) in the front section, outside `<details>` | today's page has them all |
| the appendix is one closed `<details>` and holds all 20 hypothesis ids, the limits table and the method text (nothing deleted) | no appendix |
| "Sales (before any costs)" in the front, chart titled "Sales by month (before any costs)", D5's not-profit sentence present; report.json field names unchanged (the consumer contract test unchanged) | "Revenue" |
| no currency symbol or code on any amount when "Not stated", and "Amounts are in your file's currency" present | no currency at all today (passes by accident for the symbol; the sentence fails) |
| with GBP confirmed, amounts carry it | no currency |
| partial-month sentence present under the chart, naming January 2025 and 1 to 18 January (Kaggle); December 2011 and 1 to 9 December (demo) | absent (`charts[0].note` is null) |
| the chart holds whole months only | passes today: a regression guard |
| summary order: inside the usual range -> sentence B first (demo); outside -> A first (Kaggle) | no summary |
| the summary never says "caused", "because of", "explains" | today's headline says "explanation" |
| T2's line says "last year only" | absent |
| R2's line never says "launched" or "discontinued" | today's statement says it |
| stage 1: one test per file of 6.5 - including "a bare $ is not read as AUD" and "a Country column is not read as a currency" | no detection |
| recommendations: a digit / a number word / a currency symbol / "caused" in the AI's text is refused; an extra or missing claim id is refused; one retry then the suppression notice; no AI call under rule 7, blocked, or an incomplete previous month; every fact sentence's figures equal the contract's | the step is off and unstructured |
| consumer contract: the new rows | rows not yet added |
| frontend (only after approval of section 8): the same no-jargon and bridge tests in Vitest | - |

Process per CLAUDE.md 3.6: the new stage 3 fields (`bridge`, `year_ago`,
`hedge`) and the claim selection are conclusion-producing code - method
first, tests first, mutation, doubt-review cycles. Stage 5's assembly and
the page: failing tests first and one review cycle, mutation on logic.
Stage 1's currency detection is logic: full process.

## 10. Open questions for Thach (none answered by Claude)

1. **Q1 Waterfall on refund months.** Where stage 3 refuses B2 (both demo
   runs), draw the order value as one bar with a sentence (Claude's
   proposal, finding 1), or draw all four bars with a caution? D-text says
   "every lever is drawn".
2. **Q2 Rounding.** Stage 3 writes cent amounts by largest remainder so the
   shown bars sum exactly (proposal), or another rule (whole units; a
   "rounding" bar)?
3. **Q3 Summary order.** Does "say this FIRST when it is" mean the range
   sentence opens the summary (as written in 1.1)? And is stage 3's size
   test plus season band the right "usual range", with the word "usual"
   (stage 3's) rather than "normal"? **Q3b:** one wording for every
   consistent season band, or two by the gap's size (a new stage 3 field)?
4. **Q4 Two customer counts.** The waterfall's customers who placed an
   order (609 -> 756) and the KPI's active customers (634 -> 779): plain
   names for both, or the active count in the appendix only?
5. **Q5 The ¥ sign** (yen and yuan): ask like `$`, or read as JPY?
6. **Q6 A column of ISO codes whose header does not name a currency:**
   not evidence (proposal), or evidence?
7. **Q7 Mixed currencies:** option A, B (or C, D) of 6.3. **Q7b:** does
   v1 ask the AI for a currency at all, or code only?
8. **Q8 Display:** the symbol where unambiguous, or the ISO code
   everywhere?
9. **Q9 Bare `$`:** which currencies are offered first - dollars only
   (USD, AUD, CAD, NZD, SGD, HKD ...) or the peso currencies too (MXN,
   ARS, CLP, COP)?
10. **Q10 Recommendations when no cause is named** (rule 7, as on both demo
    runs): no action with the code line (proposal), or actions from the
    "moved, not singled out" items?
11. **Q11 Which claims:** at most 3; data (D) and time (T) excluded;
    "pulled the other way" included - right?
12. **Q12 The forecast band's words:** "a range meant to hold the real
    figure about 8 times in 10, worked out from how far off this method's
    past estimates were" - acceptable for an 80% interval built from the
    past errors' spread?
13. **Q13 Partial month:** show its sales so far in the sentence (24,211.50
    on Kaggle), or name the dates only?
14. **Q14 3F:** what is left for the AI - (a) nothing, (b) one meaning
    sentence per claim, (c) rewording stage 3's sentences?
15. **Q15 Where the chart sits:** under the summary (as written), or in
    another section? The outline does not place it.
16. **Q16 Rule 7's checklist:** "moved this month, but not singled out"
    as a group (as written), or those lines in the appendix only?
17. **Q17 The page today** draws the refused basket split on the demo
    (finding 1): fix it now, separately, or with the redesign?
18. **Q18 New field homes:** the change amount in stage 2
    (`core.revenue_change`), the bridge, `year_ago` and `hedge` in stage 3,
    the front sentences in report.json `front` - agreed?
19. **Q19 Model for recommendations:** `MODEL_REASONING` (Sonnet 5, as
    ADR-0003 says for reasoning steps), or `MODEL_BULK` (Haiku 4.5, about
    half the cost) for a task this bounded?

## 11. After approval (proposed order; nothing started)

1. Stage 2 `revenue_change`; stage 3 `bridge`, `year_ago`, `hedge` (full
   process). 2. Stage 1 currency (after Q5-Q9). 3. Stage 5: the front
   section, the appendix, the partial month, the currency (failing tests
   first, one review cycle). 4. Stage 4 structured actions (full process;
   a real call only with Thach's approval). 5. The frontend (after Q17 and
   section 8's approval). Each is its own session, grouped for commits as
   CLAUDE.md says.
