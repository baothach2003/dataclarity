# Line taxonomy - design (session 2E-t), v1: the money ledger

**Status: APPROVED IN PRINCIPLE (Thach, 2026-09-28), revision 2 with his v1
scope cut and his answers to review 4 (section 8). The fifth fresh-context
review found findings that fabricate and need his definition (section 9):
waiting for his answers, then revision 3 and a sixth review. Nothing here is
built.** The decision record is
`docs/adr/0008-line-taxonomy.md`. Written 2026-09-27 (fifth overnight run)
from Thach's brief in PROJECT_PLAN item 2E-t (a)-(e) and his answer to Q3
of the fourth run; revised after each of four fresh-context reviews and with
his two sets of answers (sixth and seventh runs). Every figure is measured on
today's code (HEAD df580c3; the code as at 99e9eb2) by the scripts in the
scratchpad's `run7/2et/` - the earlier revisions' in `2et/` and
`2et_rev/review4/`; the implementation sessions re-measure on the built code.

## 0. The v1 scope (Thach, 2026-09-28)

**v1 is the MONEY ledger only.** The taxonomy decides what each line does to
revenue, orders, units, returns, customers and the product tables. It does
not keep a stock ledger, and it reads no source signal the user maps:

- **Every stock KPI** - velocity, days to stockout, any low-stock figure -
  reads "not supported in v1", with that reason, on EVERY file, rather than a
  figure that can be wrong. This retires 2C's sign defect (a zero-amount -20
  line added 20 to the computed stock). The Dashboard's low-stock table (6F,
  7C) is out of v1; the README says v1 analyses sales, not inventory.
- **No source-signal mappings**: transaction-type values and invoice prefixes
  are not mapped to return / restock / stock in / stock out in Review. The
  canonical `transaction_type` keeps the one reading it has always had (2A),
  with Thach's Q15 for its negative lines (section 2).
- **One no-money class**: without a stock ledger a zero-amount line's
  direction does not matter, so the five classes the fourth revision had
  (`free_item`, `stock_write_off`, `stock_found`, `stock_count`,
  `no_movement`) are ONE: `no_money` - counted, no money, present in the
  product dimension as today.
- The stock ledger, the signal mappings, the split of `no_money`, and the
  questions review 4 left on them (#2, #4, #5, #11, #12) are the v2 item in
  PROJECT_PLAN's Backlog.

## 1. Why

The engine decides what a line *is* from the signs of its quantity and
amount, in several places, and the list of meanings grew one class per
incident. Signs are lossy - a coupon and a refund both carry a negative
amount - and nothing records whether a class came from the user or from a
rule. This design replaces the inference with ONE classification, made once
in stage 1, on accounting categories, with one table of effects that stages
2 and 3 read.

### 1.1 What the engine infers today

| # | Rule today | Where | Decides | In v1 |
|---|---|---|---|---|
| 1 | `transaction_type` "in" is stock received, out of revenue; any other value a sale | `shared/transactions.line_numbers` (2A) | revenue scope | kept for an amount >= 0 or no price; a negative "in" line is in revenue by its item (Q15, section 2). Kaggle maps its *Payment Method* as `transaction_type` (a separate item - decision 8); none of its values is "in" |
| 2 | sale = counted, qty > 0, amount > 0, not a discount or charge | `parse_transactions` (2E, 2E-c, 2E-l) | orders, units, gross sales, products | rule 8 of 4.2: the same lines. A gift voucher sold is a sale until the user confirms the gift-card class (Online Retail II: 77 lines, +1,756.17) |
| 3 | return line = counted, qty < 0, amount < 0 | same (2E-c2) | returns, return rate, the returns lens | rule 9: the same lines. All 19,493 such lines of Online Retail II sit on C (credit) invoices; same-day cancellations among them cannot be told apart (4.4) |
| 4 | deduction = counted and none of the above | same (2E-c, 2E-c2) | the returns lens's `deductions`, P4 | `allowance` (money, unconfirmed), `discount` (confirmed), `no_money` (none): the same lines, named apart in metrics.json's identity |
| 5 | the user's classes: charge, discount, pooled, cost, adjustment, "a product" | `shared/line_classes.py`, stage 1's `non_product_lines.py` (2E-d2, 2E-l) | revenue scope, orders, the product tables | the item question (2.1), plus `gift_card`; an unanswered suggestion is recorded and carried downstream (Q17) |
| 6 | a line with neither SKU nor name is the gap | `shared/products.py` (2E-g) | never ranked; the lens's `unidentified` | the pooled item by rule, as today |
| 7 | stock on hand from the stock-in lines against every counted line | `metrics_products._velocity` (2C, 2E-g) | days to stockout | **removed**: "not supported in v1" on every file (section 0). The defect it retires: 100 received, 63 sold, 20 more removed read 57 days to stockout instead of 17 (`2et/ledger_sign.py`) |
| 8 | B2 is refused on any return line or negative-amount counted line | `hypothesis_evidence_lever.b2` (2E-c2) | the basket hypothesis | unchanged (Q21) |
| 9 | the first day nets per product and class key | `shared/first_purchase.py` (2E-f, 2E-d2) | new / resurrected customers | unchanged: it reads the same lines |
| 10 | a receipt is judged on its sale / return / counted / out-of-revenue lines | `shared/orders.py` (2E-e, 2E-e2, 2E-k) | the order basis, the customer fill | unchanged: it reads the same lines |
| 11 | a line with no parseable quantity or price is counted nowhere | `parse_transactions` (`valid`) | every figure | `unmeasurable`, REPORTED with its reason (decision 7): Kaggle's 1,213 lines - 604 with no quantity, 609 with no price, 9.6% of the file - left revenue silently |

Each stage recomputes rules 1-6 from the raw columns and the answers
(`parse_transactions` runs in stage 2 and again in stage 3); they agree only
because they share code.

## 2. The model: what the item is, and what the line does

A line's class is decided on two questions:

- **The item** - what the key (its SKU, else its name) is: a `product`, a
  `pooled` code (many items under one code - M "Manual" - and, by rule,
  every line with neither SKU nor name), a `charge` the customer pays, a
  `discount`, a `gift_card`, a `cost` (a fee or cost the business pays), an
  `adjustment`. Today's per-key answers (`shared/line_classes.py`) are
  exactly this question; v1 adds `gift_card`. The class keeps today's name
  `cost` (the fourth revision called it `fee`): renaming it would change the
  contracts, Review and metrics.json's `non_product` rows for no gain.
- **The line** - what it does to money, read from the sign of its amount
  (quantity x unit price). A credit note is read by its lines' signs, as
  today: a C line of a product is a return or an allowance by its signs, a C
  line of postage a postage refund (still a `charge`, negative - Thach's Q21:
  other revenue, negative), a C line of a fee a fee reversal (still a
  `cost`). **The one source signal v1 reads is the canonical
  `transaction_type`'s "in"** (2A), as Thach's Q15 defines it: the amount's
  sign decides. A negative amount is money going back to a customer - in
  revenue, through the line's item (a product or pooled item's line is a
  return whatever its quantity's sign, its units counted back); an amount
  of 0 or more, or no price, is stock received - outside revenue, reported
  with its lines and money. No Review question. The schema prompt drops
  "e.g. a purchase or a return" from its "in" (2E-t1); SPECS section 9
  states the rule.

### 2.1 The closed class list (brief a)

The accounting test for money: *tied to the sale* (revenue or
contra-revenue) or *tied to the cost of earning it* (an expense, outside
revenue). Every line of the file gets exactly one class. Online Retail II is
the whole file (1,067,371 lines); "classed" is Thach's classes (POST, DOT, C2
and 23444 charges, D discount, AMAZONFEE, CRUK, BANK CHARGES and S costs, B,
ADJUST and ADJUST2 adjustments, M pooled), "unanswered" none
(`run7/2et/proto.json`).

