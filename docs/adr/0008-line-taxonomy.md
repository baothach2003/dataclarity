# ADR-0008: One closed line taxonomy, decided once in stage 1 - v1 the money ledger

## Status
APPROVED IN PRINCIPLE (Thach, 2026-09-28). Revision 2 folds in his v1 scope
cut and his answers to review 4 (`docs/LINE_TAXONOMY.md` sections 0 and 8).
The fifth review (2026-09-28) found that Q15's reading of "in" lines
fabricates on a priced stock ledger and needs his definition (design section
9, questions 21-24); revision 3 and a sixth review follow his answers.
Nothing is implemented yet (2E-t1..t3).
The design it records: `docs/LINE_TAXONOMY.md`.

## Date
2026-09-27 (fifth overnight run, session 2E-t - design only); revised
2026-09-28 with Thach's answers (sixth run) and his v1 scope cut (seventh
run)

## Context

A sales export mixes lines that mean very different things: goods sold,
goods returned, discounts, postage the customer paid, marketplace fees,
bad-debt write-offs, stock received, stock damaged or found, gift vouchers.
Revenue, orders, units, the return rate, customer activity and the product
tables each need to know which is which.

The engine has read that meaning from the SIGNS of quantity and amount, in
several places (`shared/transactions.py`, `shared/products.py`,
`shared/first_purchase.py`, `shared/orders.py`, B2's refusal in stage 3), and
grew one class per incident: the deduction (2E-c), the return line (2E-c2),
the user's non-product classes (2E-d2), the charge and pooled items (2E-l),
the identity gap (2E-g). Signs are lossy - a coupon and a refund both carry
a negative amount - and nothing recorded whether a class came from the user
or a rule. Measured on Online Retail II and Kaggle: a gift voucher sold is
counted as a sale (a liability until redeemed); lines with no parseable
quantity or price are counted nowhere and reported nowhere (Kaggle: 1,213,
9.6% of the file); the stock balance read a zero-amount -20 line as stock
coming back (57 days to stockout instead of 17, on a file with stock-in
lines).

Four fresh-context reviews showed that a stock ledger needs definitions the
data rarely supports - which way a zero-amount line moves stock, whether a
return goes back on the shelf, what a credit prefix or a receipt correction
means - each a way to print a wrong stock figure.

## Decision

1. **v1 is the money ledger only** (Thach, 2026-09-28). Every stock KPI -
   velocity, days to stockout, any low-stock figure - reads "not supported
   in v1" with that reason on every file. No source signal is mapped in
   Review (transaction-type values, invoice prefixes). The stock ledger and
   the signal mappings are a v2 item.
2. **Two questions decide a line's class**: what the ITEM is (per key: a
   product, a pooled code - including lines with neither SKU nor name - a
   charge, a discount, a gift card, a cost, an adjustment) and what the LINE
   does to money, read from the amount's sign. The canonical
   `transaction_type`'s "in" keeps 2A's reading with Thach's Q15: the
   amount's sign decides - negative is money back to a customer, in revenue
   through the line's item; otherwise stock received, outside revenue,
   reported.
3. **A closed class list on accounting categories** results, one class per
   line, from ordered rules that place every line: `sale`, `pooled_sale`,
   `customer_return`, `pooled_return`, `allowance` (unconfirmed),
   `discount`, `charge`, `no_money` (counted); `gift_card_sale`,
   `gift_card_redemption`, `cost`, `adjustment`, `stock_in`,
   `unclassified`, `unmeasurable` (not counted, reported). The test for
   money: tied to the sale (revenue or contra-revenue) or to the cost of
   earning it (an expense, outside revenue). The date does not decide the
   class; an undated line is in no month.
4. **One effects matrix** (`shared/line_effects.py`) - each class against
   gross sales, returns, discounts, other deductions (unconfirmed), other
   revenue, net revenue, customer money, customer presence, purchases, the
   first-day netting, units, the return rate, stage 2's product tables and
   stage 3's product dimension - is the single source of truth. Net revenue =
   gross sales - returns - discounts - other deductions + other revenue;
   everything outside revenue is reported, never dropped. On a file with no
   negative "in" line, no amount too large to add and no confirmed gift card,
   every set of lines today's readers use is unchanged (measured, both demo
   files).
