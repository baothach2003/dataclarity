# Line taxonomy - design (session 2E-t)

**Status: APPROVED IN PRINCIPLE (Thach, 2026-09-28), subject to his eight
answers (section 8, now decisions) and a fourth fresh-context review
(section 9). Nothing here is built.** The decision record is
`docs/adr/0008-line-taxonomy.md`. Written 2026-09-27 in the fifth overnight
run, from Thach's brief in PROJECT_PLAN item 2E-t (a)-(e), his answer to Q3
of the fourth run, and what session 2E-n's reviews found; revised after each
of three fresh-context reviews, then with his answers (sixth run). Figures are measured on the two demo files with today's code
(scratchpad `2et/`, the reviews' `2et/review/`, `review2/`, `review3/`);
the implementation sessions re-measure them on the built code.

## 1. Why

The engine decides what a line *is* from the signs of its quantity and
amount, in several places, and the list of meanings grew one class per
incident. Signs are lossy: a customer return and a damaged write-off both
carry a negative quantity; a coupon and a refund both carry a negative
amount; a positive zero-price line is a free item on one invoice and stock
found in a count on another. Money and stock were mixed in one "deduction"
bucket. This design replaces the inference with ONE classification, made
once in stage 1, on accounting categories, with one table of effects that
every stage reads.

### 1.1 What the engine infers today

| # | Rule today | Where | Decides | What it gets wrong (measured / recorded) |
|---|---|---|---|---|
| 1 | `transaction_type` "in" is stock received, out of revenue; any other value a sale | `shared/transactions.line_numbers`, `metrics_products._stock_in` (2A, 2E-g) | revenue scope, the stock ledger | Kaggle maps its *Payment Method* column as `transaction_type`: "Cash" reads as "out" by accident |
| 2 | sale = counted, qty > 0, amount > 0, not a discount or charge | `shared/transactions.parse_transactions` (2E, 2E-c, 2E-l) | orders, units, gross sales, products | a gift voucher sold is a sale (77 Online Retail II sale lines, +1,756.17) |
| 3 | return line = counted, qty < 0, amount < 0 | same (2E-c2) | returns, return rate, the returns lens | all 18,827 return lines are on C (credit) invoices, which no rule reads; 1,797 pair one-to-one with a same-day sale of the same SKU, customer, quantity and price (476,682.59 each way) - cancelled orders, same-day returns and re-issues that the data cannot tell apart (section 4.4) |
| 4 | deduction = counted and none of the above | same (2E-c, 2E-c2) | the returns lens's `deductions`, P4 | one bucket for money and stock: discounts and refunds at a negative price beside zero-amount lines that move stock and no money - 2,745 positive (2,674 with no customer, 1,693 of those with no description) and 3,457 negative (none with a customer; 2,689 with no description, the rest "damaged", "missing", "check"...) |
| 5 | the user's classes: charge, discount, pooled, cost, adjustment, "a product" | `shared/line_classes.py`, stage 1's `non_product_lines.py` (2E-d2, 2E-l) | revenue scope, orders, the product tables | unanswered, every line is a product - right for revenue, but nothing records that it was never asked |
| 6 | a line with neither SKU nor name is the gap | `shared/products.py` (2E-g) | never ranked; the lens's `unidentified` | an identity rule doing a class's job |
| 7 | the stock balance is every counted line's quantity against the stock-in lines | `metrics_products._velocity` (2C) | days to stockout | a zero-amount line of -20 RAISES the computed stock by 20 - measured (scratchpad `2et/ledger_sign.py`): 100 received, 63 sold, 20 more removed reads **57 days** to stockout instead of 17. Only on files with stock-in lines; neither demo file has one (velocity null). A KPI fabrication older than this design (question 6) |
| 8 | B2 is refused on any negative-amount line that is not a return | `hypothesis_evidence_lever.b2` (2E-c2) | the basket hypothesis | a coupon and a refund at a negative price cannot be told apart, so both refuse (kept - section 6) |
| 9 | the first day nets per product and class key | `shared/first_purchase.py` (2E-f, 2E-d2) | new / resurrected customers | reads the classes twice (netting keys vs product keys) |
| 10 | a receipt is judged on its sale / return / counted / stock-in lines | `shared/orders.py` (2E-e, 2E-e2, 2E-k) | the order basis, the customer fill | inherits every sign rule above |
| 11 | a line with no parseable quantity or price is not counted | `parse_transactions` (`valid`) | every figure | reported NOWHERE unless its date is missing: Kaggle's 1,213 such lines (604 without a quantity, 609 without a price - 9.6% of the file) leave revenue silently. A SUPPRESS on a demo file, older than this design (question 7) |

Each stage recomputes rules 1-6 from the raw columns and the answers
(`parse_transactions` runs in stage 2 and again in stage 3); they agree only
because they share code.

## 2. The model: what the item is, and what the line does

A line's class is decided on TWO questions, each with its own evidence:

- **The item** - what the key (its SKU, else its name) is: a `product`, a
  `pooled` code (many items, no single product - M "Manual", and every line
  with neither SKU nor name), a `charge` the customer pays, a `discount`, a
  `gift_card`, a `fee`, an `adjustment`. Today's per-key answers
  (`shared/line_classes.py`) are exactly this question.
- **The movement** - what this line does. Its money is read from the sign of
  the amount; a source signal the user maps (a transaction-type value, an
  invoice prefix) changes the reading ONLY where it adds information the
  signs lack:
  - `sale`, `credit` - no change: the signs decide (a credit note's lines are
    returns or allowances by their signs). SPECS' own type "out" (stock sold
    or shipped) is pre-mapped to `sale`.
  - `return` - the line is a customer return whatever its signs: its money
    counts as out (-|amount|), its units as back (-|quantity|), and its goods
    back in stock. For exports that book returns at positive quantity and
    price under a "Return" type.
  - `stock in` - stock received: the line leaves revenue, as 2A's "in" does
    today, and is REPORTED with its lines and money (the schema prompt lets
    "in" be a customer return too; today that money leaves silently). It
    applies to product and pooled items only; a fee, a charge, a discount or
    an adjustment keeps its class.
  - `stock out` - only zero-amount lines: their direction is out.