| Class | Counted | Accounting | Online Retail II classed | unanswered | Kaggle |
|---|---|---|---|---|---|
| `sale` | yes | revenue: gross sales | 1,037,029 lines, +20,110,963.19 | 1,041,671, +20,972,968.14 | 11,362, +1,472,998.50 |
| `pooled_sale` | yes | revenue: gross sales, never a ranked product | 882, +341,104.90 (M) | - | - |
| `customer_return` | yes | contra-revenue: sales returns | 18,290, -726,633.05 | 19,493, -1,527,041.43 | - |
| `pooled_return` | yes | contra-revenue: sales returns, never ranked | 537, -423,886.17 (M) | - | - |
| `allowance` | yes | contra-revenue, UNCONFIRMED: a money line of a product or pooled item that is neither a sale nor a return by its signs (a negative price: a refund, a coupon, a bad-debt write-off) | - | 5, -158,676.14 (B "Adjust bad debt") | - |
| `discount` | yes | contra-revenue: a discount the user confirmed | 177, -13,484.54 (D) | - | - |
| `charge` | yes | other revenue (a negative one is a charge refunded) | 3,931, +449,559.47 | - | - |
| `no_money` | yes | no money: a product or pooled line with an amount of 0 (a free item, a write-off, a count, a quantity of 0) | 6,184 | 6,202 | - |
| `gift_card_sale` | **no** | a liability (deferred revenue), outside revenue, reported - only once the user confirms the item | (77 money lines, +1,756.17, and 22 of 0, if confirmed) | - | - |
| `gift_card_redemption` | **no** | settles or reverses the liability, outside revenue, reported | (1 line, -69.56, if confirmed) | - | - |
| `cost` | **no** | expense, outside revenue, reported | 265, -310,325.44 | - | - |
| `adjustment` | **no** | outside revenue, reported (bad debt is an expense) | 76, -140,047.79 | - | - |
| `stock_in` | **no** | stock received: outside revenue, reported with its lines and money | - | - | - |
| `unclassified` | **no** | isolated, reported (4.3) | **none** | **none** | **none** |
| `unmeasurable` | **no** | no finite quantity, no price (unless "in"), or an amount too large to add: counted nowhere, reported with its reason | - | - | 1,213 (604 no quantity, 609 no price) |

The classes marked "yes" are counted; a counted line also needs a date to be
in a month (4.2).

