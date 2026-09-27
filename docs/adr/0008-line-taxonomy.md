# ADR-0008: One closed line taxonomy, decided once in stage 1

## Status
APPROVED IN PRINCIPLE (Thach, 2026-09-28), subject to his eight answers
(folded in: `docs/LINE_TAXONOMY.md` section 8) and a fourth fresh-context
review of the revision. That review (2026-09-28) found issues that would
fabricate and that need his definitions (`docs/LINE_TAXONOMY.md` section 9,
questions 9-20), and demo figures to correct (the gift vouchers sit in 24
months, not six); a revision and a fifth review follow his answers. Nothing
is implemented yet (2E-t1..t3). The design it records:
`docs/LINE_TAXONOMY.md`.

## Date
2026-09-27 (fifth overnight run, session 2E-t - design only); revised
2026-09-28 with Thach's answers (sixth overnight run)

## Context

A sales export mixes lines that mean very different things: goods sold,
goods returned, discounts, postage the customer paid, marketplace fees,
bad-debt write-offs, stock received, stock damaged or found, gift vouchers.
Revenue, orders, units, the return rate, customer activity, the product
tables and the stock balance each need to know which is which.

The engine has read that meaning from the SIGNS of quantity and amount, in
several places (`shared/transactions.py`, `shared/products.py`,
`shared/first_purchase.py`, `shared/orders.py`, the stock balance in
`stages/analyze/metrics_products.py`, B2's refusal in stage 3), and grew one
class per incident: the deduction (2E-c), the return line (2E-c2), the
user's non-product classes (2E-d2), the charge and pooled items (2E-l), the
identity gap (2E-g). Signs are lossy - a customer return and a damaged
write-off both carry a negative quantity, a coupon and a refund both carry a
negative amount, a positive zero-price line is a free item on one invoice
and stock found on another - and money and stock were mixed in one bucket.
Measured on Online Retail II and Kaggle:

- the deduction bucket mixes discounts with zero-amount lines that move
  stock and no money (2,745 positive, 3,457 negative on Online Retail II),
  whose direction the signs do not give;
- the stock balance counts a zero-amount -20 line as stock coming BACK (57
  days to stockout instead of 17, on a file with stock-in lines);
- a gift voucher sold is counted as a sale (a liability until redeemed);
- all 18,827 return lines are on credit (C) invoices, which no rule reads;
- lines with no parseable quantity or price are counted nowhere and
  reported nowhere (Kaggle: 1,213, 9.6% of the file).

Each stage recomputes the meaning from the raw columns; they agree only
because they share the code.

## Decision

1. **Two questions decide a line's class**: what the ITEM is (per key: a
   product, a pooled code - including lines with neither SKU nor name - a
   charge, a discount, a gift card, a fee, an adjustment) and what the LINE
   does. Its money is read from the amount's sign; a source signal the user
   maps (a transaction-type value, which outranks an invoice prefix) changes
   that reading only where it adds what the signs lack - `return` (a return
   booked at positive signs), `stock in` (out of revenue, reported, as 2A),
   `stock out` (a zero-amount line's direction); `sale` and `credit` change
   nothing. A zero-amount line's direction is mapped per (description,
   sign). A signal never overrides the user's item answer.
2. **A closed class list on accounting categories** results, one class per
   line, from ordered rules that place every line: `sale`,
   `customer_return`, `restocked_return`, `pooled_sale`, `pooled_return`,
   `allowance`, `discount`, `charge`, `free_item`, `stock_write_off`,
   `stock_found`, `stock_count`, `no_movement` (counted, as today), and
   `gift_card_sale`, `gift_card_redemption`, `fee`, `adjustment`,
   `stock_in`, `unclassified`, `unmeasurable` (not counted, reported). The
   test for money: tied to the sale (revenue or contra-revenue) or to the
   cost of earning it (an expense, outside revenue); a line that moves goods
   and no money belongs to the stock ledger, which works in magnitudes.
   `counted` keeps today's meaning until the user confirms a gift-card
   class.
3. **One effects matrix** (`shared/line_effects.py`) - each class against
   gross sales, returns, discounts, other revenue, net revenue, customer
   money, customer presence, purchases, units, the return rate, the product
   tables and a separate stock ledger - is the single source of truth; its
   customer columns reproduce today's rules. Net revenue = gross sales -
   returns - discounts + other revenue; everything outside revenue is
   reported, never dropped.
