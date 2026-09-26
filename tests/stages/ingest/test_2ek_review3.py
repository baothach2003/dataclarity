"""Session 2E-k doubt-review cycle 3 (the bound), written before the fixes.

- F3 (FABRICATE on the walk-in shape): common labels were missed - the
  Vietnamese "Khach hang le" and "Khach vang lai", plurals ("Walk-ins"),
  underscores and codes ("Walk_In", "CASH01", "GUEST01"), "Misc",
  "Non-member", "Unregistered", "Cliente final", "Barverkauf", the Chinese
  and Indonesian defaults. A word may now carry digits, an underscore or a
  plural "s" after it; only a letter before or after it makes it part of
  another word. F4 (a "GUEST01" spelling kept its lines after "Guest" was
  confirmed) is asked about as its own word.
- F1 (FABRICATE): a first placeholder, already asked about as a word,
  shielded a second one from the 4-times test. The largest value is taken
  among the values not already asked about.
- F5 (SUPPRESS): when stage 1's own verdict is "date only", its unanswered
  parse counts lines and fills nothing - the fill is "not measured", not 0.
"""

import pandas as pd
import pytest

from shared.order_checks import order_checks
from stages.ingest.customer_placeholders import placeholder_candidates

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer"}


def _sales(customers: list[str | None]) -> pd.DataFrame:
    n = len(customers)
    return pd.DataFrame({"Day": ["2026-08-03"] * n, "Qty": "1", "Price": "10", "Cust": customers})


@pytest.mark.parametrize("spelling", [
    "Khách hàng lẻ", "Khách vãng lai", "Walk-ins", "Guests", "Walk_In", "CASH01", "GUEST01",
    "WALKIN1", "Misc", "Non-member", "Unregistered", "Cliente final", "Cliente Contado",
    "Barverkauf", "散客", "Pelanggan Umum"])
def test_the_common_walk_in_labels_are_words(spelling: str) -> None:
    customers = [f"C{i}" for i in range(31) for _ in range(3)] + [spelling] * 7

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [(c.value, c.why) for c in found] == [(spelling, "word")]


@pytest.mark.parametrize("name", ["Miscellaneous Ltd", "Guesthouse Ltd", "Bigcash Ltd", "Walker"])
def test_a_letter_before_or_after_still_makes_another_word(name: str) -> None:
    customers = [f"C{i}" for i in range(31) for _ in range(3)] + [name] * 7

    assert placeholder_candidates(_sales(customers), MAPPING) == []


def test_a_second_label_behind_a_first_one_is_still_the_largest_of_the_rest() -> None:
    # "Guest" on 300 lines (a word); "Front Desk" on 80, 20 times the next
    # real customer (4 lines each).
    customers = ["Guest"] * 300 + ["Front Desk"] * 80 + [f"C{i}" for i in range(155) for _ in range(4)]

    found = placeholder_candidates(_sales(customers), MAPPING)

    assert [(c.value, c.why) for c in found] == [("Guest", "word"), ("Front Desk", "share")]


def _priced(rows: list[tuple[str, int, float]]) -> pd.DataFrame:
    """(customer, lines, price) groups, quantity 1 each."""
    lines = [(customer, price) for customer, count, price in rows for _ in range(count)]
    return pd.DataFrame({"Day": "2026-08-03", "Qty": "1", "Price": [str(p) for _, p in lines],
                         "Cust": [c for c, _ in lines]})


def test_the_rest_is_taken_by_lines_alone() -> None:
    # Mutation check P6. Lines: Guest 300 (a word), Front Desk 80, each C 4:
    # Front Desk is 20 times the rest. Revenue: Front Desk 80 at 1 each, 2
    # times a C's 40 - so only the lines find it. 8% of the 1000 lines.
    df = _priced([("Guest", 300, 10), ("Front Desk", 80, 1)] + [(f"C{i}", 4, 10) for i in range(155)])

    found = placeholder_candidates(df, MAPPING)

    assert [c.value for c in found] == ["Guest", "Front Desk"]


def test_the_rest_is_taken_by_revenue_alone() -> None:
    # Mutation check P7. Revenue: Guest 3000 (a word), Front Desk 8 lines at
    # 100 = 800, each C 40: 20 times the rest, 8% of the 10,000. Lines:
    # Front Desk's 8 are 2 times a C's 4 - so only the revenue finds it.
    df = _priced([("Guest", 300, 10), ("Front Desk", 8, 100)] + [(f"C{i}", 4, 10) for i in range(155)])

    found = placeholder_candidates(df, MAPPING)

    assert [c.value for c in found] == ["Guest", "Front Desk"]


def test_a_line_of_negative_amount_is_no_sale_revenue() -> None:
    # Mutation check P10: quantity 1 at price -30 is no sale (as in
    # parse_transactions), so Guest's sale revenue is its 3 lines of 10, of
    # the 960 sold: 3.125%. Counted as a sale it would net Guest to 0.
    df = _priced([("Guest", 3, 10), ("Guest", 1, -30)] + [(f"C{i}", 3, 10) for i in range(31)])

    found = placeholder_candidates(df, MAPPING)

    assert [(c.value, c.lines, c.revenue_pct) for c in found] == [("Guest", 4, pytest.approx(3.125))]


def test_the_fill_is_not_measured_when_the_check_reads_dates_only() -> None:
    """6 walk-in receipts with no customer and 4 receipts named on their first
    line: most receipts name no customer, so unanswered the file counts lines
    and fills nothing - but with the receipt answer Yes it fills 4 lines."""
    rows = []
    for index in range(10):
        day = f"2026-08-{index + 1:02d}"
        name = f"C{index}" if index < 4 else None
        rows += [(day, f"R{index}", name), (day, f"R{index}", None)]
    df = pd.DataFrame([{"Day": d, "Qty": "1", "Price": "10", "Inv": i, "Cust": c} for d, i, c in rows])

    checks = order_checks(df, {**MAPPING, "Inv": "order_id"})

    assert (checks.date_only, checks.fill_lines) == (True, None)
