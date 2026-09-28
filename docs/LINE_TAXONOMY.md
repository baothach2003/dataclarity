# Line taxonomy - design (session 2E-t), v1: the money ledger

**Status: APPROVED IN PRINCIPLE (Thach, 2026-09-28). Revision 3, with his
answers to review 5 and the standing rule (sections 0 and 8); revision 3b
folds in the sixth fresh-context review, and revision 3c its scoped second
cycle on the notes and the anchor (section 9) - no finding needed to stop the
run: the standing rule settles those of its shape (decisions made alone,
section 8). Nothing here is built.** The decision
record is `docs/adr/0008-line-taxonomy.md`. Written 2026-09-27 (fifth
overnight run) from Thach's brief in PROJECT_PLAN item 2E-t (a)-(e) and his
answer to Q3 of the fourth run; revised after each of five fresh-context
reviews and with his three sets of answers (sixth, seventh and eighth runs).
Every figure is measured on today's code (HEAD 2643f94; the code as at
99e9eb2) by the scripts in the scratchpad's `run8/2et/` - revision 2's in
`run7/2et/`, the earlier ones in `2et/` and `2et_rev/review4/`; the
implementation sessions re-measure on the built code.

## 0. The v1 scope (Thach, 2026-09-28)

**v1 is the MONEY ledger only.** The taxonomy decides what each line does to
revenue, orders, units, returns, customers and the product tables. It keeps
no stock ledger and reads no source signal the user maps:

- **Every stock KPI** - velocity, days to stockout, any low-stock figure,
  stage 4's products at stockout risk and its reorder figures - reads "not
  supported in v1", with that reason, on EVERY file, rather than a figure that
  can be wrong. This retires 2C's sign defect (a zero-amount -20 line added 20
  to the computed stock). The Dashboard's low-stock table (6F, 7C) is out of
  v1; the README says v1 analyses sales, not inventory.
- **No source-signal mappings**: transaction-type values and invoice prefixes
  are not mapped to return / restock / stock in / stock out in Review. The
  canonical `transaction_type` keeps the one reading it has always had (2A):
  a line typed "in" is outside revenue (section 2).