4. **Classification happens once, in stage 1**: the user's answers and
   mappings, then the rules. Suggestions - class words, gift-card and
   write-off words, what the AI proposes a column means - are recorded and
   never applied alone (2E-d2; Thach's Q3: an unanswered file loses no
   revenue). Each line gets `line_class`, `item_source`, `movement_source`
   and `suggestions` in `cleaned.csv`; stages 2 and 3 read `line_class`
   only.
5. `unclassified` is only for a line no rule places (Thach, Q3); the rules
   place every line, and v1 refuses no shape (Thach, 2026-09-28), so it is
   the tested, empty class - never a user's answer.
6. **Cancellations are out of v1** (Thach, 2026-09-28): a same-day credit
   stays a return, and the return rate says so wherever it is shown - it
   includes same-day cancellations, which the data cannot separate.
7. **A zero-amount line's stock direction has no default** (Thach,
   2026-09-28): unknown until mapped; the product's days to stockout are null
   with a reason.

## Alternatives considered

### Keep inferring from signs, and add classes as incidents arrive
- Pros: no migration; each fix is local.
- Cons: every new shape needs a rule in several places, and the rules
  disagree the moment one is updated and another is not; signs cannot tell
  a return from a write-off, a coupon from a refund, or stock found from a
  free item.
- Rejected: it is how the current list grew.

### One class question, with a credit-note prefix mapped straight to a class
- Pros: simpler to explain.
- Cons: a C line of a fee or of postage would become a customer return
  (Online Retail II: 223 fee lines, -345,005.66, into returns; 537 pooled
  refunds into sales) - review 1 of the design.
- Rejected: the item and the kind of line are separate questions.

### Classify in each stage from the answers (today's `line_classes`)
- Pros: stage 1 stays small.
- Cons: two stages recompute one decision; nothing records which rule
  placed a line.
- Rejected: "classification once" is the brief; the source columns make
  every class auditable.

### Let the AI classify lines
- Pros: it can read descriptions no word list covers.
- Cons: it sees a 30-row sample (ADR-0002) and cannot see a file's codes,
  prefixes or pairs; its output would decide money.
- Rejected: the AI may suggest what a column means; the user confirms.

### A `cancellation` class for same-day sale-and-credit pairs
- Pros: an order that never happened would leave gross sales and returns.
- Cons: the data cannot tell it from a same-day return or a re-issue - on
  Online Retail II the credit comes BEFORE the "cancelled" sale in 439 of
  1,797 pairs, most of them a credit for an older invoice followed by a
  re-issue.
- Rejected for v1 (Thach, 2026-09-28): a same-day credit stays a return;
  the return rate is labelled as including same-day cancellations.

### Read a zero-amount line's stock direction from its sign
- Pros: every line moves stock with no answer.
- Cons: Online Retail II books write-offs negative and found stock positive,
  the opposite of the sale convention a return follows; a free item on an
  invoice is positive and goes out. Today's ledger reads a -20 write-off as
  +20.
- Rejected: an unknown direction makes the product's stock history
  incomplete (days to stockout null with a reason) until mapped - a
  suppression, never a fabricated number. No default either (Thach,
  2026-09-28): "negative = out, positive with no customer = in" is Online
  Retail II's convention alone.

## Consequences

- `cleaned.csv` gains four columns; the stage 1 contracts, `metrics.json`
  and `diagnosis.json` go to their next majors; readers refuse the earlier
  ones as today and the user answers again in Review.
- Measured on today's code, no revenue, product table or headline moves on
  either demo file unless the user confirms a new class. A confirmed
  gift-voucher class moves six months of Online Retail II (2011-10 by
  16.67, and 2010-10 and 2010-11, which seasonality reads), so 2011-11's
  headline must then be re-measured. Kaggle gains a count of its
  unmeasurable lines.
- The stock ledger stops fabricating: it works in magnitudes; a zero-amount
  line moves stock only once its direction is known (unknown, the product's
  days to stockout are null - about 29% of products on Online Retail II's
  shape); a return comes back only under a `return` signal.
- B2's refusal on unexplained negative-amount lines is kept for `allowance`;
  a confirmed discount no longer refuses it.
- Review gains the signal and direction mappings and shows the revenue
  identity and the unclassified share.
- The return rate carries a note (it includes same-day cancellations);
  unmeasurable lines are reported (2E-t2).
- The migration table (`docs/LINE_TAXONOMY.md` section 6) is the regression
  anchor: a demo difference it does not list stops the implementation.
