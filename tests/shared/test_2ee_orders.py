"""Session 2E-e (Thach): an optional canonical field `order_id`, written
before the change. The schema had no order field, so every "order" was a
LINE: on Online Retail II AOV was average line value (18.20 against 475.53
by invoice) and frequency was lines per customer (32.2 against 1.58).

- Mapped: orders = distinct order ids that have a sale row.
- Not mapped: every sale line is an order - basis "lines", labelled so.
- A sale line with a blank order id is an order on its own.
- A real order is one order: its lines share one day and one customer. When
  more than 10% of the ids span several days or customers the column is not
  an order id, and the figures fall back to lines with a reason. Measured gap:
  0.0% for Invoice and Transaction ID, 74-100% for every other column.
"""

import pandas as pd

from contracts.cleaning import OrderConfirmations
from shared.orders import ORDER_ID_MAX_SPANNING_SHARE, count_orders
from shared.transactions import parse_transactions

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Cust": "customer", "Inv": "order_id"}


def _parsed(rows, mapping=MAPPING):
    # One customer on every line: the check reads dates only, so the user's
    # Yes to Review's receipt question is given (2E-e2 review cycle 2 F4).
    df = pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust", "Inv"])
    return parse_transactions(df, mapping, OrderConfirmations(order_id_is_receipt=True))


def test_orders_are_distinct_order_ids_with_a_sale_row() -> None:
    """Invoice A has two sale lines, B one; C holds only a return. By hand:
    2 orders, not 3 sale lines."""
    parsed = _parsed([("2026-08-03", "1", "10", "k", "A"), ("2026-08-03", "2", "10", "k", "A"),
                      ("2026-08-04", "1", "10", "m", "B"), ("2026-08-05", "-1", "10", "m", "C")])

    assert parsed.orders_basis == "order_id"
    assert count_orders(parsed.order_key, parsed.sale) == 2


def test_without_an_order_id_every_sale_line_is_an_order() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "order_id"}
    parsed = _parsed([("2026-08-03", "1", "10", "k", "A"), ("2026-08-03", "2", "10", "k", "A"),
                      ("2026-08-04", "1", "10", "m", "B")], mapping)

    assert (parsed.orders_basis, parsed.orders_basis_reason) == ("lines", None)
    assert count_orders(parsed.order_key, parsed.sale) == 3


def test_sale_lines_with_blank_order_ids_make_the_file_count_lines() -> None:
    """A, A, blank, blank. Was: 1 order for A and one per blank line = 3
    (decision 1: a blank id is an order on its own). SUPERSEDED on the safe
    side after review cycle 2 (F1): ids blank until a POS upgrade made orders
    fall 279 -> 93 on an unchanged business. Any sale line without an id makes
    the file count lines - 4 here - and the reason says how many (no
    tolerance, Thach after 2E-e; both real files have no blank id)."""
    parsed = _parsed([("2026-08-03", "1", "10", "k", "A"), ("2026-08-03", "1", "10", "k", "A"),
                      ("2026-08-04", "1", "10", "m", ""), ("2026-08-04", "1", "10", "m", None)])

    assert parsed.orders_basis == "lines"
    # "sale and return lines" since review cycle 3 (a blank id on a return
    # line counts too).
    assert "2 of 4 sale and return lines have no order id" in parsed.orders_basis_reason
    assert count_orders(parsed.order_key, parsed.sale) == 4


def _ids(n_ids: int, spanning: int, by: str) -> list[tuple]:
    """`n_ids` orders of two lines each; the first `spanning` of them have
    their second line on another day (by="day") or customer (by="customer")."""
    rows = []
    for index in range(n_ids):
        split = index < spanning
        rows.append(("2026-08-03", "1", "10", "k", f"I{index}"))
        rows.append(("2026-08-04" if split and by == "day" else "2026-08-03", "1", "10",
                     "z" if split and by == "customer" else "k", f"I{index}"))
    return rows


def test_the_spanning_limit_is_ten_percent() -> None:
    assert ORDER_ID_MAX_SPANNING_SHARE == 0.10


def test_one_id_in_ten_spanning_days_is_still_an_order_id() -> None:
    """10% exactly - at the limit, not above it (a real order may cross
    midnight or ship over two days)."""
    parsed = _parsed(_ids(10, 1, "day"))

    assert parsed.orders_basis == "order_id"


def test_one_id_in_nine_spanning_days_is_not_an_order_id() -> None:
    """11.1% of the ids cover two days: the figures fall back to lines, and
    the reason says why."""
    parsed = _parsed(_ids(9, 1, "day"))

    assert parsed.orders_basis == "lines"
    assert "11.1%" in parsed.orders_basis_reason  # one decimal since the review (F9)
    assert count_orders(parsed.order_key, parsed.sale) == 18


def test_one_id_in_nine_spanning_customers_is_not_an_order_id() -> None:
    parsed = _parsed(_ids(9, 1, "customer"))

    assert parsed.orders_basis == "lines"