- **One no-money class per item**: without a stock ledger a zero-amount
  line's direction does not matter, so the five classes the fourth revision
  had (`free_item`, `stock_write_off`, `stock_found`, `stock_count`,
  `no_movement`) are one: `no_money` - counted, no money, present in the
  product dimension as today - with its pooled twin `pooled_no_money` (the
  item, not the direction: review 5 #4).
- The stock ledger, the signal mappings, the split of `no_money`, and the
  questions review 4 left on them (#2, #4, #5, #11, #12) are the v2 item in
  PROJECT_PLAN's Backlog.

**The standing rule** (Thach, 2026-09-28, permanent - CLAUDE.md 3.3a): when
the data cannot tell two meanings apart, v1 NEVER guesses. It keeps the
existing behaviour, reports the affected lines and money, and adds a visible
note wherever the affected figure is shown. Its instances in this design:

- a zero-amount line's stock direction (decision 5) - moot in v1, which keeps
  no stock ledger;
- lines typed "in" (Q25): a customer return booked as "in" cannot be told
  from stock received, nor a supplier's receipt correction from a customer's
  refund - every "in" line stays outside revenue, as 2A, its lines and money
  are reported by sign, and revenue and the return rate carry a note (every
  note of this section is shown as section 3 says: beside the figure, or
  once when always-on - present by construction rather than because of the
  file's data - Thach, 2026-09-29);
- a same-day credit (decision 1): a cancellation cannot be told from a
  same-day return - it stays a return, and the return rate carries a note;
- a line on a key the rules suggest is a cost, charge, discount, adjustment
  or gift card that the user has not confirmed (Q3, Q26): it keeps its
  rule-based class, and its lines and money are stated beside every figure
  they are in - revenue, gross sales, returns, the return rate, orders;
- a line at a negative price (an `allowance`): a refund, a coupon and a
  bad-debt write-off cannot be told apart - it stays an other deduction, and
  returns and the return rate say a refund among them is not in them;
- a price already reduced by a discount cannot be told from a list price -
  gross sales are at the price written, and the discounts term says so;
- a mapped `transaction_type` value other than "in" or "out" ("Return",
  "Cash"): v1 maps no type value (the scope cut), so what it means is not
  known - the line is read by its signs, as today, and the values are
  reported beside revenue and returns.

The notes are listed in section 3; each one is a decision the rule made, not
a new figure.

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
| 1 | `transaction_type` "in" is stock received, out of revenue; any other value a sale | `shared/transactions.line_numbers` (2A) | revenue scope | kept for EVERY "in" line (Q25, superseding Q15); its lines and money reported by sign; a note on revenue and the return rate. Kaggle maps its *Payment Method* as `transaction_type` (a separate item - decision 8); none of its values is "in" |
| 2 | sale = counted, qty > 0, amount > 0, not a discount or charge | `parse_transactions` (2E, 2E-c, 2E-l) | orders, units, gross sales, products | rule 7 of 4.2: the same lines. A gift voucher sold is a sale until the user confirms the gift-card class (Online Retail II: 77 lines, +1,756.17) |
| 3 | return line = counted, qty < 0, amount < 0 | same (2E-c2) | returns, return rate, the returns lens | rule 8: the same lines. All 19,493 such lines of Online Retail II sit on C (credit) invoices; same-day cancellations among them cannot be told apart (4.4) |
| 4 | deduction = counted and none of the above | same (2E-c, 2E-c2) | the returns lens's `deductions`, P4 | `allowance` (money, unconfirmed), `discount` (confirmed), `no_money` (none), and their pooled twins: the same lines, named apart in metrics.json's identity |
| 5 | the user's classes: charge, discount, pooled, cost, adjustment, "a product" | `shared/line_classes.py`, stage 1's `non_product_lines.py` (2E-d2, 2E-l) | revenue scope, orders, the product tables | the item question (2.1), plus `gift_card`; an unanswered candidate is recorded and carried downstream (Q17) |
| 6 | a line with neither SKU nor name is the gap | `shared/products.py` (2E-g) | never ranked; the lens's `unidentified` | the pooled item by rule, as today |
| 7 | stock on hand from the stock-in lines against every counted line | `metrics_products._velocity` (2C, 2E-g) | days to stockout | **removed**: "not supported in v1" on every file (section 0). The defect it retires: 100 received, 63 sold, 20 more removed read 57 days to stockout instead of 17 (`2et/ledger_sign.py`) |
| 8 | B2 is refused on any return line or negative-amount counted line | `hypothesis_evidence_lever.b2` (2E-c2) | the basket hypothesis | unchanged (Q21) |
| 9 | the first day nets per product and class key | `shared/first_purchase.py` (2E-f, 2E-d2) | new / resurrected customers | unchanged: it reads the same lines |
| 10 | a receipt is judged on its sale / return / counted / out-of-revenue lines | `shared/orders.py` (2E-e, 2E-e2, 2E-k) | the order basis, the customer fill | unchanged: it reads the same lines, the out-of-revenue ones from `line_class` alone |
| 11 | a line with no parseable quantity or price is counted nowhere | `parse_transactions` (`valid`) | every figure | `unmeasurable`, REPORTED with its reason, for the file and the compared months (decision 7, Q28): Kaggle's 1,213 lines - 604 with no quantity, 609 with no price, 9.6% of the file - left revenue silently |

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
  `cost` (A2).
- **The line** - what it does to money, read from the sign of its amount
  (quantity x unit price). A credit note is read by its lines' signs, as
  today: a C line of a product is a return or an allowance by its signs, a C
  line of postage a postage refund (still a `charge`, negative - Thach's Q21:
  other revenue, negative), a C line of a fee a fee reversal (still a
  `cost`).
- **The canonical `transaction_type`'s "in"** (2A; Thach's Q25, which
  supersedes his Q15): every line typed "in" is `stock_in` - outside revenue,
  whatever its sign or its item, as 2A has always read it. The sign cannot
  tell a supplier's receipt correction (-30 @ 4.00, "in") from a customer's
  refund, nor a customer return booked the canonical way (+2 @ 5, "in") from
  a delivery (review 5 #1, #2), so v1 does not guess (the standing rule):
  the "in" lines and their money are reported by sign, and on a file with
  "in" lines revenue and the return rate carry the note
  `returns_booked_as_in` (section 3). No Review question. The schema prompt
  drops "e.g. a purchase or a return" from its "in" (2E-t1).

### 2.1 The closed class list (brief a)

The accounting test for money: *tied to the sale* (revenue or
contra-revenue) or *tied to the cost of earning it* (an expense, outside
revenue). Every line of the file gets exactly one class. Online Retail II is
the whole file (1,067,371 lines); "classed" is Thach's classes (POST, DOT, C2
and 23444 charges, D discount, AMAZONFEE, CRUK, BANK CHARGES and S costs, B,
ADJUST and ADJUST2 adjustments, M pooled), "unanswered" none
(`run8/2et/proto3.json`).

| Class | Counted | Accounting | Online Retail II classed | unanswered | Kaggle |
|---|---|---|---|---|---|
| `sale` | yes | revenue: gross sales | 1,037,029 lines, +20,110,963.19 | 1,041,671, +20,972,968.14 | 11,362, +1,472,998.50 |
| `pooled_sale` | yes | revenue: gross sales, never a ranked product | 882, +341,104.90 (M) | - | - |
| `customer_return` | yes | contra-revenue: sales returns | 18,290, -726,633.05 | 19,493, -1,527,041.43 | - |
| `pooled_return` | yes | contra-revenue: sales returns, never ranked | 537, -423,886.17 (M) | - | - |
| `allowance` | yes | contra-revenue, UNCONFIRMED: a money line of a product that is neither a sale nor a return by its signs (a negative price: a refund, a coupon, a bad-debt write-off) | - | 5, -158,676.14 (B "Adjust bad debt") | - |
| `pooled_allowance` | yes | the same, of a pooled item | - | - | - |
| `discount` | yes | contra-revenue: a discount the user confirmed | 177, -13,484.54 (D) | - | - |
| `charge` | yes | other revenue (a negative one is a charge refunded) | 3,931, +449,559.47 | - | - |
| `no_money` | yes | no money: a product line with an amount of 0 (a free item, a write-off, a count, a quantity of 0) | 6,177 | 6,202 | - |
| `pooled_no_money` | yes | the same, of a pooled item | 7 (M) | - | - |
| `gift_card_sale` | **no** | a liability (deferred revenue), outside revenue, reported - only once the user confirms the item | (77 money lines, +1,756.17, and 18 of 0, if the 7 candidates are confirmed; 4 more zero-amount lines sit on `gift_0001_60` and `_90`, which move no money and are not asked) | - | - |
| `gift_card_redemption` | **no** | settles or reverses the liability, outside revenue, reported | (1 line, -69.56, if confirmed) | - | - |
| `cost` | **no** | expense, outside revenue, reported | 265, -310,325.44 | - | - |
| `adjustment` | **no** | outside revenue, reported (bad debt is an expense) | 76, -140,047.79 | - | - |
| `stock_in` | **no** | every line typed "in": outside revenue, reported with its lines and money by sign | - | - | - |
| `unclassified` | **no** | isolated, reported (4.3) | **none** | **none** | **none** |
| `unmeasurable` | **no** | no finite quantity, no finite price, or an amount too large to add: counted nowhere, reported with its reason | - | - | 1,213 (604 no quantity, 609 no price) |

The classes marked "yes" are counted; a counted line also needs a date to be
in a month (4.2). Unanswered, M is a product, so its 7 zero-amount lines are
`no_money` there, as today.

**What the code distinguishes today maps in without loss:** sale -> `sale`;
return line -> `customer_return`; deduction -> `allowance` (money, not
classed), `discount` (classed) or `no_money` (none); pooled and the gap ->
the pooled twins; `charge`, `cost`, `adjustment` -> the same; "in" ->
`stock_in`; invalid -> `unmeasurable`, or its own class when only the date
is missing (4.2).

`cancellation` is NOT in the list: 4.4.

## 3. The effects matrix (brief b) - the single source of truth

One table, in one module (`shared/line_effects.py`), read by stages 2 and 3.
Every money column sums the lines' amounts AS SIGNED; returns, discounts and
other deductions are REPORTED as what they took away - minus their signed sum
(returns = -(sum of return amounts)), so a positive discount line (a reversal)
reduces the discounts term - as the returns lens stores them today.
**The identity: net revenue = gross sales - returns - discounts - other
deductions (unconfirmed) + other revenue**, to float residue - judged
against the money the month's counted lines moved (`money_moved`), since a
charge and its reversal cancel inside one term (2E-t2 U8) - (Thach's Q16:
"other deductions (unconfirmed)" until confirmed; only lines the user
confirmed as discounts are "discounts").

| Class | Gross sales | Returns | Discounts | Other deductions (unconfirmed) | Other revenue | Net revenue | Customer money | Customer presence | Purchase | First-day netting | Units | Return rate | Product tables (stage 2) | Product dimension (stage 3) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `sale` | + | | | | | + | + | yes | yes | yes | + qty | denominator | yes | its product |
| `pooled_sale` | + | | | | | + | + | yes | yes | yes | + qty | denominator | no | the gap bucket |
| `customer_return` | | + | | | | + | + | yes | no | yes | qty (negative) | numerator | yes | its product |
| `pooled_return` | | + | | | | + | + | yes | no | yes | qty (negative) | numerator | no | the gap bucket |
| `allowance` | | | | + | | + | + | yes | no | no | no | no | yes (its product's revenue) | its product |
| `pooled_allowance` | | | | + | | + | + | yes | no | no | no | no | no | the gap bucket |
| `discount` | | | + | | | + | + | yes | no | no | no | no | no | "(not a product)" |
| `charge` | | | | | + | + | + | yes | no | no | no | no | no | "(not a product)" |
| `no_money` | | | | | | none | none | yes | no | no | no | no | present, no money | its product (present) |
| `pooled_no_money` | | | | | | none | none | yes | no | no | no | no | no | the gap bucket (present) |
| `gift_card_sale`, `gift_card_redemption`, `cost`, `adjustment` | | | | | | outside - reported | none | no | no | no | no | no | no | no |
| `stock_in` | | | | | | outside - reported by sign, with a note | none | no | no | no | no | no | no | no |
| `unclassified` | | | | | | outside - isolated, reported | none | no | no | no | no | no | no | no |
| `unmeasurable` | | | | | | counted nowhere - reported (lines, reason) | none | no | no | no | no | no | no | no |

- **The customer columns reproduce today's rules**: *customer money* (the
  bridge, RFM monetary) = every line in net revenue with a customer;
  *customer presence* (active customers, the RFM population - 3C: a
  returns-only customer is active) = every counted line with a customer
  (2011-11 classed: 1,710 active, 1,662 buyers - `run7/2et/m8.out`);
  *purchase* (orders, frequency, recency) = the sale lines; the first-day
  netting (2E-f) reads sale and return lines of products and pooled items.
  The lines outside revenue - `stock_in`, `cost`, `adjustment` and the gift
  cards - name no receipt's customer (2E-e2 F4, 2E-d2 F9), read from
  `line_class` alone (review 5 #14, #16).
- **The two product columns** (Thach's Q23): stage 2's product TABLES rank
  products only; stage 3's product DIMENSION keeps every counted line so it
  sums to the change - charges and discounts in its "(not a product)" bucket,
  the pooled twins with the gap, as today.
- **The notes** (the standing rule; E1, E5, E10): metrics.json's
  `core.notes` is one list, and stage 3's output carries the same list (its
  narration and stage 4's prompts read it). A note is `{code, figures, text,
  measures}`: `figures` names what it qualifies, from `revenue`,
  `gross_sales`, `returns`, `discounts`, `other_deductions`, `return_rate`,
  `orders`, `aov`, `units`, `customers`, `products` and `diagnosis` (the
  headline and the causes, which read the whole history window); `text` is
  one fixed sentence per code, below; each measure is `{name, scope, lines,
  amount, orders, keys}` for the scopes `file` (every line), `current` and
  `previous` (the dated lines of the month) - `amount` the SIGNED sum of the
  lines' amounts (null where not finite), `orders` the distinct orders among
  the lines or as defined below, `keys` where defined, the rest null. The
  `file` scope is every line the measure is about: a note over counted
  lines counts the dated ones (an undated line is in no figure, and in
  `undated_lines`); the reports of lines outside revenue and of stock
  received count every such line, dated or not.
  Wherever stage 5 or the frontend shows a figure, it shows the notes that
  name it, with their measures - except an ALWAYS-ON note, shown ONCE, in a
  "How to read these figures" section (Thach, 2026-09-29, adjustment 1: a
  note beside every figure trains readers to ignore them all). A note is
  always-on when it is present by construction rather than because of this
  file's data (Thach's words: "S3, and any note present on every file by
  construction, such as U5 at zero"): `discounts_in_prices`, and
  `same_day_cancellations` when every one of its measures, in every scope,
  counts 0 lines (a file with no customer column
  counts its returns in `returns_unchecked`: that note is the file's own,
  and stands beside the figures it names). A consumer renders a note by its
  code, figures and measures; its sentence is the default rendering
  (adjustment 2). A note is present when its file-scope measure has lines,
  except two: `discounts_in_prices` always, and `same_day_cancellations` on
  every file with DATED return lines, its measures zero where no return
  matches (decision 1: the note qualifies the return rate - beside it, or
  once when always-on - 2E-t2 U5; a file whose every return is undated has
  no return rate to qualify - 2E-t2 review 3 #6).
  Its codes:
  - `same_day_cancellations` (gross_sales, returns, return_rate, orders,
    aov, customers, products, diagnosis; decision 1, widened by the
    standing rule - S2, U7): "Returns and the return rate include same-day
    cancellations, which the data cannot separate: the measures count the
    return lines rung the day their customer bought the same product, those
    sale lines, and the return lines no match can check: with no named
    customer, or on a pooled code." Present on every file with a dated
    return line (decision 1). Measures `returns` - `customer_return` lines
    (products only: a pooled code is many items, not the same product -
    E11) whose named customer has a `sale` line of the same product on the
    same calendar day, the product read as the first-day netting reads it
    (`shared/products.netting_keys`: SKU, else name, a name-only line on
    its one SKU - U16); `sales` - those sale lines; `returns_unchecked` -
    the dated return lines no match can reach, with no named customer or
    `pooled_return` (U14: with no customer column every return is one,
    never "no cancellation"); `orders` the orders among each.
  - `returns_booked_as_in` (revenue, returns, return_rate, aov, units,
    customers, products, diagnosis; Q25, S6, U7): "Lines typed "in" are
    outside revenue as stock received. A customer return booked as "in" cannot be told from stock
    received, so returns, the return rate and the customer figures leave it
    out, and revenue is not reduced by it." Measures `positive`, `negative`,
    `zero` (by the sign of a finite amount) and `unknown` (no finite
    amount) over the `stock_in` lines.
  - `unconfirmed_suggestions` (revenue, gross_sales, returns,
    other_deductions, return_rate, orders, aov, units, customers, products,
    diagnosis; Q3, Q26, S1): "Some keys the file suggests are costs, charges,
    discounts, adjustments or gift cards were not confirmed in Review: their
    lines stay what their signs say, in every figure. The measures count
    them, their returns, and the orders holding only such lines." Measures
    (`keys` the distinct products they are on, read as the same-day match
    reads them - U16) `lines` - the counted lines on unconfirmed candidate keys suggested cost,
    charge, discount, adjustment or gift card (E2: not `pooled`, whose lines
    stay sales and returns once confirmed), with `keys` and `orders` = the
    orders holding a sale line and only such sale lines; `returns` - their
    return lines, `orders` = the orders holding a return line and only such
    return lines (Q26's share for the return rate). The identity's returns
    term carries minus the `returns` amount as `returns_on_suggested_keys`.
  - `unconfirmed_deductions` (revenue, other_deductions, returns,
    return_rate, aov, customers, products, diagnosis; S4, U7): "Lines at a negative price are other
    deductions: refunds, coupons and write-offs the data cannot tell apart. A
    refund among them is not in returns or the return rate, and a write-off
    among them keeps revenue lower than it may be." Measure `lines` - the
    counted `allowance` and `pooled_allowance` lines.
  - `discounts_in_prices` (gross_sales, discounts; every file; S3):
    "Discounts count only lines classed as discounts; a discount already
    taken off a line's price is not visible, and that line's gross sales are
    at the reduced price." No measure.
  - `other_transaction_types` (revenue, gross_sales, returns,
    other_deductions, return_rate, orders, aov, units, customers, products,
    diagnosis - every figure a counted line is in; S5, U7): "Lines carry
    transaction types other than in or out; v1 reads only "in", so these
    are read by their signs as sales or returns. The measures count them by
    value, the rarest values together." Over COUNTED lines, per value as
    "in" is read (`identifier_text`, case-folded): the five values with the
    most lines, each named by its commonest spelling cut to 40 characters,
    then one `(other values)` measure whose `keys` counts its values (U15:
    the names are the file's own text and reach the AI, so they are
    bounded); a cell with nothing visible is blank, read as "out" (2E-i),
    never a value.

  No note changes a figure. Every money figure and measure writes a zero as
  0.0, never -0.0 (review 6b #12). A note's sentence and figures are fixed
  per code in `contracts/lines.py`, which refuses any other: they are part
  of the contract, so changing one is a major bump of metrics.json and
  diagnosis.json (U12).
- **Stock**: no column in v1. `products.velocity` is null on every file with
  the reason that stock figures are not supported in v1, and stage 4's
  `products_at_stockout_risk` likewise (review 5 #3).

Every figure outside revenue (gift cards, costs, adjustments, stock
received, unclassified, unmeasurable) is reported in metrics.json with its
lines and money, never dropped silently; `stock_in` by sign (lines and money
of its positive and its negative amounts), with its lines of no finite amount
counted apart (their money is unknown - review 5 #13).

## 4. Classification once, in stage 1 (brief c)

Stage 1 writes three columns into `cleaned.csv`:

- `line_class` - the class (2.1);
- `class_source` - `user` when the item answer decided it, `rule` otherwise
  (the brief's `class_source`);
- `suggested_class` - the suggestion pending on the line's key, one of
  the line-class ANSWERS (`charge`, `discount`, `pooled`, `cost`,
  `adjustment`, `gift_card` - not the classes of 2.1; review 6b #2): the
  line-class candidates (4.1) the user did not answer, as `execute_run`
  finds them on the file it classifies (the cleaned frame and the plan's
  mapping), by the function the schema step uses on the raw file - a key
  that moves no money is no candidate, so carries none (review 5 #5). A line
  whose item is answered - its own key, or for a name-only line its one SKU
  - carries none; an unanswered name-only line without a candidate of its
  own takes its one SKU's (review 6b #9).
  Blank is written as a missing cell, never as empty text (review 6 #2: an
  empty text would raise the `text_reads_as_missing` warning on every file).
  After a remap Review lists candidates read from the profile's top values
  (the frontend, money not measured), so its list can differ from these; a
  key the rules suggest that Review did not ask stays unconfirmed, and is
  marked so (E6).

A source column named exactly like one of them (as written), and not
dropped by the plan, is kept, renamed `<name>_source`, then
`<name>_source_2`, `_3`... while any source column has that name; the report's
`column_mapping` follows the rename (review 5 #15), cleaning_report.json
records it as a warning (`reserved_column_renamed`), and Review says so
(Q24). This amends CONTRACTS
section 5's "cleaned.csv keeps the source column names" for these three
names only. The rename happens before the plan runs, so the run's flags on
that column, `changes[].column` and the details name it as cleaned.csv holds
it; `plan_final.json` keeps the plan as submitted (E8, as corrected by 2E-t1's
review cycle 2). `columns_out` counts the three new columns, as it counts every
column a run adds. Stages 2 and 3 read
`line_class` and `suggested_class` only, through `shared/transactions.py`,
which refuses a value outside the closed list.

### 4.1 Evidence

| Question | Unit | 1. the user | 2. the rule | Suggestions (never applied alone) |
|---|---|---|---|---|
| the item | per key (SKU, else name; a name-only line inherits its one SKU's answer, as today) | the answer in Review | neither SKU nor name -> `pooled`; otherwise `product` | today's class words and the gift-card words ("gift card", "gift voucher", "gift certificate", "gift_"), at the start or end of the SKU or the commonest name, in the order adjustment, pooled, discount, gift card, charge, cost - so "discount voucher" is a discount, and no bare "voucher" (review 5 #12) |
| the line | per line | - | the amount's sign; "in" as section 2 | - |

The brief's third tier - "AI suggestions the user confirms" - is the schema
inference: the AI proposes what each column means and the user confirms the
mapping in Review (ADR-0002); the AI never classes a line (review 5 #16).

On Online Retail II the gift-card words match 9 keys, `gift_0001_10` to
`gift_0001_90`, all vouchers and no other key; 7 move money and become
candidates beside today's 13 (60 and 90 move none); Kaggle has no candidate
(`run8/2et/proto3.json`).

**A suggestion never applies itself** (2E-d2; Thach's Q3): a key the words
suggest is a charge but nobody confirmed keeps its rule-based class (`sale`),
so an unanswered file loses no revenue - and its suggestion travels with it.

### 4.2 From the answers to the class - a total table

In order, first match wins:

1. typed "in" -> `stock_in` (Q25; before every other rule, so the receipt
   fill's out-of-revenue lines are read from `line_class` alone - review 5
   #14).
2. no finite quantity -> `unmeasurable` ("no quantity").
3. no finite price -> `unmeasurable` ("no price").
4. quantity x price not finite -> `unmeasurable` ("amount too large to add";
   today such a line is counted, and its month's revenue is written as null
   in a required field - measured).
5. the user's item: `charge`, `discount`, `cost`, `adjustment` -> that
   class, at any amount and sign (a zero-amount postage line stays a
   `charge` with no money); `gift_card` -> `gift_card_sale` for an amount
   >= 0, `gift_card_redemption` below 0.
6. a product or pooled item (P) with an amount of 0 -> `no_money`
   (`pooled_no_money`).
7. P, quantity > 0 and amount > 0 -> `sale` (`pooled_sale`).
8. P, quantity < 0 and amount < 0 -> `customer_return` (`pooled_return`).
9. P otherwise (a negative price) -> `allowance` (`pooled_allowance`).

**The date does not decide the class** (A3) - except through today's
name-only vote, which reads the dated sale lines as it does today (E7:
reading undated ones too would move a name-only line's class on a file with
undated lines - review 6 #13). An undated line keeps its class and is in no
month: it is counted in no figure and reported in
`undated_lines` - except an `unmeasurable` line, reported once, as
unmeasurable (Q24). Every combination of the inputs (typed "in", quantity
finite or not and its sign, price finite, amount finite and its sign, the
item answer, SKU or name present) falls in exactly one rule; the test covers
each.

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
v1** - a same-day credit stays a return, and the return rate carries the
`same_day_cancellations` note (section 3) - an instance of the standing rule.

### 4.5 The suggestions downstream (Thach's Q17)

Stages 2 and 3 read `suggested_class` beside `line_class`: a product's
suggestion is its key's - the one its OWN key's lines carry; a name-only
line resolved to a SKU keeps its own name key's suggestion, which marks no
product (its lines are in the `unconfirmed_suggestions` note), so the mark
never depends on which line came first (2E-t2 U6). Each contract that names products carries ONE map,
`suggested_classes`: every product it names - by its label, which is unique
(`shared/products.py`) - whose key carries an unconfirmed suggestion, with
that class. metrics.json names products in `top_products` and
`biggest_decliners`; diagnosis.json in the product dimension's members, new
and removed members, R1's top member and R3's products. Stage 5 and the
frontend print such a product as "<name> (suggested: <class>, not
confirmed)"; a headline that names a product (none does today - rules 5-7
name causes and lenses) does the same. `prompts/root_cause.md` and
`prompts/strategy.md` receive `suggested_classes` and the notes, with the
rule that a product marked suggested is named with its mark and is never the
subject of a product recommendation (review 6 #6: DOTCOM POSTAGE, unanswered,
is 2011-11's top product). Measured on the demo outputs, with
the suggestions exactly the candidates (`run7/2et/m4b.json`, review 5 #5):
unanswered, `{"DOTCOM POSTAGE": "charge"}` in metrics.json (the top product
of 2011-11, 36,905.40) and in diagnosis.json, which also names
`Dotcomgiftshop Gift Voucher £20.00` (a removed member; `gift_0001_20` moves
money) as `gift_card`; classed, only that voucher, in diagnosis.json; Kaggle,
none. The key 23595 ("re-adjustment", a removed member) moves no money, so
it is no candidate and carries no suggestion.

## 5. Guarantees (brief d)

- **Exactly one class per line**, tested on both demo files and on the
  sweeps: `line_class` has no blank and no value outside the list; the
  effects matrix has a row for every class (a test fails when a class is
  added without its effects); the rules of 4.2 are tested over every
  combination of their inputs.
- **The same lines**: on a file with no amount too large to add and no
  confirmed gift card, every set of lines today's readers use - counted,
  sale, returned, charge, deduction, left out, units, and the lines the
  receipt fill may not read - is the same set under v1. Measured by a
  prototype of 4.2 beside today's `parse_transactions`: identical, line by
  line, on Kaggle and on Online Retail II in both states, the fill's lines
  read from `line_class` alone (`run8/2et/proto3.py`, `proto3.json`); 2E-t2
  keeps that comparison as a test. `valid` (a date, a finite quantity and
  price) stays a reading of the raw columns.
- **`unclassified` is isolated**, never assumed a sale: outside every
  revenue figure, its lines, money and share of the money moved in
  metrics.json and in Review. **`unmeasurable`** is counted nowhere and
  reported with its lines per reason, for the whole file and for each
  compared month by its date where the date reads (Q28 - Kaggle 2024-11: 39
  lines, 15 no quantity and 24 no price; 2024-12: 33, 19 and 14); its money
  is unknown - that is why it is unmeasurable - and is never derived from
  another column (Kaggle's unmapped *Total Spent* holds 79,072.50 on its 609
  unpriced lines; the canonical schema has no line-total field). A trust
  check that hedges a lines-based cause when the months' unmeasurable
  counts differ is Phase 8 (Q28: Kaggle's B1 does not flip - all lines +29,
  counted +35).
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
| 2A: transaction type "in" is out of revenue | rule 1 (Q25) | nothing in any figure; the "in" lines are reported with their lines and money by sign, and the `returns_booked_as_in` note qualifies revenue and the return rate |
| 2C / 2E-g: the stock balance and velocity | none in v1 | `products.velocity` null on every file with the reason "not supported in v1"; the derivation from stock-in lines is removed, and its sign defect with it |
| 4A-4C (not built): stage 4's products at stockout risk | none in v1 | `contracts/forecast.py`'s `products_at_stockout_risk` null with the same reason (no forecast.json has been written, so in place - CONTRACTS section 10); `prompts/strategy.md` asks for no reorder figure (review 5 #3) |
| 2E / 2E-c: a sale is qty > 0 and amount > 0 | rule 7 | nothing |
| 2E-c: the deduction bucket | `allowance`, `discount`, `no_money` and the pooled twins | nothing in money; metrics.json's identity names discounts and other deductions apart |
| 2E-c2: a return line is qty < 0 and amount < 0 | rule 8 | nothing |
| 2E-c2: B2 refuses on return lines and negative-amount counted lines | kept exactly (Q21) | nothing; relaxing it for confirmed discounts is Phase 8 |
| 2E-c2: the return rate | the same figure | its notes (`same_day_cancellations`; `returns_booked_as_in`, `unconfirmed_suggestions`, `unconfirmed_deductions` and `other_transaction_types` where they apply) |
| 2E-d2 / 2E-l: charge, discount, pooled, cost, adjustment answers | the item question, plus `gift_card` | a confirmed gift card leaves revenue; `non_product` gains a `gift_card` row then |
| 2E-g: the identity gap | the pooled item by rule | nothing (`unidentified` stays) |
| 2E-h: undated lines | the class is decided without the date | `undated_lines` no longer counts a line that is unmeasurable (reported once, there) |
| CONTRACTS section 5: cleaned.csv keeps the source column names | kept, except a source column named `line_class`, `class_source` or `suggested_class`, renamed `<name>_source` (Q24) | `column_mapping`, the run's flags on it and `changes[].column` follow the rename |
| 3C doubt-review C2: a non-finite quantity or price is invalid | rules 2-4 | a finite quantity and price whose product overflows is `unmeasurable` (today it is counted, and its month's revenue is written as null in a required field) |
| 2E-n: the products' share on their sale lines | on the `sale` class | nothing |

**Contract bumps.** `cleaned.csv` gains three columns. The stage 1
contracts that carry the line-class enum (it gains `gift_card`: closed
enums, so a major - CONTRACTS section 10: schema_inference.json,
plan_*.json) go to 4.0, and `cleaning_report.json` with them (its readers
need the new columns); readers refuse the earlier ones as today ("re-upload
the file"), and the user answers again in Review. `metrics.json` goes to
16.0 and `diagnosis.json` to 17.0 (`undated_lines`' meaning, the velocity
reason, the additions below).

**THE REGRESSION ANCHOR** (Thach, 2026-09-28): the implementation sessions
2E-t1..t3 re-run the demo files through the built code, and every
difference from the pinned baselines must be one listed here; a difference
not listed stops the run. "Identical" means equal as serialised JSON - no
tolerance (review 5 #9).

*The pinned baselines* - today's code, `NOW` 2026-09-26, each through stage
1's real path: raw.csv + a plan -> `execute_run` (no AI call) ->
`analyze_run` -> every stage 3 piece (frame, trust, calendar, signals,
tree, localization, hypotheses, the catalog's not_testable, the headline)
(`run8/2et/pins/pin_*.json`, `pin3_summary.json` with their hashes):

- *Online Retail II*, the whole file (current month 2011-11), every column
  `flag_only`, mapped Invoice / StockCode / Description / Quantity /
  InvoiceDate / Price / Customer ID (Country ignored), in two states:
  classed and unanswered. Headlines: classed "Revenue went from 1,087,768.59
  to 1,479,884.13 (+392,115.54). The change is consistent with seasonality
  (...): 86% of the change."; unanswered "from 1,070,704.67 to 1,461,756.25
  (+391,051.58) ... 99% of the change."
- *Kaggle*, as Thach's Q22 asked: the stored run's approved plan (every
  column `flag_only`, its mapping) re-executed - a cleaned.csv
  byte-identical to the stored one. Current month 2024-12; headline "Revenue
  went from 41,367.50 to 46,292.50 (+4,925.00). The best-supported
  explanation: customers bought more lines (lever lens, 96% of the change)."
  The plan is re-executed as stored, its `schema_version` rewritten to the
  reader's (1.0 then; 4.0 once the stage 1 majors move) - its content
  unchanged. Decision 8's re-run of the schema inference is a separate item.
- Through the real path, metrics.json and every piece revision 2 pinned in
  memory are identical (`pin3_summary.json`).

*The differences allowed, on every demo run:*

1. **Versions**: the stage 1 contracts 4.0, metrics.json 16.0,
   diagnosis.json 17.0.
2. **`products.velocity_reason`**: today "the file has no stock-in lines
   (transaction type "in"), so stock on hand cannot be derived..." on all
   three runs; v1's "not supported in v1" reason. `velocity` stays null.
3. **Additions** (new fields, nothing removed): cleaned.csv's three columns,
   and so cleaning_report.json's `columns_out` 11 -> 14 (Kaggle) and 8 -> 11
   (Online Retail II); metrics.json's identity terms for the compared months
   (with `returns_on_suggested_keys`), the outside-revenue totals for the
   file and the compared months (with `stock_in` by sign), the `unclassified`
   report (0 lines, 0.0, a share of 0.0 on all three runs), the unmeasurable
   report (file and compared months), `notes`, `suggested_classes` - and
   `money_moved` in each month's identity (U8), outside revenue's `sign`
   (U9); the same
   `notes` and diagnosis.json's `suggested_classes` in stage 3's output. No
   new cleaning warning.
4. **Stage 1's line-class candidates** on Online Retail II gain the 7
   gift-voucher keys (`gift_0001_10`, `_20`, `_30`, `_40`, `_50`, `_70`,
   `_80`), suggested `gift_card`, among today's 13 (ordered by lines, as
   today); on Kaggle none, as today. The list, by today's function with the
   gift words (`run8/2et1/measure/measure_t1.json`): POST, DOT, M, C2, D, S,
   BANK CHARGES, 23444, ADJUST, AMAZONFEE, gift_0001_20, gift_0001_30, CRUK,
   gift_0001_10, gift_0001_50, gift_0001_40, B, gift_0001_80, ADJUST2,
   gift_0001_70 (the pins' plans are manual, so they hold no
   schema_inference.json; review 6b #3).

*Their values on the demo runs* (measured, `run8/2et/`):

- *Online Retail II classed*: identity 2011-11 1,460,682.95 / 28,259.70 /
  474.85 / 0 / 47,935.73 = 1,479,884.13; 2011-10 1,128,115.16 / 66,602.40 /
  56.08 / 0 / 26,311.91 = 1,087,768.59 (money moved 1,539,048.53 and
  1,222,063.91); `returns_on_suggested_keys` 0.0 in both months (the one return on an unconfirmed key, `gift_0001_80`'s
  -69.56, is in 2010-01). Outside revenue: the file cost 265 lines,
  -310,325.44 and adjustment 76, -140,047.79; 2011-11 cost 13, -18,127.88;
  2011-10 cost 18, -17,063.92; no stock_in. Unmeasurable 0; undated 0.
  `suggested_classes`: metrics.json none, diagnosis.json `Dotcomgiftshop
  Gift Voucher £20.00` gift_card. `non_product` unchanged. Notes
  (`run8/2et/notes5.json`; measures as lines / amount / orders):
  `same_day_cancellations` - returns: the file 2,630 / -416,673.77 / 1,108,
  2011-11 162 / -7,905.67 / 69, 2011-10 166 / -25,970.12 / 46; sales: the
  file 3,028 / +515,973.87 / 1,174, 2011-11 202 / +12,734.24 / 72, 2011-10
  198 / +30,873.44 / 53; returns no match can check (U14, measured at
  2E-t2 - 353 with no named customer and M's 537 pooled returns): the file
  890 / -430,822.14 / 617, 2011-11 28 / -4,808.72 / 18, 2011-10 60 /
  -22,939.20 / 37. `unconfirmed_suggestions` (the 7 gift-voucher
  keys) - lines: the file 96 / +1,686.61 / 0 orders / 7 keys, 2011-11 0,
  2011-10 1 / +16.67 / 0 / 1 key; returns: the file 1 / -69.56 / 1, the
  months 0. `discounts_in_prices`.
- *Online Retail II unanswered*: identity 2011-11 1,509,496.33 / 47,740.08 /
  0 / 0 / 0 = 1,461,756.25, `returns_on_suggested_keys` 19,480.38; 2011-10
  1,154,979.30 / 84,274.63 / 0 / 0 / 0 = 1,070,704.67,
  `returns_on_suggested_keys` 17,672.23 (money moved 1,557,236.41 and
  1,239,253.93; the 5 B lines, the file's only
  other deductions, fall in neither month). Nothing outside revenue;
  unmeasurable 0; undated 0. `suggested_classes`: metrics.json `DOTCOM
  POSTAGE` charge; diagnosis.json that and the voucher. `non_product` empty,
  as today. Notes: `same_day_cancellations` (M unanswered is a product, so
  its lines count) - returns: the file 2,813 / -551,654.16 / 1,270, 2011-11
  177 / -9,473.48 / 82, 2011-10 179 / -41,958.84 / 55; sales: the file
  3,210 / +638,534.57 / 1,335, 2011-11 222 / +15,262.51 / 88, 2011-10 213 /
  +50,060.59 / 64; returns no match can check (U14; no pooled code
  unanswered): the file 749 / -431,904.64 / 390, 2011-11 23 / -18,330.44 /
  13, 2011-10 62 / -19,559.43 / 28. `unconfirmed_suggestions` - lines: the file 4,545 /
  -12,611.69 / 241 orders / 19 keys, 2011-11 308 / +29,333.00 / 10 / 9,
  2011-10 232 / +9,208.58 / 20 / 10; returns: the file 667 / -376,591.77 /
  439, 2011-11 45 / -19,480.38 / 34, 2011-10 37 / -17,672.23 / 21.
  `unconfirmed_deductions` - the file 5 / -158,676.14, the months 0.
  `discounts_in_prices`.
- *Kaggle*: identity 2024-12 46,292.50 and 2024-11 41,367.50, all gross
  sales; unmeasurable 1,213 in the file (604 no quantity, 609 no price),
  2024-12 33 (19, 14), 2024-11 39 (15, 24), their money unknown; undated 0.
  Notes: `other_transaction_types` - its *Payment Method*, mapped as
  `transaction_type` (decision 8's item), over counted lines: the file Cash
  3,917 / +513,676.00, Credit Card 3,729 / +481,135.00, Digital Wallet 3,716 /
  +478,187.50; 2024-12 118 / +15,916.50, 111 / +14,575.50, 114 / +15,800.50;
  2024-11 99 / +13,492.00, 105 / +13,706.50, 104 / +14,169.00 - and
  `discounts_in_prices` (112 of 2024-12's 343 counted lines have *Discount
  Applied* = True, an unmapped column - review 6 #5). No return line, so no
  `same_day_cancellations`; no suggestion; nothing outside revenue.

Every other leaf of the stage 1 contracts, cleaned.csv, metrics.json and
stage 3's pieces is identical, the three headlines byte-identical: the
counted lines, and every set built on them, are today's (section 5).
Measured at 2E-t1 (`run8/2et1/measure/measure_t1.json`): through the built
stage 1, the three runs differ from the pins in exactly `columns_out`, the
stage 1 `schema_version` and metrics.json's, cleaned.csv's source columns
byte for byte identical, and the classes are section 2.1's.

*A documented class change, NOT the demo state*: if Thach confirms the 7
gift-voucher candidates as `gift_card` (classed), their lines leave revenue
in 24 of the file's 25 months (all but 2011-11): 2009-12 by -217.37, 2010-01
by +1.48 (a -69.56 refund and 68.08 of vouchers), ... 2011-10 by -16.67,
2011-12 by -8.33 (the month-by-month list: `run8/2et/pins/gift3.json`).
Measured through the classes, with the keys answered `cost` on today's code
(E4: a cost is left out exactly as a gift card will be), 113 leaves of the
2011-11 outputs move: metrics.core 31 (the 24 months, `revenue_previous`,
`aov_previous`, `revenue_change_pct`, and the 4 of the cost row that v1
writes as its own `gift_card` row), stage 3 82 (hypotheses 24, localization
20, signals 19, the tree 16, the calendar 2, the headline 1); no verdict
changes. The headline reads "from 1,087,751.92 to 1,479,884.13
(+392,132.21)", still rule 5, seasonality, 86%. Under v1 the same change also
moves what only v1 writes (review 6b #10): the 2011-10 identity's gross
sales (1,128,115.16 -> 1,128,098.49) and its outside-revenue totals (a
`gift_card_sale` line, +16.67); `non_product` gains a `gift_card` row (6
leaves) instead of the cost row's 4; the classed `unconfirmed_suggestions`
note and diagnosis.json's voucher in `suggested_classes` go; cleaned.csv's
three columns change on the 96 gift lines of the 7 keys; the cleaning
report's `confirmations` gain 7 answers.

## 7. Implementation split (Thach expects 2-3 sessions)

1. **2E-t1 - the classifier and the stage 1 contracts.**
   `stages/ingest/line_taxonomy.py` (the rules of 4.2, the item answers and
   their inheritance, the suggestions from the candidates), the gift-card
   words (stage 1 and the frontend's mirror), `gift_card` in the line-class
   enum, the three `cleaned.csv` columns, the reserved-name rename with the
   mapping, the stage 1 majors, the schema prompt's "in", the combination
   test, the "exactly one class" test, the demo measurement of the classes
   against section 2.1.
2. **2E-t2 - stages 2 and 3 read the class.** `shared/line_effects.py` (the
   matrix), `parse_transactions` reading `line_class` and `suggested_class`,
   the identity with `returns_on_suggested_keys`, the outside-revenue totals
   (`stock_in` by sign), `unclassified` and `unmeasurable` (file and
   compared months) in metrics.json, the six `notes` (metrics.json and stage
   3's output; `prompts/root_cause.md` and `strategy.md` read them and
   `suggested_classes`), `suggested_classes`, velocity and
   stage 4's stockout risk "not supported in v1" (the stock derivation
   removed; `prompts/strategy.md`), the equivalence test of section 5, every
   earlier test retargeted by the migration table, the demo files measured
   against the anchor.
3. **2E-t3 - Review.** The `gift_card` answer and the gift-card candidates,
   the identity line for the whole file (stage 1 computes it for the answers
   as they stand), the notes, the unclassified and unmeasurable counts, the
   reserved-name notice (frontend, by `docs/FIGMA_DESIGN_NOTES.md`).
   **Built (2E-t3):** stage 1's `line_summary` (`POST /line-summary`) on
   the lines execute would write (`clean_frame`, read back as cleaned.csv's
   text), with metrics.json's own functions (`shared/line_report.py`, the
   scope `file`); asked when Review opens and again on the user's request,
   marked "before your latest changes" after an edit. On the three demo
   runs it equals metrics.json's file-scope blocks, and its net revenue the
   sum of `revenue_by_month`.

The Online Retail II demo build follows 2E-t3. **Not in this split**
(decision 8): Kaggle's payment method mapped as `transaction_type` - stage
1's schema inference is re-run on Kaggle when the demo is rebuilt.

## 8. Decisions (Thach, 2026-09-28)

After the fifth run (the fourth revision's eight questions):

1. **Cancellations**: out of v1; a same-day credit stays a return; the return
   rate carries a note wherever it is shown.
2. **Refusals**: none in v1. `unclassified` stays the tested, empty class.
3. **Returns to stock**: moot in v1 (no stock ledger; the v2 item).
4. **Gift cards**: outside revenue and not counted once the user confirms;
   `gift_card_redemption` kept.
5. **Zero-amount direction**: no default - moot in v1 (the v2 item); the
   first instance of the standing rule.
6. **The stock ledger fix** - superseded by the v1 scope cut.
7. **Reporting unmeasurable lines**: in 2E-t2.
8. **Kaggle's payment method as `transaction_type`**: a separate item.

After the sixth run (review 4's questions; the design's 9-20 are the
report's Q13-Q24): **the v1 scope cut** (section 0; questions 9, 10, 14,
15, 16 moot, the v2 item's); **Q15** (11) - SUPERSEDED by Q25 below;
**Q16** (12) "other deductions (unconfirmed)"; **Q17** (13) the suggested
class downstream (4.5); **Q21** (17) B2 unchanged, a negative charge is
other revenue, negative; **Q22** (18) Kaggle's baseline pinned; **Q23** (19)
two product columns; **Q24** (20) unmeasurable lines reported, their money
never derived, reported once when also undated, the `_source` rename said in
Review.

After the seventh run (review 5's questions; the design's 21-24 are the
report's Q25-Q28):

- **Q25** (21): every line typed "in" stays outside revenue, as 2A; its lines
  and money are reported by sign; on a file with "in" lines revenue and the
  return rate carry a note. **It supersedes Q15** - the sign cannot tell a
  supplier's receipt correction from a customer's return (review 5).
- **Q26** (22): the identity and the return-rate note state the share of
  returns on keys with an unconfirmed suggestion; no figure changes.
- **Q27** (23): R3 stays (A4).
- **Q28** (24): unmeasurable lines per compared month; the trust check to
  Phase 8.
- **A1-A6** accepted (A1 - "in" lines by their item - is moot under Q25; A2
  `cost` keeps its name; A3 the date does not decide the class; A4 R3 stays;
  A5 the returns lens keeps its four terms, `deductions` = discounts + other
  deductions, and P4 already reads "Discounts and other deductions"; A6
  `no_money`). Review 5's eleven author's fixes are in this revision.
- **The standing rule** (section 0; CLAUDE.md 3.3a).

**Taken by the author in revision 3, for Thach to see** (none changes a demo
figure): the notes are one list in both contracts, each with its code, the
figures it qualifies, its text, lines and money (E1); Q26's share leaves out
keys suggested `pooled`, whose refunds stay returns once confirmed (E2);
every product-or-pooled class has a pooled twin, so the item survives in
`line_class` - `pooled_allowance` beside the `pooled_no_money` review 5 #4
asked for (E3); the confirmed-gift difference is measured with the keys
answered `cost` (E4).

**Taken by the author in revision 3b, from review 6** - the standing rule
applied (S), or a definition the design owed (E); none changes a figure:
- S1 (#1): the unconfirmed-suggestion note qualifies every figure its lines
  are in, for the file and both months - unanswered, one B "Adjust bad debt"
  line (-38,925.87) in 2010-10 carries T2's year-earlier base, and the
  headline's 99% is 86% without it.
- S2 (#4): the same-day-cancellation note qualifies gross sales, returns,
  orders and AOV too, and counts the return lines that COULD be
  cancellations (a named customer's same-day sale of the same product).
- S3 (#5): `discounts_in_prices` on every file - a price net of a discount
  cannot be told from a list price (Kaggle's unmapped *Discount Applied*).
- S4 (#7, #11): `unconfirmed_deductions` - a refund at a negative price
  cannot be told from a coupon. A negative-price line on a key that also
  sells can never be confirmed per key (answering the key moves its sales
  too): per-line answers are Phase 8.
- S5 (#8): `other_transaction_types` - v1 maps no type value, so a "Return"
  or a "Cash" is read by its signs, and reported. It fires on Kaggle, whose
  payment method is mapped as `transaction_type` (decision 8's item).
- S6 (#9): the "in" note qualifies returns and the customer figures, and
  says revenue is not reduced by returns booked as "in".
- E5 (#3): each note carries its lines and money for the file and both
  months; E2 follows the text of Q26 as Thach approved it.
- E6 (#10): the suggestions are the candidates `execute_run` finds on the
  file it classifies.
- E7 (#13): the name-only vote reads today's dated sale lines.
- E8 (#14): the `_source` rename amends CONTRACTS section 5 for three names;
  it happens before the plan runs (2E-t1 review cycle 2), so the flags and
  `changes[]` follow it.
- E9 (#2): a blank suggestion is a missing cell; the anchor lists
  `columns_out` and pins the candidates on the raw files.
- E10 (review 6b #1, #5-#8): a note is `{code, figures, text, measures}`
  with a fixed text per code and named measures per scope, so the anchor pins
  every number and every sentence; `diagnosis` joins the figures of the
  notes whose lines can sit in the history window stage 3 reads (one B line
  in 2010-10 carries T2's year-earlier base - S1); the figure lists are
  complete; the same-day note measures the sale side too.
- E11 (review 6b #4): `same_day_cancellations` reads products only - a pooled
  code is many items, so an M refund beside an M sale is not "the same
  product".

**Open, not blocking v1** (review 6 #12, for Thach): the closed list has no
class for pass-through money other than gift cards - sales tax, tips,
deposits booked as lines. Unanswered they are sales (no word suggests them),
and the nearest answers misplace them (`cost` reports tax as an expense,
`charge` keeps it in revenue). Neither demo file has such lines; v1 behaves
as today. Recommended: a v2 class `pass_through` (outside revenue, reported,
like a gift card), with its words.

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
stopped for Thach. Six would fabricate (the magnitude ledger's -30 read as
+30; a return moving no stock with no caveat; a refund typed "in" never
leaving revenue; unanswered "discounts" all bad debt; the "unconfirmed" mark
not reaching stages 2 and 3; a credit prefix mapped `return`), others needed
his definition, and the anchor had errors. Revision 2 answered them with his
v1 scope cut and his answers.

**Review 5** (revision 2, 2026-09-28, sixteen findings; `run7/2et/review5/`)
- the run stopped for Thach. Would fabricate: Q15's sign rule made a priced
receipt correction typed "in" a customer return (#1), and a customer return
booked "+, in" stayed outside revenue (#2). Needed his definition:
unconfirmed lines inside unanswered returns (#6), A1 and A4 (#10),
unmeasurable lines by month (#7). **Revision 3** answers them: #1, #2 and
A1 by Q25 (section 2) and the standing rule; #6 by Q26 (the
`unconfirmed_suggestions` note); A4 by Q27; #7 by Q28; and the
eleven author's fixes - #3 stage 4's stockout risk "not supported in v1";
#4 the pooled twins (E3); #5 the suggestions are the candidates; #8 the
notes in stage 3's output; #9 the pins through stage 1's real path, every
piece, exact equality; #11 no `undated_amount`; #12 the gift words' order
and no bare "voucher"; #13 `stock_in` money of no finite amount counted
apart, a month-sum overflow to 8D; #14 rule 1; #15 the mapping follows the
rename; #16 the out-of-revenue lines name no receipt, the gift difference
through the classes (E4), the prompts read the notes, the AI tier stated
(4.1).

**Review 6b** (revision 3b, scoped to the notes, the suggestion and the
anchor, 2026-09-28; fourteen findings; `run8/2et/review6b/`): it confirmed
every identity term, the notes4 figures the anchor quoted, the headlines, the
gift months and the 113 leaves, and the `suggested_classes` maps. Its
findings are the author's or the standing rule's: the notes cannot reach the
history window (#1 - E10: `diagnosis`), `suggested_class` names answers, not
classes (#2), the candidate pin was missing (#3 - now listed), pooled lines
in the same-day match (#4 - E11), the value counts over other lines (#5),
the sale side of a cancellation (#6), a short figure list (#7), numbers with
no field (#8 - E10), a name-only line's suggestion beside an inherited answer
(#9: the built code already carries none), the gift change's v1 leaves
(#10), the file-level and `unclassified` values (#11), a false reason and
-0.0 (#12), the rename's details (#13), the Kaggle plan's version (#14). No
finding needed the run to stop.

**Review 6** (revision 3, 2026-09-28; fourteen findings;
`run8/2et/review6/`). It re-checked every identity term,
`returns_on_suggested_keys`, Kaggle's unmeasurable counts per month, the 9
gift keys, the three headlines and the `suggested_classes` maps, and found
the rules of 4.2 total. Its findings of the standing rule's shape (#1, #4,
#5, #7, #8, #9, #11) are settled by the rule (S1-S6); the rest are the
author's (E5-E9, and #6 the prompts, #14 the wording and the 18 zero-amount
gift lines); #12 is open for Thach and does not block v1. No finding needed
the run to stop.
