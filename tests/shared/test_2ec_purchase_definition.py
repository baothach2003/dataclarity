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
    df, parsed = _parsed(rows)
    return first_purchase_months(df["Cust"], parsed.dates, parsed.quantities,
                                 parsed.sale, parsed.returned)


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


def test_a_same_day_buy_and_refund_is_not_an_opening_refund() -> None:
    """Bought 1 and returned 1 on the opening day: net 0, not below zero."""
    months = _months([("2026-01-05", "1", "10", "sameday"),
                      ("2026-01-05", "-1", "10", "sameday")])

    assert months["sameday"] == "2026-01"


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


def test_an_opening_day_that_nets_to_residue_is_not_a_refund() -> None:
    """2E-c doubt-review F5: bought 0.3 and returned 0.1 + 0.2 on the opening
    day. In one row order the sum is -5.6e-17 - "a refund" - in the other
    +0. Residue is not a refund, whatever the order."""
    rows = [("2026-01-05", "0.3", "10", "a"), ("2026-01-05", "-0.1", "10", "a"),
            ("2026-01-05", "-0.2", "10", "a"), ("2026-08-05", "1", "10", "a"),
            ("2026-01-05", "-0.1", "10", "b"), ("2026-01-05", "-0.2", "10", "b"),
            ("2026-01-05", "0.3", "10", "b"), ("2026-08-05", "1", "10", "b")]
    months = _months(rows)

    assert (months["a"], months["b"]) == ("2026-01", "2026-01")


def test_a_customer_with_only_deductions_has_no_first_purchase() -> None:
    """2E-c doubt-review cycle 2: only a refund-opener was set to None; a
    coupon-only or free-item-only customer came back NaN, so the bridge's
    `is None` count of arrivals without a first purchase missed them."""
    months = _months([("2026-08-05", "1", "-5", "coupononly"),
                      ("2026-08-06", "2", "0", "freeonly")])

    assert (months["coupononly"], months["freeonly"]) == (None, None)