5. **Classification happens once, in stage 1**: the user's answers, then the
   rules. Suggestions (class words, gift-card words) are recorded and never
   applied alone (2E-d2; Thach's Q3); stages 2 and 3 read `line_class` and
   `suggested_class` from `cleaned.csv` (with `class_source`), and every
   product they name that carries an unconfirmed suggestion is listed with it
   (Thach's Q17).
6. `unclassified` is only for a line no rule places (Thach, Q3); the rules
   place every line and v1 refuses no shape, so it is the tested, empty
   class.
7. **Cancellations are out of v1**: a same-day credit stays a return, and
   the return rate says so where it is shown.

## Alternatives considered

### Keep inferring from signs, and add classes as incidents arrive
- Pros: no migration; each fix is local.
- Cons: every new shape needs a rule in several places, and the rules
  disagree the moment one is updated and another is not.
- Rejected: it is how the current list grew.

### A stock ledger in v1 (the design's first four revisions)
- Pros: days to stockout on files with stock-in lines.
- Cons: it needs a direction for every zero-amount line, a restocking rule
  for returns, and a reading of credit prefixes and receipt corrections;
  review 4 found each of them printing a wrong stock figure (a -30 receipt
  correction read +30: 99 days where the truth was 39). Most POS exports
  carry no stock-in line at all.
- Rejected for v1 (Thach, 2026-09-28): "not supported in v1" rather than a
  figure that can be wrong; the v2 item.

### Source-signal mappings in Review (type values, invoice prefixes)
- Pros: exports that book returns at positive signs under a "Return" type
  would read correctly.
- Cons: a prefix mapped `return` flipped a positive credit line into a
  return (Online Retail II 2010-02: -747.14); their main use is the stock
  ledger.
- Rejected for v1 (Thach): the v2 item. A credit note is read by its lines'
  signs, as today.

### One class question, with a credit-note prefix mapped straight to a class
- Cons: a C line of a fee or of postage would become a customer return
  (Online Retail II: 223 fee lines, -345,005.66, into returns) - review 1.
- Rejected: the item and the kind of line are separate questions.

### Classify in each stage from the answers (today's `line_classes`)
- Cons: two stages recompute one decision; nothing records which rule
  placed a line.
- Rejected: "classification once" is the brief.

### Let the AI classify lines
- Cons: it sees a 30-row sample (ADR-0002) and cannot see a file's codes; its
  output would decide money.
- Rejected: the AI may suggest what a column means; the user confirms.

### A `cancellation` class for same-day sale-and-credit pairs
- Cons: the data cannot tell it from a same-day return or a re-issue (on
  Online Retail II the credit comes BEFORE the "cancelled" sale in 439 of
  1,797 pairs).
- Rejected for v1 (Thach, 2026-09-28): a same-day credit stays a return; the
  return rate is labelled as including same-day cancellations.

## Consequences

- `cleaned.csv` gains `line_class`, `class_source` and `suggested_class`;
  the stage 1 contracts carrying the line-class enum (it gains `gift_card`),
  metrics.json (16.0) and diagnosis.json (17.0) go to their next majors;
  readers refuse the earlier ones as today and the user answers again in
  Review.
- On both demo files no revenue, product table, verdict or headline moves:
  the differences are the versions, the velocity reason, additions (the
  identity, the outside-revenue totals, the unmeasurable report, the
  return-rate note, the suggested classes) and 7 gift-voucher candidates in
  Review (the regression anchor, `docs/LINE_TAXONOMY.md` section 6). A
  confirmed gift-voucher class would move 24 months of Online Retail II
  (2011-11's headline figures, not its rule or its 86%).
- 2C's stock derivation and its sign defect are removed; the Dashboard's
  low-stock table (6F, 7C) is out of v1.
- An "in" line with a negative amount is counted by its item (Q15); an
  amount too large to add is unmeasurable instead of counted.
- B2's refusal is unchanged (Q21); its relaxation for confirmed discounts is
  Phase 8.
- Review gains the gift-card answer, the identity for the whole file and the
  unclassified and unmeasurable counts.
- The migration table and anchor (`docs/LINE_TAXONOMY.md` section 6) are the
  regression reference: a demo difference they do not list stops the
  implementation.