A credit note is therefore a movement, never a class: a C line of a product
is a return or an allowance by its signs, a C line of postage a postage
refund (still a `charge`, negative), a C line of a fee a fee reversal (still
a `fee`) - a signal never overrides the user's item answer (review 1 #2).
Prefixes offer only `sale`, `credit` and `return` (no `stock in` - review 3
#2). On one line a type value outranks a prefix (the more specific unit).

### 2.1 The closed class list (brief a)

The accounting test for money: *tied to the sale* (revenue or
contra-revenue) or *tied to the cost of earning it* (an expense, outside
revenue); a line that moves goods and no money belongs to the stock ledger.
Every line of the file gets exactly one class.

| Class | Counted | Accounting | Online Retail II (whole file, Thach's classes, today's code) |
|---|---|---|---|
| `sale` | yes | revenue (gross sales) | the sale lines of products |
| `customer_return` | yes | contra-revenue (sales returns); goods back in stock NOT known | about 18,300 of the 18,827 return lines (the rest pooled) |
| `restocked_return` | yes | contra-revenue (sales returns); goods back in stock | lines under a type mapped `return` (neither demo file) |
| `pooled_sale` | yes | revenue (gross sales), never a ranked product | M "Manual" sale lines (M has 1,426 lines); lines with neither SKU nor name |
| `pooled_return` | yes | contra-revenue (sales returns), never ranked | M: 537 credit lines, -423,886.17 (15 in 2011-11, -3,249.16) |
| `allowance` | yes | contra-revenue: a money line of a product or pooled item that is neither a sale nor a return by its signs (a refund or coupon at a negative price, a positive credit) - today's deduction with money | unanswered, the 5 "Adjust bad debt" lines at a negative price (-158,676.14) |
| `discount` | yes | contra-revenue | D: 177 lines, -13,484.54 (5 at a positive amount, +397.89: reversals, reducing discounts) |
| `charge` | yes | other revenue (a credit is a refund of it) | POST, DOT, C2, 23444, including their 18 zero-amount lines |
| `free_item` | yes | no money; goods out (a promotional cost) | zero-price positive lines of a product on an invoice with a paid line: 759 |
| `stock_write_off` | yes | no money; stock out | zero-amount lines whose (description, sign) the user maps "out" |
| `stock_found` | yes | no money; stock in | zero-amount lines whose (description, sign) the user maps "in"; a zero-amount line under a `return` type |
| `stock_count` | yes | no money; stock direction NOT known | every other zero-amount line of a product or pooled item with a nonzero quantity: 1,680 blank positive lines with no customer, 2,689 blank negative lines, "found", "check"... until mapped |
| `no_movement` | yes | nothing moves (quantity 0) | lines with quantity 0 |
| `gift_card_sale` | **no** | liability (deferred revenue), outside revenue, reported | gift_0001_*: 77 money lines, +1,756.17, and 22 zero-amount lines |
| `gift_card_redemption` | **no** | settles or reverses the liability, outside revenue, reported | 1 line, -69.56 (a voucher refunded) |
| `fee` | **no** | expense, outside revenue, reported | AMAZONFEE, BANK CHARGES, CRUK, S (today's `cost`) |
| `adjustment` | **no** | outside revenue, reported (bad debt is an expense) | B, ADJUST, ADJUST2 |
| `stock_in` | **no** | stock ledger only; any money reported | transaction type "in" (neither demo file) |
| `unclassified` | **no** | isolated, reported (section 4.3) | **none on either demo file** |
| `unmeasurable` | **no** | no parseable date, quantity or price, or an amount that overflows: counted nowhere, reported | Kaggle 1,213 lines |

**Counted keeps TODAY's meaning** - the classes marked "yes" are exactly
today's counted lines (valid, not "in", not a fee or an adjustment) - except
where the user confirms a gift-card class, which takes those lines out as a
fee is taken out. Every reader of `parsed.counted` (`period_mask`,
`money_moved`, `months_with_rows`, the receipt fill, the members' presence)
reads the same lines until then (review 3 #4).

**What the code distinguishes today maps in without loss:** sale ->
`sale`; return line -> `customer_return`; deduction -> `allowance` (money)
or a stock class (no money); the pooled class and the identity gap ->
`pooled_sale` / `pooled_return`; `charge`, `discount`, `adjustment` -> the
same; `cost` -> `fee`; "in" -> `stock_in`; the answer "a product" -> the
product item; invalid -> `unmeasurable`.

`cancellation` is NOT in the list: section 4.4.

## 3. The effects matrix (brief b) - the single source of truth

One table, in one module (`shared/line_effects.py`), read by stages 2 and
3. **Signs:** every money column sums the lines' amounts AS SIGNED (a
`return`-signal line as -|amount|); "returns" and "discounts" are then
REPORTED as the magnitude of what they took away (returns = -(sum of return
amounts); a discount at a positive amount reduces discounts), as the returns
lens stores them today (`lever.py`). The identity: **net revenue = gross
sales - returns - discounts + other revenue**, to float residue. Gross sales
holds `sale` and `pooled_sale`; returns the three return classes; discounts
`allowance` and `discount`; other revenue `charge`.

**The customer columns reproduce today's rules exactly**: *customer money*
(the bridge's money, RFM monetary) = every line in net revenue with a
customer, so the bridge reconciles to the net change (`tree.py`); *customer
presence* (active customers, the bridge's presence, the RFM population - 3C:
a returns-only customer is active; RFM's "No purchases in file") = every
COUNTED line with a customer, as today (2011-11 with Thach's classes: 1,710
active - 1,662 buyers, 47 with other money lines only, 1 with a zero-amount
line only); *purchase* (orders, frequency, recency) = the sale lines; the
first purchase that makes a customer new reads sale AND return lines of
products and pooled items, 2E-f's first-day netting as today.

**The stock ledger** works in magnitudes, so no sign convention can invert
it: in = `stock_in`, `stock_found`, `restocked_return` (+|qty|); out =
`sale`, `pooled_sale`, `free_item`, `stock_write_off` (-|qty|); none = every
other class. A product with a `stock_count` line has an INCOMPLETE history:
days to stockout null with a reason (a suppression by design - question 5).
Today's rule 7 (a -20 line adding 20) cannot survive magnitudes.

| Class | Gross sales | Returns | Discounts | Other rev. | Net revenue | Cust. money | Cust. presence | Purchase | First-day netting | Units | Return rate | Product tables (money / presence) | Stock ledger |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sale` | + | | | | + | + | yes | yes | yes | + | denominator | yes / yes | out |
| `customer_return` | | + | | | + | + | yes | no | yes | + (negative) | numerator | yes / yes | none |
| `restocked_return` | | + | | | + | + | yes | no | yes | + (negative) | numerator | yes / yes | in |
| `pooled_sale` | + | | | | + | + | yes | yes | yes | + | denominator | no (`unidentified`) | out |
| `pooled_return` | | + | | | + | + | yes | no | yes | + (negative) | numerator | no | none |
| `allowance` | | | + | | + | + | yes | no | no | no | no | yes / yes (as today) | none |
| `discount` | | | + | | + | + | yes | no | no | no | no | no | none |
| `charge` | | | | + | + | + | yes | no | no | no | no | no | none |
| `free_item` | | | | | none | none | yes | no | no | no | no | no / yes | out |
| `stock_write_off` | | | | | none | none | yes | no | no | no | no | no / yes | out |
| `stock_found` | | | | | none | none | yes | no | no | no | no | no / yes | in |
| `stock_count` | | | | | none | none | yes | no | no | no | no | no / yes | history incomplete |
| `no_movement` | | | | | none | none | yes | no | no | no | no | no / yes | none |
| `gift_card_sale` | | | | | outside - reported | none | no | no | no | no | no | no | none |
| `gift_card_redemption` | | | | | outside - reported | none | no | no | no | no | no | no | none |
| `fee` | | | | | outside - reported | none | no | no | no | no | no | no | none |
| `adjustment` | | | | | outside - reported | none | no | no | no | no | no | no | none |
| `stock_in` | | | | | outside - reported | none | no | no | no | no | no | no | in |
| `unclassified` | | | | | outside - isolated, reported | none | no | no | no | no | no | no | none |
| `unmeasurable` | | | | | counted nowhere - reported (lines, reason) | none | no | no | no | no | no | no | none |

"Presence" in the product tables is today's: a product is a member of the
product dimension in a month through any counted line (`members.py`), so the
stock classes keep it present with no money (review 3 #4 - otherwise 2011-11
lost 27 members). The product lens decomposes gross sales of `sale` lines
(2E-n's reading G becomes "the `sale` class"). Every figure outside revenue
(gift cards, fees, adjustments, stock-in money, unclassified, unmeasurable)
is reported in metrics.json with its lines and money, never dropped
silently.

## 4. Classification once, in stage 1 (brief c)

Stage 1 writes into `cleaned.csv` (reserved names no source column can
take): `line_class`; `item_source` and `movement_source` (`user` | `signal`
| `rule` - the brief's `class_source`, one per question); `suggestions`
(the pending suggestions, one per question, e.g. `item:charge;direction:out`
- one cell cannot hold three, review 3 #6). Stages 2 and 3 read `line_class`
only, through `shared/transactions.py`, which refuses a value outside the
closed list.

### 4.1 Evidence, per question and per unit

| Question | Unit | 1. the user | 2. the rule | Suggestions (never applied alone) |
|---|---|---|---|---|
| the item | per key (SKU, else name) | the answer in Review (today's line-class answers) | neither SKU nor name -> `pooled`; otherwise `product` | class words (charge, discount, pooled, fee, adjustment - `non_product_lines.py`); gift-card words ("gift card", "voucher", "gift_"); what the AI proposes a column means (ADR-0002) |
| the kind of line | per mapped VALUE: a type value (outranks), an invoice prefix | the mapping in Review (2): type values sale / credit / return / stock in / stock out / not a signal ("in" pre-mapped to stock in, "out" to sale); prefixes sale / credit / return | none: the signs | type values worded "return", "refund" |
| a zero-amount line's direction | per (description, sign) - 10 descriptions carry both signs, holding 4,773 lines | the mapping in Review: out / in | a positive zero-price line of a product on an invoice with a paid line (order id mapped) -> `free_item`; otherwise not known | "damaged", "missing", "thrown away", "given away" -> out; "found" -> in |

**A suggestion never applies itself** (2E-d2; Thach's Q3): a line the rules
suggest is a charge but nobody confirmed keeps its rule-based class
(`sale`), with the suggestion recorded - so an unanswered file loses no
revenue.

### 4.2 From the answers to the class - a total table

In order, first match wins:

1. no parseable date or quantity, or (unless 2 applies) no parseable price,
   or a non-finite amount -> `unmeasurable`.
2. a product or pooled item under a `stock in` signal, with a date and a
   quantity (no price needed, as 2E-g F1) -> `stock_in`.
3. a charge, discount, fee or adjustment item -> that class, at any amount
   and sign (a zero-amount postage line stays a `charge` with no money).
4. a gift-card item -> amount >= 0 `gift_card_sale`, amount < 0
   `gift_card_redemption`.
5. a product or pooled item (P) under a `return` signal -> amount != 0: P
   return (`restocked_return` for a product, `pooled_return` for pooled),
   money -|amount|, units -|quantity|; amount 0 -> `stock_found`.
6. P with quantity 0 -> `no_movement`.
7. P, amount > 0: quantity > 0 -> P sale; quantity < 0 -> `allowance`.
8. P, amount < 0: quantity < 0 -> P return (`customer_return` /
   `pooled_return`); quantity > 0 -> `allowance`.
9. P, amount 0: a `stock out` signal or a mapped "out" -> `stock_write_off`;
   a mapped "in" -> `stock_found`; `free_item` by its rule; otherwise
   `stock_count`.

`sale` and `credit` signals change nothing (7 and 8 read the signs), so a
type "out" mapped as a sale, or a C prefix mapped as a credit, reproduces
today's lines exactly (review 3 #1: the second revision sent every money
line under "stock out" or every return under "sale" to `allowance`).
Every combination falls in exactly one rule; the test covers every input of
every rule (item, signal, amount and quantity signs, the direction answer,
a paid line on the invoice, order id mapped).

### 4.3 `unclassified`

Per Thach's Q3, only for a line no rule places. Section 4.2 places every
line, so nothing is `unclassified` (on either demo file). **No refusals in
v1** (Thach, decision 2): the class stays the tested, empty class, isolated,
for a shape a later decision may choose to refuse rather than place - never
as an answer a user gives (a "don't
know" that removed DOT's 36,905.40 from 2011-11's revenue would contradict
Q3; review 2 #4).

### 4.4 Why `cancellation` is not a class

A cancelled order never became revenue; a same-day return did. The data
cannot tell them apart. Measured on Online Retail II (review 1 #7,
`2et/review/pairs2.out`): 1,797 one-to-one same-day pairs at one price; in
**439 the credit is rung BEFORE the sale** it would cancel (21 of 96 in
2011-11) - of those with a named customer, 321 of 415 had bought the SKU on
an earlier day: a credit note for an old invoice followed by a re-issue,
where the re-issue is the sale that stands; 102 pairs match on a blank
customer; 111 are pooled M lines; on a file with no customer column, 4,745
of 19,493 credit lines would match. Even a matcher requiring the credit
after the sale, a named customer, an identified product and exactly one
candidate would class a real same-day return as a cancellation.
**Decided (Thach, decision 1): out of v1** - a same-day credit stays a
return, and the return rate is labelled honestly wherever it is shown: it
includes same-day cancellations, which the data cannot separate. metrics.json
carries that sentence beside the rate (`return_rate_note`, 2E-t2); every
surface that shows the rate (the report, the dashboard) reads it.

## 5. Guarantees (brief d)

- **Exactly one class per line**, tested on both demo files and on the
  sweeps: `line_class` has no blank and no value outside the list; the
  counted classes are exactly today's counted lines (until a gift-card class
  is confirmed); the effects matrix has a row for every class (a test fails
  when a class is added without its effects); the rules of 4.2 are tested
  over every combination of their inputs.
- **`unclassified` is isolated**, never assumed a sale: outside every revenue
  figure; its lines, money and share of the money moved in metrics.json and
  in Review. So is **`unmeasurable`**: counted nowhere, its lines and reason
  reported (today they are not - rule 11 of 1.1).
- **Review shows the identity** gross sales - returns - discounts + other
  revenue = net revenue for the file and the compared months, to float
  residue, with the outside-revenue totals beside it; metrics.json carries
  the same terms.

## 6. Migration (brief e)

**Earlier decisions it changes:**

| Decision | Becomes | What changes beyond where the rule lives |
|---|---|---|
| 2A: transaction type "in" is out of revenue | the `stock in` signal, "in" pre-mapped | its money is reported, not dropped silently; other type values can be mapped (`return` adds returns booked at positive signs) |
| 2E / 2E-c: a sale is qty > 0 and amount > 0 | rule 7 | nothing |
| 2E-c: the deduction bucket | `allowance` (money, in net revenue and in its product, as today) + stock classes and `no_movement` (no money) | nothing in money |
| 2E-c2: a return line is qty < 0 and amount < 0; zero-amount negative lines are no return | rule 8 | nothing |
| 2E-c2 B2: a negative-amount non-return line refuses the basket | kept: an `allowance` refuses (a coupon and a refund at a negative price stay indistinguishable); a confirmed `discount` no longer does | a confirmed discount stops refusing B2 |
| 2E-d2 / 2E-l: charge, discount, pooled, cost, adjustment answers | the item question; `cost` -> `fee` | nothing |
| 2E-g: the identity gap | the pooled item by rule | nothing (the `unidentified` term stays) |
| 2E-n: the products' share on their sale lines | on the `sale` class | nothing |
| 2C / 2E-g: the stock balance | the stock ledger of section 3, in magnitudes | a zero-amount line moves stock only once its direction is known - NO default (Thach, decision 5: "negative = out, positive with no customer = in" is Online Retail II's convention alone); unknown, the product's history is incomplete (velocity null with a reason) - a SUPPRESS by design, where today a -20 line adds 20: on Online Retail II's shape, 857 of the 2,889 products sold in 2011-11 have such a line (832 with every word suggestion confirmed) - about 29% of days-to-stockout figures null on a file like it with stock-in lines; neither demo file has one; a return comes back only under a `return` signal (today it always does - decision 3) |
| 2E-c2: the return rate | the same figure | its label: metrics.json's `return_rate_note` says it includes same-day cancellations, which the data cannot separate (decision 1) |

**Contract bumps.** `cleaned.csv` gains four columns; the stage 1
contracts (`schema_inference.json`, `plan_*.json`, `cleaning_report.json`)
go to their next major (the signal and direction mappings); `metrics.json`
and `diagnosis.json` to their next majors (the identity's terms,
`unclassified`, `unmeasurable`, the outside-revenue totals, the stock
ledger; the returns lens by class). Readers refuse the earlier majors as
today ("re-upload the file" for stage 1, "re-analyse this run" for stages
2-3): the user answers again in Review. Carrying answers across a major is
not proposed (no reader of an older plan exists).

**NOT YET VALID as the anchor: the fourth review found it wrong (section 9,
review 4 #1, #7, #8, #14); it is corrected with Thach's answers to review 4.**

**The demo files, on today's code - THE REGRESSION ANCHOR** (Thach,
2026-09-28): the implementation sessions 2E-t1..t3 re-measure on the built
code, and every demo difference must be one listed here; a difference not
listed stops the run. The new reported figures (`unmeasurable`, the
outside-revenue totals, `return_rate_note`, the identity's terms) are
additions, not differences:

- *Online Retail II, Thach's classes, unmapped signals*: rules 7-9 reproduce
  today's sale and return lines and every month's net revenue (measured,
  review 3); the counted lines are today's, so customer presence, the bridge
  and the product dimension are unchanged; the zero-amount lines become
  stock classes (no money); the 18 zero-amount postage lines stay `charge`.
  No revenue, product table or headline moves.
- *With C mapped as a credit*: nothing changes (credit = the signs).
- *If Thach also confirms the gift-voucher class*: those lines leave revenue
  in SIX months - 2010-01 (the -69.56 voucher refund, +69.56), 2010-10
  (127.65) and 2010-11 (51.06) (months seasonality reads), 2011-09 (25.00),
  2011-10 (16.67), 2011-12 (8.33) - and 2011-11's headline figures would
  read "from 1,087,751.92 ... (+392,132.21)"; its rule and its 86% must be
  re-measured, not assumed (the 86% was measured only with cancellations
  removed; review 3 #8).
- *Unanswered*: every line placed as today; no revenue, product table or
  headline moves.
- *If cancellations were applied* (question 1; review 1 #8, measured by
  removing the one-price pairs): 2011-11's headline is byte-identical, but
  P3 goes partial -> ruled_out (share 0.0978 -> 0.0446), P1 0.2897 -> 0.2634,
  B1 0.369 -> 0.384, and metrics.json's `return_rate` 0.1475 -> 0.1387
  (2011-10: 0.1688 -> 0.1585).
- *Kaggle*: no negative, zero or unpriced counted line; its payment method
  mapped as a type maps nothing; its 1,213 unmeasurable lines are now
  REPORTED (they are counted nowhere, as today): every figure unchanged, a
  new count in metrics.json.

## 7. Proposed implementation split (Thach expects 2-3 sessions)

1. **2E-t1 - the classifier and the stage 1 contracts.**
   `stages/ingest/line_taxonomy.py` (the three questions, the signals, the
   rules of 4.2, the suggestions), the four `cleaned.csv` columns, the stage
   1 majors, the combination test, the "exactly one class" test, the demo
   measurement of the classes.
2. **2E-t2 - stages 2 and 3 read the class.** `shared/line_effects.py`
   (the matrix), `parse_transactions` reading `line_class`, the identity,
   `unclassified` and `unmeasurable` in metrics.json (decision 7: the
   unmeasurable lines reported here), the stock ledger in magnitudes
   (decision 6: the ledger fix here), `return_rate_note` (decision 1), the
   lenses by class in diagnosis.json, every earlier test retargeted by the
   migration table, both demo files measured against section 6.
3. **2E-t3 - Review.** The signal mappings (types, prefixes), the direction
   mapping of zero-amount (description, sign) pairs, the suggestions to
   confirm, the identity line and the unclassified share (frontend, by
   `docs/FIGMA_DESIGN_NOTES.md`).

**Before 2E-t1:** the fourth fresh-context review of this revision (section
9). The Online Retail II demo build follows 2E-t3. **Not in this split**
(Thach, decision 8): Kaggle's payment method mapped as `transaction_type` is
a separate item - the schema prompt was fixed earlier, but the demo run
holds the old inference; stage 1's schema inference is re-run on Kaggle when
the demo is rebuilt (a real API call) to confirm the fix holds.

## 8. Decisions (Thach, 2026-09-28 - the eight questions answered)

1. **Cancellations**: out of v1; a same-day credit stays a return. The return
   rate is labelled honestly wherever it is shown: it includes same-day
   cancellations, which the data cannot separate (4.4; `return_rate_note`).
2. **Refusals**: none in v1. `unclassified` stays the tested, empty class.
3. **Returns to stock**: only under a type mapped `return`, as designed.
4. **Gift cards**: agreed - outside revenue and not counted once the user
   confirms; `gift_card_redemption` kept.
5. **Zero-amount direction**: NO default. "Negative = out, positive with no
   customer = in" is inferred from Online Retail II alone, and applying it to
   every file is a guess. Unknown stays unknown: velocity null with its
   reason. The cost falls only on files with stock-in lines; neither demo has
   one.
6. **The stock ledger fix**: in 2E-t2, as recommended.
7. **Reporting unmeasurable lines**: in 2E-t2, as recommended.
8. **Kaggle's payment method as `transaction_type`**: a separate item (section
   7): re-run stage 1's schema inference on Kaggle when the demo is rebuilt.

## 9. Reviews (fresh context, 2026-09-27)

**Review 1** (the first draft, eleven findings): negative-price lines sent
to `unclassified` (moving unanswered headlines, against Q3); a C-prefix
mapping overriding Thach's classes; pooled refunds made sales; coupons at a
negative price out of revenue; the matrix's signs against its own identity;
the customer bridge broken; a cancellation matcher that removes re-issued
sales; unmeasured demo differences; free items into stock the wrong way;
figures the scripts did not print. Reproductions: scratchpad `2et/review/`.

**Review 2** (the first revision, eleven findings): an allowance left its
product's tables; the class table was not total once a signal disagreed
with the signs, and zero-amount postage became goods; a prefix delivered an
item class; a "don't know" answer took revenue out against Q3; the customer
columns contradicted 3C, RFM and the first-day netting; unconfirmed zero
lines make velocity null; the units of the answers were undefined; a P4
line count that does not exist; Kaggle's unmeasurable lines reported
nowhere today; carrying answers across a major has no reader. Folded in.
Reproductions: scratchpad `2et/review2/`.

**Review 3** (the second revision, nine findings): signals of kind `sale`
or `stock out` on money lines moved every sale or every return to
`allowance`; `stock in` overrode the item answer and dropped money
unreported; the direction per description could not place mixed-sign
descriptions, the SUPPRESS was unsized and the ledger arithmetic unstated;
the stock classes and gift cards changed `counted`'s readers; pooled
returns left the first-day netting; signal precedence and the suggestion
cell were undefined; overlapping counts; the gift-voucher difference
incomplete; the totality test's inputs. Folded into the third revision.
Reproductions: scratchpad `2et/review3/`.

**Review 4** (after Thach's answers, 2026-09-28; seventeen findings, every
figure re-run on today's code - scratchpad `2et_rev/review4/`). **The run
stopped here, by Thach's condition** (a finding that fabricates or needs his
definition). The design's other figures re-ran as written (the class-table
counts, the 1,710 active customers, 857 / 832 of 2,889 products, the
gift-voucher headline, Kaggle's 1,213 = 604 + 609).

- *Would FABRICATE, need his definition:* #4 the magnitude ledger turns a
  receipt correction booked -30 under "in" into +30 (99 days to stockout,
  the truth 39); #5 a customer return is "back in stock NOT known" in 2.1
  but moves no stock in the ledger, days printed with no caveat (19 days) -
  the guess decision 5 rejected; #6 SPECS' "in" means "stock received, e.g.
  a purchase or a return" (the schema prompt), so a refund typed "in" never
  reduces revenue (net 50 where it is 40); #9 unanswered, the identity's
  "discounts" term is all bad debt (Online Retail II's B lines) while the
  real Discount lines read as returns; #10 Q3's "marked unconfirmed" never
  leaves cleaned.csv - unanswered, DOTCOM POSTAGE is the top product,
  unmarked (older); #11 a C prefix mapped `return` restocks goods (decision 3
  says a TYPE), and rule 5 flips a positive C line (-747.14 in 2010-02).
- *Need his definition:* #2 SPECS' type "out" pre-mapped to `sale` sends a
  zero-amount "out" write-off to `stock_count` (null) - the design's own
  57-days example gives null, not 17 - and a (description, sign) pair's
  "description" is the product name on the canonical schema (one question
  per product); #7 a confirmed discount stops refusing B2 (the demo's B2
  evidence changes; negative charges undefined); #12 `free_item` sets a
  direction by rule (703 of 759 on customer-less invoices), against decision
  5; #13 Kaggle's stored run is unreadable by today's code and decision 8
  re-runs its inference - its baseline must be pinned; #16 the product
  dimension's "(not a product)" bucket (charges and discounts keep the
  dimension summing to the change) against the matrix's "no"; #17
  unmeasurable lines' money (Kaggle's 609 unpriced lines carry Total Spent
  79,072.50), their overlap with `undated_lines`, the return-rate note on a
  file with no returns, a mapped direction outranking the `free_item` rule,
  a type mapped "not a signal" against a prefix, reserved column names
  already in a file, a gift-card line under a `return` type.
- *The author's to correct (no definition needed), with the next revision:*
  #1 the gift vouchers sit in 24 of 25 months, not six (2010-01 moves by
  +1.48, not 69.56), and move ~107 output values; #3 rule 1's "non-finite
  amount" sends an unpriced stock-in line to `unmeasurable` before rule 2
  (2E-g F1 reopened); #8 the cancellations bullet must leave the anchor
  (decision 1); #14 the anchor must list metrics.json's `non_product` block
  changes; #15 "counted = today's counted" is false for a charge under "in"
  and an overflowing amount.

**Questions for Thach after review 4** (the author's recommendation after
each; his answers become decisions 9 onwards, then a revision and a fifth
review):

9. *A stock line with the minority sign for its signal* (#4, a -30 under
   "in"): recommended - magnitudes only for zero-amount lines whose direction
   is mapped; such a line is counted, reported, and makes the product's days
   to stockout null with its reason - never flipped.
10. *Returns whose restocking the file does not say* (#5): recommended -
    days to stockout as a lower bound, "at least N days - returns not counted
    back into stock" (stock can only be higher); or null with its reason.
11. *Money on a line typed "in"* (#6): recommended - two answers in Review,
    "stock received from suppliers" (outside revenue) and "returns from
    customers" (`return`); unanswered, the amount's sign decides the money;
    SPECS and the schema prompt drop "e.g. a purchase or a return".
12. *The identity's term for unconfirmed negative lines* (#9): recommended -
    "other deductions (unconfirmed)"; only confirmed lines are "discounts".
13. *The "unconfirmed" mark downstream* (#10): recommended - stages also read
    the suggested class; a product carrying an unconfirmed suggestion is
    marked in the product tables and in a headline naming it.
14. *A credit prefix mapped `return`* (#11): recommended - never restocks,
    never flips a sign; positive lines on credit notes keep their signs'
    reading and are counted in a reported total.
15. *The canonical type "out" and the direction question* (#2): recommended -
    "out" gives a zero-amount line its direction (the file's own signal);
    the direction is asked per sign, descriptions shown as examples, with a
    per-description override.
16. *`free_item`'s direction* (#12): recommended - unknown until mapped
    (decision 5; 29% -> 34% null on Online Retail II's shape).
17. *B2 and negative charges* (#7): recommended - B2 unchanged in 2E-t, its
    relaxation for confirmed discounts to Phase 8; a negative charge is other
    revenue, negative.
18. *Kaggle's baseline* (#13): recommended - pinned before 2E-t1 as today's
    code re-executing the stored run's approved plan (no AI call); decision
    8's re-run after 2E-t3, compared on its own.
19. *The product dimension* (#16): recommended - two matrix columns, the
    product tables (no) and stage 3's product dimension (the "(not a
    product)" bucket, as today).
20. *The small ones* (#17): recommended - unmeasurable lines reported with
    their count and the money they carry, never derived; a line both undated
    and unmeasurable reported once, as unmeasurable; the return-rate note
    only on a file with returns; a mapped direction outranks `free_item`; a
    type mapped "not a signal" silences the type only; a file's own column
    named like a new one is kept with a `_source` suffix, said in Review; a
    gift-card line under a `return` type follows its item (outside revenue).
