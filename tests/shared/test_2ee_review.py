"""2E-e doubt-review, written before the fixes (each run by execution first).

F5: two tills sharing a receipt numbering reuse ids on other days for other
    customers. Under the 10% tolerance the ids were MERGED into one order:
    orders 310 -> 283, AOV +9.5%, frequency below one order per buyer. An
    order is one order - one day, one customer - so the key is the id on that
    day for that customer: a collision splits, never merges.
F4 (with no customer column a one-per-day batch id passes) is NOT fixed here:
    "no day holds two ids" also refused a real shop taking one order a day,
    and the data cannot tell the two apart - recorded for Thach.
F9: the reason rounded 10.4% down to "10%", reading as a refusal AT the limit.
"""

import pandas as pd

from shared.orders import count_orders
from shared.transactions import parse_transactions

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Cust": "customer", "Inv": "order_id"}


def _parsed(rows, mapping=MAPPING):
    return parse_transactions(pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Cust", "Inv"]),
                              mapping)


def test_a_reused_receipt_number_is_two_orders_not_one() -> None:
    """Ten receipts of one line; receipt R1 is reused two days later by another
    customer (1 id in 10 spans - within the tolerance). 11 orders, not 10."""
    rows = [("2026-08-03", "1", "10", f"k{i}", f"R{i}") for i in range(10)]
    rows.append(("2026-08-05", "1", "10", "other", "R1"))

    parsed = _parsed(rows)

    assert parsed.orders_basis == "order_id"
    assert count_orders(parsed.order_key, parsed.sale) == 11


def test_the_refusal_reason_does_not_round_down_to_the_limit() -> None:
    """14 ids of 134 span (10.4%): refused, and the reason says 10.4%."""
    rows = []
    for index in range(134):
        rows.append(("2026-08-03", "1", "10", "k", f"I{index}"))
        rows.append(("2026-08-04" if index < 14 else "2026-08-03", "1", "10", "k", f"I{index}"))

    parsed = _parsed(rows)

    assert parsed.orders_basis == "lines"
    assert "10.4%" in parsed.orders_basis_reason


def test_a_receipt_reused_the_same_day_by_another_customer_is_two_orders() -> None:
    """Mutation check (F5): the key carries the customer too - receipt R1 used
    by two customers on the same day is two orders."""
    rows = [("2026-08-03", "1", "10", f"k{i}", f"R{i}") for i in range(10)]
    rows.append(("2026-08-03", "1", "10", "other", "R1"))

    parsed = _parsed(rows)

    assert parsed.orders_basis == "order_id"
    assert count_orders(parsed.order_key, parsed.sale) == 11


# --- review cycle 2, written before the fixes -------------------------------------


def test_a_header_style_export_does_not_split_its_orders() -> None:
    """Cycle 2 F2: the customer is written on each receipt's FIRST line only
    (ERP "invoice detail" exports). The check ignored the blank customer but
    the key made it a customer "", so every order split in two (orders 93 ->
    186, AOV halved). Within one id on one day, a blank customer is the one
    named customer: 3 receipts of 3 lines = 3 orders."""
    rows = []
    for receipt, customer in (("R1", "ann"), ("R2", "bob"), ("R3", "cy")):
        rows.append(("2026-08-03", "1", "10", customer, receipt))
        rows += [("2026-08-03", "1", "10", "", receipt)] * 2

    parsed = _parsed(rows)

    assert parsed.orders_basis == "order_id"
    assert count_orders(parsed.order_key, parsed.sale) == 3


def test_a_refusal_just_over_the_limit_says_more_than_ten_percent() -> None:
    """Cycle 2 F4: 251 of 2,500 ids (10.04%) printed "10.0%" - read as AT the
    limit. The reason gives the counts and says "more than 10%"."""
    rows = []
    for index in range(2500):
        rows.append(("2026-08-03", "1", "10", "k", f"I{index}"))
        rows.append(("2026-08-04" if index < 251 else "2026-08-03", "1", "10", "k", f"I{index}"))

    reason = _parsed(rows).orders_basis_reason

    assert "251 of 2,500" in reason and "more than 10%" in reason


def test_a_blank_customer_on_a_receipt_with_two_named_ones_stays_blank() -> None:
    """Mutation check (cycle 2): receipt R0 names ann AND bob on one day (1 id
    of 10 spans customers - within the tolerance) and has a line with no
    customer. There is no ONE customer to give that line, so it stays its own:
    R0 is three orders (ann, bob, blank) and the other nine one each = 12."""
    rows = [("2026-08-03", "1", "10", "ann", "R0"), ("2026-08-03", "1", "10", "bob", "R0"),
            ("2026-08-03", "1", "10", "", "R0")]
    rows += [("2026-08-03", "1", "10", f"k{i}", f"R{i}") for i in range(1, 10)]

    parsed = _parsed(rows)

    assert parsed.orders_basis == "order_id"
    assert count_orders(parsed.order_key, parsed.sale) == 12


# --- review cycle 3, written before the fix -----------------------------------------


def test_blank_order_ids_on_return_lines_make_the_file_count_lines_too() -> None:
    """Cycle 3 F1: the blank-id rule looked at sale lines only, so return lines
    rung up without a receipt were each "an order holding a return line": the
    return rate went 0.097 -> 0.387 on an unchanged business. A blank id on a
    sale OR a return line makes the file count lines."""
    rows = [("2026-08-03", "1", "10", "k", "A"), ("2026-08-03", "1", "10", "k", "B"),
            ("2026-08-04", "-1", "10", "k", ""), ("2026-08-04", "-1", "10", "k", "")]

    parsed = _parsed(rows)

    assert parsed.orders_basis == "lines"
    assert "2 of 4 sale and return lines have no order id" in parsed.orders_basis_reason