**What the code distinguishes today maps in without loss:** sale -> `sale`;
return line -> `customer_return`; deduction -> `allowance` (money, not
classed), `discount` (classed) or `no_money` (none); pooled and the gap ->
`pooled_sale` / `pooled_return`; `charge`, `cost`, `adjustment` -> the same;
"in" -> `stock_in`; invalid -> `unmeasurable`, or its own class when only
the date is missing (4.2).

`cancellation` is NOT in the list: 4.4.

## 3. The effects matrix (brief b) - the single source of truth

One table, in one module (`shared/line_effects.py`), read by stages 2 and 3.
Every money column sums the lines' amounts AS SIGNED; returns, discounts and
other deductions are REPORTED as the magnitude of what they took away
(returns = -(sum of return amounts)), as the returns lens stores them today.
**The identity: net revenue = gross sales - returns - discounts - other
deductions (unconfirmed) + other revenue**, to float residue (Thach's Q16:
"other deductions (unconfirmed)" until confirmed; only lines the user
confirmed as discounts are "discounts").

| Class | Gross sales | Returns | Discounts | Other deductions (unconfirmed) | Other revenue | Net revenue | Customer money | Customer presence | Purchase | First-day netting | Units | Return rate | Product tables (stage 2) | Product dimension (stage 3) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sale` | + | | | | | + | + | yes | yes | yes | + qty | denominator | yes | its product |
| `pooled_sale` | + | | | | | + | + | yes | yes | yes | + qty | denominator | no | the gap bucket |
| `customer_return` | | + | | | | + | + | yes | no | yes | - abs(qty) | numerator | yes | its product |
| `pooled_return` | | + | | | | + | + | yes | no | yes | - abs(qty) | numerator | no | the gap bucket |
| `allowance` | | | | + | | + | + | yes | no | no | no | no | yes (its product's revenue) | its product |
| `discount` | | | + | | | + | + | yes | no | no | no | no | no | "(not a product)" |
| `charge` | | | | | + | + | + | yes | no | no | no | no | no | "(not a product)" |
| `no_money` | | | | | | none | none | yes | no | no | no | no | present, no money | its product (present) |
| `gift_card_sale`, `gift_card_redemption`, `cost`, `adjustment`, `stock_in` | | | | | | outside - reported | none | no | no | no | no | no | no | no |
| `unclassified` | | | | | | outside - isolated, reported | none | no | no | no | no | no | no | no |
| `unmeasurable` | | | | | | counted nowhere - reported (lines, reason) | none | no | no | no | no | no | no | no |

- **The customer columns reproduce today's rules**: *customer money* (the
  bridge, RFM monetary) = every line in net revenue with a customer;
  *customer presence* (active customers, the RFM population - 3C: a
  returns-only customer is active) = every counted line with a customer
  (2011-11 classed: 1,710 active, 1,662 buyers - `run7/2et/m8.out`);
  *purchase* (orders, frequency, recency) = the sale lines; the first-day
  netting (2E-f) reads sale and return lines of products and pooled items.
- **The two product columns** (Thach's Q23): stage 2's product TABLES rank
  products only; stage 3's product DIMENSION keeps every counted line so it
  sums to the change - charges and discounts in its "(not a product)" bucket,
  pooled lines with the gap, as today.
- **Units**: a return's units are counted back as -abs(quantity), so a
  negative "in" line booked +5 at a negative price is 5 units back.
- **The return rate** (Thach, decision 1) carries `return_rate_note` in
  metrics.json - "it includes same-day cancellations, which the data cannot
  separate" - on a file with return lines only (Q24).
- **Stock**: no column in v1. `products.velocity` is null on every file with
  the reason that stock figures are not supported in v1 (section 0).

Every figure outside revenue (gift cards, costs, adjustments, stock
received, unclassified, unmeasurable) is reported in metrics.json with its
lines and money, never dropped silently.

## 4. Classification once, in stage 1 (brief c)

Stage 1 writes three columns into `cleaned.csv`:

- `line_class` - the class (2.1);
- `class_source` - `user` when the item answer decided it, `rule` otherwise
  (the brief's `class_source`);
- `suggested_class` - the suggestion pending on the line's key (a class word
  or a gift-card word, 4.1), blank when there is none or the user answered
  the key.

A source column already named like one of them is kept, renamed with a
`_source` suffix (numbered if that name is taken too), and Review says so
(Q24). Stages 2 and 3 read `line_class` and `suggested_class` only, through
`shared/transactions.py`, which refuses a value outside the closed list.

### 4.1 Evidence

| Question | Unit | 1. the user | 2. the rule | Suggestions (never applied alone) |
|---|---|---|---|---|
| the item | per key (SKU, else name; a name-only line inherits its one SKU's answer, as today) | the answer in Review | neither SKU nor name -> `pooled`; otherwise `product` | today's class words (charge, discount, pooled, cost, adjustment - `non_product_lines.py`), and gift-card words ("gift card", "gift voucher", "voucher", "gift certificate", "gift_") - at the start or end of the SKU or the commonest name, as today |
| the line | per line | - | the amount's sign; "in" as section 2 | - |

On Online Retail II the gift-card words match 9 keys, `gift_0001_10` to
`gift_0001_90`, all vouchers and no other key; 7 move money and become
candidates (60 and 90 move none, and a key that moves no money is not asked,
as today); Kaggle has no candidate (`run7/2et/m45.json`).

**A suggestion never applies itself** (2E-d2; Thach's Q3): a key the words
suggest is a charge but nobody confirmed keeps its rule-based class (`sale`),
so an unanswered file loses no revenue - and its suggestion travels with it.

### 4.2 From the answers to the class - a total table

In order, first match wins:

1. no finite quantity -> `unmeasurable` ("no quantity").
2. a price, but quantity x price is not finite -> `unmeasurable` ("amount
   too large to add"; today it is counted: its month's revenue is infinite,
   written as null, and the metrics.json does not read back - measured).
3. typed "in", and no price or an amount >= 0 -> `stock_in` (no price is
   needed, as 2E-g F1 decided for stock-in lines - review 4 #3).
4. no price -> `unmeasurable` ("no price").
5. the user's item: `charge`, `discount`, `cost`, `adjustment` -> that
   class, at any amount and sign (a zero-amount postage line stays a
   `charge` with no money); `gift_card` -> `gift_card_sale` for an amount
   >= 0, `gift_card_redemption` below 0.
6. a product or pooled item (P) typed "in" (its amount is negative here) ->
   P return (`customer_return`, `pooled_return` for pooled).
7. P with an amount of 0 -> `no_money`.
8. P, quantity > 0 and amount > 0 -> P sale (`sale`, `pooled_sale`).
9. P, quantity < 0 and amount < 0 -> P return.
10. P otherwise (a negative price) -> `allowance`.

**The date does not decide the class.** An undated line keeps its class and
is in no month: it is counted in no figure and reported in `undated_lines`
with the money it carries (2E-h) - except an `unmeasurable` line, reported
once, as unmeasurable (Q24). A line typed "in" with an amount >= 0 is
`stock_in` whatever its item, as today (out of revenue); with a negative
amount it takes its item's class, and so its revenue. Every combination of
the inputs (quantity finite or not and its sign, price present, amount
finite and its sign, typed "in", the item answer, SKU or name present) falls
in exactly one rule; the test covers each.

### 4.3 `unclassified`

Per Thach's Q3, only for a line no rule places. Section 4.2 places every
line, so nothing is `unclassified` on either demo file. **No refusals in
v1** (Thach, decision 2): it stays the tested, empty class, isolated, for a
shape a later decision may choose to refuse - never an answer a user gives (a
"don't know" that removed DOT's 36,905.40 from 2011-11's revenue would
contradict Q3; review 2 #4).

### 4.4 Why `cancellation` is not a class

A cancelled order never became revenue; a same-day return did; the data
cannot tell them apart. Review 1 measured 1,797 one-to-one same-day pairs of
a sale and a credit on Online Retail II, in 439 of which the credit is rung
BEFORE the sale it would cancel - a credit note for an old invoice followed
by a re-issue (`2et/review/pairs2.out`). **Decided (Thach, decision 1): out of
v1** - a same-day credit stays a return, and the return rate is labelled
honestly wherever it is shown (`return_rate_note`, section 3).

### 4.5 The suggestions downstream (Thach's Q17)

Stages 2 and 3 read `suggested_class` beside `line_class`: a product's
suggestion is its key's. Each contract that names products carries ONE map,
`suggested_classes`: every product it names - by its label, which is unique
(`shared/products.py`) - whose key carries an unconfirmed suggestion, with
that class. metrics.json names products in `top_products` and
`biggest_decliners`; diagnosis.json in the product dimension's members, new
and removed members, R1's top member and R3's products. Stage 5 and the
frontend print such a product as "<name> (suggested: <class>, not
confirmed)"; a headline that names a product (none does today - rules 5-7
name causes and lenses) does the same. Measured on the demo outputs
(`run7/2et/m4b.json`): unanswered, `{"DOTCOM POSTAGE": "charge"}` in
metrics.json (the top product of 2011-11, 36,905.40) and in diagnosis.json,
which also names `Dotcomgiftshop Gift Voucher £20.00` (a removed member) as
`gift_card`; classed, only that voucher, in diagnosis.json; Kaggle, none.

## 5. Guarantees (brief d)

- **Exactly one class per line**, tested on both demo files and on the
  sweeps: `line_class` has no blank and no value outside the list; the
  effects matrix has a row for every class (a test fails when a class is
  added without its effects); the rules of 4.2 are tested over every
  combination of their inputs.
- **The same lines**: on a file with no negative "in" line, no amount too
  large to add and no confirmed gift card, every set of lines today's
  readers use - valid, counted, sale, returned, charge, deduction, left out,
  units, and the lines the receipt fill may not read - is the same set under
  v1. Measured by a prototype of 4.2 beside today's `parse_transactions`:
  identical, line by line, on Kaggle and on Online Retail II in both states
  (`run7/2et/proto.py`, `proto.json`); 2E-t2 keeps that comparison as a test.
- **`unclassified` is isolated**, never assumed a sale: outside every
  revenue figure, its lines, money and share of the money moved in
  metrics.json and in Review. **`unmeasurable`** is counted nowhere and
  reported with its lines per reason; its money is unknown - that is why it
  is unmeasurable - and is never derived from another column (Kaggle's
  unmapped *Total Spent* holds 79,072.50 on its 609 unpriced lines, 5.1% of
  that column; the canonical schema has no line-total field -
  `2et_rev/review4/kaggle.out`).
- **The identity** holds for the compared months in metrics.json, to float
  residue (2011-11 classed: 1,460,682.95 - 28,259.70 - 474.85 - 0.00 +
  47,935.73 = 1,479,884.13, today's revenue; unanswered 1,509,496.33 -
  47,740.08 = 1,461,756.25; Kaggle 2024-12 46,292.50, all gross sales), and
  Review shows it for the whole file, computed by stage 1 (pandas) for the
  answers as they stand, with the outside-revenue totals beside it.

## 6. Migration (brief e)

**Earlier decisions it changes:**

| Decision | Becomes | What changes beyond where the rule lives |
|---|---|---|
| 2A: transaction type "in" is out of revenue | rule 3 (amount >= 0 or no price: `stock_in`); rule 6 and the item rules (a negative amount) | an "in" line with a negative amount is counted by its item (Q15): a product's is a return - its money in returns, its units back, the return rate, B2's refusal; stock-in lines are reported with their lines and money |
| 2C / 2E-g: the stock balance and velocity | none in v1 | `products.velocity` null on every file with the reason "not supported in v1"; the derivation from stock-in lines is removed, and its sign defect with it |
| 2E / 2E-c: a sale is qty > 0 and amount > 0 | rule 8 | nothing |
| 2E-c: the deduction bucket | `allowance` + `discount` + `no_money` | nothing in money; metrics.json's identity names discounts and other deductions apart |
| 2E-c2: a return line is qty < 0 and amount < 0 | rule 9 | nothing |
| 2E-c2: B2 refuses on return lines and negative-amount counted lines | kept exactly (Q21) | nothing; relaxing it for confirmed discounts is Phase 8 |
| 2E-c2: the return rate | the same figure | `return_rate_note` beside it, on a file with return lines |
| 2E-d2 / 2E-l: charge, discount, pooled, cost, adjustment answers | the item question, plus `gift_card` | a confirmed gift card leaves revenue; `non_product` gains a `gift_card` row then |
| 2E-g: the identity gap | the pooled item by rule | nothing (`unidentified` stays) |
| 2E-h: undated lines | the class is decided without the date | `undated_lines` no longer counts a line that is unmeasurable (reported once, there), and carries the money of the lines it counts |
| 3C doubt-review C2: a non-finite quantity or price is invalid | rules 1, 2 and 4 | a finite quantity and price whose product overflows is `unmeasurable` (today it is counted, and its month's revenue is written as null in a required field) |
| 2E-n: the products' share on their sale lines | on the `sale` class | nothing |

**Contract bumps.** `cleaned.csv` gains three columns. The stage 1
contracts that carry the line-class enum (it gains `gift_card`: closed
enums, so a major - CONTRACTS section 10) go to their next major, and
`cleaning_report.json` with them (its readers need the new columns);
readers refuse the earlier ones as today ("re-upload the file"), and the
user answers again in Review. `metrics.json` goes to 16.0 and
`diagnosis.json` to 17.0 (counted changes meaning for negative "in" lines;
`undated_lines`' meaning changes; the velocity reason; the additions below).

**THE REGRESSION ANCHOR** (Thach, 2026-09-28): the implementation sessions
2E-t1..t3 re-run the demo files on the built code, and every difference from
the pinned baselines must be one listed here; a difference not listed stops
the run.

*The pinned baselines* - today's code, `NOW` 2026-09-26:

- *Online Retail II*, the whole file (current month 2011-11), mapped
  Invoice / StockCode / Description / Quantity / InvoiceDate / Price /
  Customer ID, in two states: classed and unanswered
  (`run7/2et/orii_pin/baseline_classed.json`, `baseline_unanswered.json`:
  metrics.json and every stage 3 output). Headlines: classed "Revenue went
  from 1,087,768.59 to 1,479,884.13 (+392,115.54). The change is consistent
  with seasonality (...): 86% of the change."; unanswered "from 1,070,704.67
  to 1,461,756.25 (+391,051.58) ... 99% of the change."
- *Kaggle*, pinned as Thach's Q22 asked: today's `execute_run` re-executing
  the stored run's approved plan (every column `flag_only`, its mapping; no
  AI call) on its raw.csv writes a cleaned.csv byte-identical to the stored
  one; then stages 2 and 3 (`run7/2et/kaggle_pin/`). Current month 2024-12;
  headline "Revenue went from 41,367.50 to 46,292.50 (+4,925.00). The
  best-supported explanation: customers bought more lines (lever lens, 96% of
  the change)." Decision 8's re-run of the schema inference is a separate
  item, compared on its own.

*The differences allowed, on every demo run:*

1. **Versions**: the stage 1 contracts' majors, metrics.json 16.0,
   diagnosis.json 17.0.
2. **`products.velocity_reason`**: today "the file has no stock-in lines
   (transaction type "in"), so stock on hand cannot be derived..." on all
   three runs; v1's "not supported in v1" reason. `velocity` stays null.
3. **Additions** (new fields, nothing removed): cleaned.csv's three columns;
   metrics.json's identity terms for the compared months, the
   outside-revenue totals, the unmeasurable report, `return_rate_note`,
   `undated_amount` beside `undated_lines`, `suggested_classes`;
   diagnosis.json's `suggested_classes`.
4. **Stage 1's line-class candidates** on Online Retail II gain the 7
   gift-voucher keys (`gift_0001_10`, `_20`, `_30`, `_40`, `_50`, `_70`,
   `_80`), suggested `gift_card`, among today's 13 (ordered by lines, as today).

*Their values on the demo runs* (measured, `run7/2et/`):

- *Online Retail II classed*: identity 2011-11 1,460,682.95 / 28,259.70 /
  474.85 / 0 / 47,935.73 = 1,479,884.13; 2011-10 1,128,115.16 / 66,602.40 /
  56.08 / 0 / 26,311.91 = 1,087,768.59. Outside revenue 2011-11: cost 13
  lines, -18,127.88; 2011-10: cost 18 lines, -17,063.92. Unmeasurable 0;
  undated 0; `return_rate_note` present. `suggested_classes`: metrics.json
  none, diagnosis.json `Dotcomgiftshop Gift Voucher £20.00` gift_card.
  `non_product` unchanged (charge, discount, pooled, cost, adjustment rows).
- *Online Retail II unanswered*: identity 2011-11 1,509,496.33 / 47,740.08 /
  0 / 0 / 0 = 1,461,756.25; 2011-10 1,154,979.30 / 84,274.63 / 0 / 0 / 0 =
  1,070,704.67 (the 5 B lines, the file's only other deductions, fall in
  neither month). Nothing outside revenue; unmeasurable 0; undated 0;
  `return_rate_note` present. `suggested_classes`: metrics.json `DOTCOM
  POSTAGE` charge; diagnosis.json that and the voucher. `non_product` empty,
  as today.
- *Kaggle*: identity 2024-12 46,292.50 gross sales = net; unmeasurable 1,213
  (604 no quantity, 609 no price), their money unknown; undated 0; no
  `return_rate_note` (no return line); no suggestion; nothing outside revenue
  except the unmeasurable lines.

Every other leaf of metrics.json and of stage 3's outputs is identical, the
three headlines byte-identical: the counted lines, and every set built on
them, are today's (section 5).

*A documented class change, NOT the demo state*: if Thach confirms the
gift-voucher keys as `gift_card` (classed), their lines leave revenue in 24
of the file's 25 months (all but 2011-11): 2009-12 by -217.37, 2010-01 by
+1.48 (a -69.56 refund and 68.08 of vouchers), ... 2011-10 by -16.67,
2011-12 by -8.33 (the month-by-month list: `run7/2et/orii_pin/orii_summary.json`).
107 leaves of the 2011-11 outputs move (metrics.core 27 - the 24 months,
`revenue_previous`, `aov_previous`, `revenue_change_pct`; localization 20;
signals 19; hypotheses' contributions, shares and evidence 24; the tree 16;
the headline 1); no verdict changes. The headline reads "from 1,087,751.92 to
1,479,884.13 (+392,132.21)", still rule 5, seasonality, 86% (0.8617, from
0.8614) (`gift_confirmed_diffs.json`).

## 7. Implementation split (Thach expects 2-3 sessions)

1. **2E-t1 - the classifier and the stage 1 contracts.**
   `stages/ingest/line_taxonomy.py` (the rules of 4.2, the item answers and
   their inheritance, the suggestions with the gift-card words), the three
   `cleaned.csv` columns and the reserved-name rename, `gift_card` in the
   line-class enum, the stage 1 majors, the schema prompt's "in", the
   combination test, the "exactly one class" test, the demo measurement of
   the classes against section 2.1.
2. **2E-t2 - stages 2 and 3 read the class.** `shared/line_effects.py` (the
   matrix), `parse_transactions` reading `line_class` and `suggested_class`,
   the identity, the outside-revenue totals, `unclassified` and
   `unmeasurable` in metrics.json (decision 7), `undated_amount`,
   `return_rate_note` (decision 1), `suggested_classes` (Q17), velocity "not
   supported in v1" and the stock derivation removed, the equivalence test of
   section 5, every earlier test retargeted by the migration table, both demo
   files measured against the anchor.
3. **2E-t3 - Review.** The `gift_card` answer and the gift-card candidates,
   the identity line for the whole file (stage 1 computes it for the answers
   as they stand), the unclassified and unmeasurable counts, the
   reserved-name notice (frontend, by `docs/FIGMA_DESIGN_NOTES.md`).

The Online Retail II demo build follows 2E-t3. **Not in this split**
(decision 8): Kaggle's payment method mapped as `transaction_type` - stage
1's schema inference is re-run on Kaggle when the demo is rebuilt.

## 8. Decisions (Thach, 2026-09-28)

After the fifth run (the fourth revision's eight questions):

1. **Cancellations**: out of v1; a same-day credit stays a return; the return
   rate is labelled honestly wherever it is shown (`return_rate_note`).
2. **Refusals**: none in v1. `unclassified` stays the tested, empty class.
3. **Returns to stock**: only under a type mapped "return" - moot in v1 (no
   stock ledger; the v2 item).
4. **Gift cards**: outside revenue and not counted once the user confirms;
   `gift_card_redemption` kept.
5. **Zero-amount direction**: no default - moot in v1 (one `no_money` class;
   the v2 item).
6. **The stock ledger fix** - superseded by the v1 scope cut: every stock KPI
   "not supported in v1".
7. **Reporting unmeasurable lines**: in 2E-t2.
8. **Kaggle's payment method as `transaction_type`**: a separate item.

After the sixth run (review 4's questions; the design's 9-20 are the
report's Q13-Q24):

- **The v1 scope cut** (section 0). Questions 9, 10, 14, 15, 16 (Q13, Q14,
  Q18, Q19, Q20) are moot; they are the v2 item's, with review 4's #4, #5,
  #11, #2, #12.
- **Q15** (11): a line typed "in" - the amount's sign decides (section 2).
- **Q16** (12): "other deductions (unconfirmed)" until confirmed.
- **Q17** (13): the stages read the suggested class; the product tables and
  any headline naming such a product show it (4.5).
- **Q21** (17): B2 unchanged; its relaxation for confirmed discounts is
  Phase 8; a negative charge is other revenue, negative.
- **Q22** (18): Kaggle's baseline pinned before 2E-t1 (section 6).
- **Q23** (19): two product columns (section 3).
- **Q24** (20): unmeasurable lines reported with their count and reason,
  their money never derived; a line undated and unmeasurable reported once,
  as unmeasurable; the return-rate note only on a file with returns; a
  source column named like a new one kept with a `_source` suffix, said in
  Review. (A mapped direction against `free_item`, a type "not a signal"
  against a prefix, a gift card under a `return` type: moot with the cut.)

**Taken by the author in revision 2, for Thach to see** (none changes a demo
figure; labelled A1-A6, not D, so they are not read as the sixth run's D1-D6
he accepted - review 5 #10): a line typed "in" with an amount >= 0 is
`stock_in` whatever its item, as today, and a negative one takes its item's
class (A1 - open, question 21); `cost` keeps its name (A2); the date does not
decide the class (A3); R3 ("a top product may have run out of stock") stays
- it reads the sales pattern, never stock, and says "verify on the shelf"
(A4 - open, question 23); the returns lens keeps its four terms,
`deductions` = discounts + other deductions, and P4 already reads "Discounts
and other deductions" (A5); the no-money class is named `no_money` (A6).

## 9. Reviews (fresh context)

**Review 1** (the first draft, 2026-09-27, eleven findings): negative-price
lines sent to `unclassified`; a C-prefix mapping overriding Thach's classes;
pooled refunds made sales; coupons out of revenue; the matrix's signs against
its identity; the customer bridge broken; a cancellation matcher removing
re-issued sales; unmeasured demo differences; free items into stock the wrong
way. Reproductions: scratchpad `2et/review/`.

**Review 2** (eleven findings): an allowance left its product's tables; the
class table not total once a signal disagreed with the signs; a prefix
delivering an item class; a "don't know" answer taking revenue out against
Q3; the customer columns against 3C, RFM and the first-day netting; Kaggle's
unmeasurable lines reported nowhere. `2et/review2/`.

**Review 3** (nine findings): signals on money lines moving every sale or
return to `allowance`; `stock in` overriding the item answer; the direction
per description; the stock classes and gift cards changing `counted`'s
readers; pooled returns leaving the first-day netting; the suggestion cell.
`2et/review3/`.

**Review 4** (2026-09-28, seventeen findings; `2et_rev/review4/`) - the run
stopped for Thach. Six would fabricate: a -30 receipt correction read +30 by
the magnitude ledger (#4); a customer return moving no stock with no caveat
(#5); a refund typed "in" never leaving revenue (#6); unanswered "discounts"
that were all bad debt (#9); the "unconfirmed" mark never reaching stages 2
and 3 (#10); a credit prefix mapped `return` restocking and flipping a sign
(#11). Others needed his definition (#2, #7, #12, #13, #16, #17), and the
anchor had errors (#1 the gift vouchers in 24 months, not six; #3 rule 1
before rule 2; #8 the cancellations bullet; #14 the `non_product` block; #15
"counted = today's"). **Revision 2** answers them: #2, #4, #5, #11, #12 leave
with the scope cut (the v2 item); #6 by Q15 (section 2); #9 by Q16; #10 by
Q17 (4.5); #7 by Q21; #13 by Q22 (the Kaggle pin); #16 by Q23; #17 by Q24;
#1 and #8 in the rebuilt anchor; #3 by rule 3 before rule 4; #14 - the
`non_product` block keeps today's rows (`cost` keeps its name, D2); #15 -
section 5 states the exceptions and the prototype measures the rest.

**Review 5** (revision 2, 2026-09-28; sixteen findings, reproductions in
`run7/2et/review5/`). **The run stopped here, by Thach's condition.** Checked
and correct: the class counts and money of 2.1 (they sum to 1,067,371
lines), both identities in both states, the three headlines, the 13 + 9 (7
with money) candidates, the 223 fee lines, Kaggle's 604 / 609.

- *Would FABRICATE, need his definition:* **#1** Q15's sign rule turns a
  priced receipt correction typed "in" (-30 @ 4.00) into a customer return:
  -120 of revenue and a return line where today the line is outside revenue -
  the data cannot tell a supplier correction from a refund. **#2** a customer
  return booked the canonical way (SPECS 9: +2 @ 5, typed "in") stays stock
  received - net revenue 50 where the truth is 40, a return rate of 0 and no
  note (as today; Q15 fixed negative "in" amounts only), and the stock
  received it reports (10.00) is that refund while the real, unpriced
  delivery's money is skipped.
- *Need his definition:* **#6** unanswered, the returns term and the return
  rate hold lines on keys the engine itself suggests are costs, charges or
  discounts - Online Retail II 2011-11: 18,157.88 of 47,740.08 on
  cost-suggested keys (Amazon fees), 847.65 charge, 474.85 discount; return
  orders 441, 396 without them (rate 0.1593 against 0.1430) - and the mark
  reaches product names only. **#10** A1 (a negative "in" line of a cost,
  adjustment or gift card stays outside revenue) against Q15's literal
  "negative = a customer return, in revenue"; A4 (R3 stays) against "every
  stock KPI not supported". **#7** Kaggle's unmeasurable lines differ by
  month (2024-11: 39, 2024-12: 33): of the 35 more counted lines behind B1's
  "customers bought more lines", about 6 are fewer unmeasurable lines (all
  lines +29) - B1 does not flip; the report is whole-file only.
- *The author's to correct (no definition needed), with revision 3:* **#3**
  stage 4's `products_at_stockout_risk` (contracts/forecast.py, CONTRACTS
  section 8) requires `days_to_stockout` and `suggested_reorder_units` and
  `prompts/strategy.md` asks for a reorder figure - under the cut it must
  read "not supported in v1" too, not `[]`. **#4** `no_money` loses the
  item: M's 7 zero-amount lines (4 in the compared months) would become a
  product member (member_count 3096 -> 3097, `non_product` pooled lines 1426
  -> 1419) - a pooled zero-amount line needs its own class, as `pooled_sale`.
  **#5** `suggested_class` must be exactly the Review candidates (a key that
  moves no money is not asked, so carries none; else 23595 "re-adjustment"
  would be marked in diagnosis.json). **#8** diagnosis.json needs the
  return-rate note too (its `return_rate` signal, read by the narration).
  **#9** the baselines need every stage 3 output (frame, calendar,
  not_testable; Kaggle's signals), an exact-equality rule, and an Online
  Retail II pin through stage 1's real path (execute_run). **#11**
  `undated_amount` mixes classes - dropped. **#12** gift-card words: discount
  words before them, and no bare "voucher" ("discount voucher", "promo
  voucher" suggested a gift card). **#13** an "in" line with a non-finite
  price reports infinite money (its money is unknown); a month whose finite
  lines sum past a float is older (8D). **#14** the receipt fill's excluded
  lines must be recoverable from `line_class` alone: every "in" line that is
  not a finite negative amount is `stock_in`, before the unmeasurable rules.
  **#15** the column mapping follows the `_source` rename. **#16** gift-card
  lines name no receipt (as costs); the confirmed-gift diff re-measured
  through the real classes (`non_product`'s `gift_card` row, the
  outside-revenue totals); `prompts/root_cause.md` and `strategy.md` read the
  note and the suggested classes; the brief's AI tier is the schema
  inference (the AI proposes what a column means, the user confirms).

**Questions for Thach after review 5** (the author's recommendation after
each; the report's Q25-Q28):

21. *"In" lines* (#1, #2, and A1). Q15's sign rule fabricates a return from
    a priced receipt correction; the canonical booking of a customer return
    (+ typed "in") stays outside revenue. The data cannot tell a customer's
    "in" line from a supplier's. Recommended: every "in" line outside
    revenue, as 2A has always read it, reported with its lines and money by
    sign; on a file with "in" lines, revenue and the return rate carry a
    note - "N lines are typed "in"; a customer return booked as "in" cannot
    be told from stock received, so returns count only the return lines
    among sales, and revenue may include returns booked as "in"" - unknown
    stays unknown, as decision 5; v2 maps type values. Or: Q15 as decided,
    with the same note. Neither demo file has an "in" line.
22. *Unconfirmed lines inside returns* (#6). Recommended: the identity's
    returns term and `return_rate_note` state the part on keys with an
    unconfirmed suggestion ("of which X, on N keys suggested as costs,
    charges or discounts - not confirmed"); no figure moves.
23. *R3* (A4). Recommended: R3 stays - it reads the sales pattern, never a
    stock figure, and says "verify on the shelf".
24. *Unmeasurable lines by month* (#7). Recommended: metrics.json reports them
    for the compared months as well as the whole file (the author's, 2E-t2);
    a trust check that hedges a lines-based cause when their count differs
    between the months goes to Phase 8 (B1 does not flip).
