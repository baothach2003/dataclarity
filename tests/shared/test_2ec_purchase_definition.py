"""Session 2E-c (Thach): what counts as a purchase - ONE definition, shared by
both stages - and who is new. Written before the change.

1. A sale row is a counted row with quantity > 0 AND a positive line amount.
   A zero-amount line (a free item, a stock adjustment) and a line with a
   negative amount (a coupon, a discount, a bad-debt write-off) are not
   purchases. Measured on Online Retail II: 2,561 of 2,631 zero-amount lines
   have no customer (stock bookkeeping), and 61 of the other 70 ride on an
   invoice with a paid line; the five negative-amount lines are all "Adjust
   bad debt".
2. A customer's first purchase month is the month of their first sale row -
   unless their history OPENS with a refund, which proves a purchase before
   the file started: such a customer is never new (rule C). The opening day
   nets sale and return quantities, as the stage 3 bridge already did, so a
   same-day buy-and-refund is not an opening refund.
"""

import pandas as pd

from shared.first_purchase import first_purchase_months
from shared.products import product_keys
from shared.transactions import parse_transactions

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Cust": "customer"}


def _parsed(rows: list[tuple[str, str, str, str]]):
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust"])
    return df, parse_transactions(df, MAPPING)


def test_a_sale_row_needs_a_positive_amount() -> None:
    _, parsed = _parsed([
        ("2026-01-05", "2", "10", "a"),    # a sale: 20
        ("2026-01-05", "1", "0", "a"),     # a free item: 0
        ("2026-01-05", "1", "-5", "a"),    # a coupon: -5
        ("2026-01-05", "-1", "10", "a"),   # a return: -10
        ("2026-01-05", "0", "10", "a"),    # nothing moved
    ])

    assert parsed.sale.tolist() == [True, False, False, False, False]
    assert parsed.returned.tolist() == [False, False, False, True, False]


def _months(rows):
    """No product column here, so since 2E-f no return can be matched to a
    purchase: every first-day return still opens with a refund, as these
    tests were written. Per-product netting: test_2ef_first_day_and_customers."""
    df, parsed = _parsed(rows)
    return first_purchase_months(df["Cust"], parsed.dates, parsed.sale, parsed.returned,
                                 products=product_keys(df, parsed), units=parsed.units)


def test_the_first_purchase_is_the_first_sale_row() -> None:
    months = _months([("2026-02-10", "1", "10", "fresh")])

    assert months["fresh"] == "2026-02"


def test_a_history_that_opens_with_a_refund_has_no_first_purchase_in_the_file() -> None:
    """Refunded in January (goods bought before the file), bought in February:
    not a new customer in February."""
    months = _months([("2026-01-05", "-1", "10", "prefile"),
                      ("2026-02-10", "1", "10", "prefile")])

    assert months["prefile"] is None


def test_a_refund_only_customer_has_no_first_purchase() -> None:
    months = _months([("2026-02-05", "-2", "10", "refunder")])

    assert months["refunder"] is None


def test_a_same_day_buy_and_refund_opens_with_a_refund() -> None:
    """Bought 1 and returned 1 on the opening day. Was "2026-01" (net 0 - not
    an opening refund, 2E-c D3). REVERSED (Thach, 2E-c2): any return line on
    the first day opens the history with a refund - netting quantities
    across products fabricated "new" (10 pens and a returned chair). Since
    2E-f the same product nets on the opening day; with no product column,
    as here, nothing can be shown to be the same product, so still None."""
    months = _months([("2026-01-05", "1", "10", "sameday"),
                      ("2026-01-05", "-1", "10", "sameday")])

    assert months["sameday"] is None


def test_returning_more_than_was_bought_on_the_opening_day_is_an_opening_refund() -> None:
    """Bought 1, returned 3 on the opening day: net -2 - two of those units
    were bought before the file."""
    months = _months([("2026-01-05", "1", "10", "more"),
                      ("2026-01-05", "-3", "10", "more"),
                      ("2026-02-10", "1", "10", "more")])

    assert months["more"] is None


def test_a_coupon_or_a_free_item_before_the_first_sale_is_not_a_refund() -> None:
    """A coupon line and a free item prove no earlier purchase; the first
    purchase is the first sale row."""
    months = _months([("2026-01-05", "1", "-5", "coupon"),
                      ("2026-02-10", "1", "10", "coupon"),
                      ("2026-01-06", "1", "0", "free"),
                      ("2026-03-10", "1", "10", "free")])

    assert months["coupon"] == "2026-02"
    assert months["free"] == "2026-03"


