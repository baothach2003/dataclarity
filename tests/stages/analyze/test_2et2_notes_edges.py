"""Session 2E-t2's mutation check (Thach, 2026-09-28): the edges of the
notes and the unmeasurable reasons that the first file left untested -
docs/LINE_TAXONOMY.md section 3.

The file, by hand (July 2026 the previous month, August the current one):
  1  07-01 O1 Ann A1  Mug             2 @ 10  sale                         +20
  2  08-03 O2 Ann A1  Mug             3 @ 10  sale                         +30
  3  08-03 O3 Bo  A1  Mug            -1 @ 10  customer_return              -10  (Bo bought nothing that day)
  4  08-04 O4 Cy  M   Manual          1 @ 5   sale (suggested pooled)       +5
  5  08-05 O5 Cy  M   Manual         -1 @ 5   customer_return (suggested pooled) -5
  6  08-07 O6 Ed  DOT DOTCOM POSTAGE  1 @ 5   sale (suggested charge)       +5
  7  08-07 O6 Ed  A1  Mug             1 @ 10  sale, in the same order      +10
  8  08-08 O7 Ed  DOT DOTCOM POSTAGE  1 @ 5   sale (suggested charge), alone +5
  9  08-12 O8 Fay A1  Mug             - @ -   typed "Cash": unmeasurable, no quantity (the rules' order)
 10  09-02 O9 Ann A1  Mug             1 @ 10  sale (the file covers August)
August: gross 55, returns 15 -> net 40; July: gross 20 -> net 20.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.metrics import MetricsContract
from stages.analyze.assemble import assemble_metrics

NOW = datetime(2026, 9, 26, tzinfo=UTC)
MAPPING = {"Day": "transaction_date", "Order": "order_id", "Who": "customer", "Sku": "sku",
           "Name": "product_name", "Qty": "quantity", "Price": "unit_price", "Type": "transaction_type"}
ROWS = [
    ("2026-07-01", "O1", "Ann", "A1", "Mug", "2", "10", "out"),
    ("2026-08-03", "O2", "Ann", "A1", "Mug", "3", "10", "out"),
    ("2026-08-03", "O3", "Bo", "A1", "Mug", "-1", "10", "out"),
    ("2026-08-04", "O4", "Cy", "M", "Manual", "1", "5", "out"),
    ("2026-08-05", "O5", "Cy", "M", "Manual", "-1", "5", "out"),
    ("2026-08-07", "O6", "Ed", "DOT", "DOTCOM POSTAGE", "1", "5", "out"),
    ("2026-08-07", "O6", "Ed", "A1", "Mug", "1", "10", "out"),
    ("2026-08-08", "O7", "Ed", "DOT", "DOTCOM POSTAGE", "1", "5", "out"),
    ("2026-08-12", "O8", "Fay", "A1", "Mug", None, None, "Cash"),
    ("2026-09-02", "O9", "Ann", "A1", "Mug", "1", "10", "out"),
]


@pytest.fixture(scope="module")
def metrics() -> MetricsContract:
    df = pd.DataFrame(ROWS, columns=["Day", "Order", "Who", "Sku", "Name", "Qty", "Price", "Type"])
    return assemble_metrics(df, MAPPING, NOW)


def _notes(metrics: MetricsContract) -> dict:
    return {n.code: n for n in metrics.core.notes}


def _measures(note) -> dict:
    return {(m.name, m.scope): (m.lines, m.amount, m.orders, m.keys) for m in note.measures}


def test_the_identity(metrics: MetricsContract) -> None:
    current = metrics.core.identity.current
    assert (current.gross_sales, current.returns, current.net_revenue) == pytest.approx((55.0, 15.0, 40.0))
    # Cy's return is on a key suggested "pooled": confirming it keeps the line a return (E2).
    assert current.returns_on_suggested_keys == 0.0


def test_a_key_suggested_pooled_is_not_an_unconfirmed_suggestion(metrics: MetricsContract) -> None:
    # Only DOT's two lines; the order O6 also holds a Mug, so only O7 holds nothing but such lines.
    assert _measures(_notes(metrics)["unconfirmed_suggestions"]) == {
        ("lines", "file"): (2, 10.0, 1, 1), ("lines", "current"): (2, 10.0, 1, 1),
        ("lines", "previous"): (0, 0.0, 0, 0),
        ("returns", "file"): (0, 0.0, 0, None), ("returns", "current"): (0, 0.0, 0, None),
        ("returns", "previous"): (0, 0.0, 0, None)}


def test_a_return_on_a_day_another_customer_bought_is_no_same_day_cancellation(metrics: MetricsContract) -> None:
    # Decision 1: the note stands wherever the return rate is shown, with its
    # measures - here none, as Bo did not buy the Mug Ann bought that day.
    note = _notes(metrics)["same_day_cancellations"]
    assert {key: value[0] for key, value in _measures(note).items()} == {
        ("returns", "file"): 0, ("returns", "current"): 0, ("returns", "previous"): 0,
        ("sales", "file"): 0, ("sales", "current"): 0, ("sales", "previous"): 0,
        ("returns_unchecked", "file"): 0, ("returns_unchecked", "current"): 0,
        ("returns_unchecked", "previous"): 0}


def test_a_line_with_neither_quantity_nor_price_is_unmeasurable_for_its_quantity(metrics: MetricsContract) -> None:
    assert [(r.scope, r.reason, r.lines) for r in metrics.core.unmeasurable] == [
        ("file", "no quantity", 1), ("current", "no quantity", 1)]


def test_a_transaction_type_on_a_line_counted_nowhere_raises_no_note(metrics: MetricsContract) -> None:
    assert [n.code for n in metrics.core.notes] == [
        "same_day_cancellations", "unconfirmed_suggestions", "discounts_in_prices"]