def test_a_free_item_on_the_opening_day_does_not_hide_an_opening_refund() -> None:
    """Mutation check (2E-c): the opening day nets SALE and RETURN quantities
    only. Returned 1 and took a free replacement (1 @ 0) on the opening day:
    net -1 over sale and return lines, so the history opens with a refund.
    Netting every line (the free item's +1) read 0 - "not a refund" - and the
    February sale made a pre-file customer new."""
    months = _months([("2026-01-05", "-1", "10", "swap"),
                      ("2026-01-05", "1", "0", "swap"),
                      ("2026-02-10", "1", "10", "swap")])

    assert months["swap"] is None


def test_a_deduction_only_day_does_not_move_the_opening_day() -> None:
    """2E-c doubt-review F4: a coupon on 3 January, a refund on the 4th, a sale
    in August. The coupon day netted 0 over sale and return lines and was
    taken as the opening day, hiding the refund: the customer came out new
    in August. A deduction is not part of a purchase history, so the history
    opens on the 4th - with a refund."""
    months = _months([("2026-01-03", "1", "-5", "x"),
                      ("2026-01-04", "-2", "10", "x"),
                      ("2026-08-05", "1", "10", "x"),
                      ("2026-01-03", "1", "0", "y"),
                      ("2026-01-04", "-2", "10", "y"),
                      ("2026-08-05", "1", "10", "y")])

    assert (months["x"], months["y"]) == (None, None)


def test_the_opening_day_reads_the_same_in_any_row_order() -> None:
    """2E-c doubt-review F5: bought 0.3 and returned 0.1 + 0.2 on the opening
    day; the netted sum was -5.6e-17 in one row order and +0 in the other.
    Was "2026-01" for both (residue is not a refund). Since 2E-c2 no sum is
    taken - a return line on the first day opens with a refund - so both row
    orders read None, and the order can never matter."""
    rows = [("2026-01-05", "0.3", "10", "a"), ("2026-01-05", "-0.1", "10", "a"),
            ("2026-01-05", "-0.2", "10", "a"), ("2026-08-05", "1", "10", "a"),
            ("2026-01-05", "-0.1", "10", "b"), ("2026-01-05", "-0.2", "10", "b"),
            ("2026-01-05", "0.3", "10", "b"), ("2026-08-05", "1", "10", "b")]
    months = _months(rows)

    assert (months["a"], months["b"]) == (None, None)


def test_a_customer_with_only_deductions_has_no_first_purchase() -> None:
    """2E-c doubt-review cycle 2: only a refund-opener was set to None; a
    coupon-only or free-item-only customer came back NaN, so the bridge's
    `is None` count of arrivals without a first purchase missed them."""
    months = _months([("2026-08-05", "1", "-5", "coupononly"),
                      ("2026-08-06", "2", "0", "freeonly")])

    assert (months["coupononly"], months["freeonly"]) == (None, None)


# --- 2E-c2 (Thach, after 2E-c's review) ------------------------------------------


def test_a_return_line_needs_a_negative_amount() -> None:
    """Symmetric with the sale row (2E-c2): a zero-amount negative-quantity
    line is a stock write-off ("damaged"), not a customer return."""
    _, parsed = _parsed([("2026-01-05", "-1", "10", "a"),    # a return: -10
                         ("2026-01-05", "-1", "0", "a")])    # a write-off: 0

    assert parsed.returned.tolist() == [True, False]
    assert parsed.deduction.tolist() == [False, True]


def test_any_return_line_on_the_first_day_opens_the_history_with_a_refund() -> None:
    """2E-c2 (Thach), reversing 2E-c's same-day netting: 10 pens bought and a
    chair returned on the first day net +9 units, but the chair was bought
    before the file."""
    months = _months([("2026-08-07", "10", "1", "x"), ("2026-08-07", "-1", "500", "x")])

    assert months["x"] is None


def test_a_write_off_on_the_first_day_does_not_open_with_a_refund() -> None:
    """2E-c review cycle 3 F2: a -1 @ 0 line two days before a first purchase
    made the customer never new. A write-off is not a return (2E-c2)."""
    months = _months([("2026-08-03", "-1", "0", "zed"), ("2026-08-05", "2", "50", "zed")])

    assert months["zed"] == "2026-08"
