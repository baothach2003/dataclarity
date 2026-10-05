"""Session 2E-t2 (Thach, 2026-09-28): stage 2 reads each line's class -
written before the code. docs/LINE_TAXONOMY.md sections 3, 5 and 6:
metrics.json's identity (gross sales - returns - discounts - other deductions
(unconfirmed) + other revenue = net revenue) with the returns on keys the
user did not confirm; the outside-revenue totals; `unclassified`;
`unmeasurable` for the file and the compared months; `undated_lines` without
the unmeasurable ones; the six notes (a fixed text per code, named measures
per scope); `suggested_classes` for the products metrics.json names; stock
figures "not supported in v1" on every file.

The file, by hand (July 2026 the previous month, August the current one):
  1  07-01 O1  Ann A1  Mug             2 @ 10   sale            +20
  2  07-15 O2  Bo  DOT DOTCOM POSTAGE  1 @ 5    sale (suggested charge) +5
  3  08-03 O3  Ann A1  Mug             3 @ 10   sale            +30
  4  08-03 O4  Ann A1  Mug            -1 @ 10   customer_return -10  (Ann bought A1 that day)
  5  08-04 O5  Cy  D   Discount       -1 @ 5    discount (answered)  -5
  6  08-05 O6  Cy  R9  Refund          1 @ -2   allowance        -2
  7  08-06 O7  Bo  POST POSTAGE        1 @ 4    charge (answered) +4
  8  08-07 O8  Bo  A2  Cup             5 @ 0    no_money          0
  9  08-08 O9  Dee DOT DOTCOM POSTAGE -1 @ 3    customer_return (suggested charge) -3
 10  08-09 O10 Ed  AMZ AMAZON FEE      1 @ -7   cost (answered)  -7, outside revenue
 11  08-10 O11 -   A1  Mug             5 @ 2    "in": stock_in   +10
 12  08-11 O12 -   A1  Mug             3 @ -    "in", no price: stock_in, money unknown
 13  08-12 O13 Fay A1  Mug             - @ 10   unmeasurable, no quantity
 14  07-20 O14 Fay A1  Mug             1 @ -    unmeasurable, no price
 15  (no date) O15 Gus A1 Mug          2 @ 10   sale, undated
 16  (no date) O16 Gus A1 Mug          - @ 10   unmeasurable (not also undated)
 17  09-02 O17 Ann A1  Mug             1 @ 10   sale (the file covers August)
August: gross 30, returns 13, discounts 5, other deductions 2, other revenue 4
-> net 14, the money moved 30+10+5+2+4+0+3 = 54; July: gross 25 -> net 25,
moved 25.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from contracts.lines import IdentityTerms
from contracts.metrics import MetricsContract
from stages.analyze.assemble import assemble_metrics

NOW = datetime(2026, 9, 26, tzinfo=UTC)
MAPPING = {"Day": "transaction_date", "Order": "order_id", "Who": "customer", "Sku": "sku",
           "Name": "product_name", "Qty": "quantity", "Price": "unit_price", "Type": "transaction_type"}
ROWS = [
    ("2026-07-01", "O1", "Ann", "A1", "Mug", "2", "10", "out"),
    ("2026-07-15", "O2", "Bo", "DOT", "DOTCOM POSTAGE", "1", "5", "out"),
    ("2026-08-03", "O3", "Ann", "A1", "Mug", "3", "10", "out"),
    ("2026-08-03", "O4", "Ann", "A1", "Mug", "-1", "10", "out"),
    ("2026-08-04", "O5", "Cy", "D", "Discount", "-1", "5", "out"),
    ("2026-08-05", "O6", "Cy", "R9", "Refund", "1", "-2", "out"),
    ("2026-08-06", "O7", "Bo", "POST", "POSTAGE", "1", "4", "out"),
    ("2026-08-07", "O8", "Bo", "A2", "Cup", "5", "0", "out"),
    ("2026-08-08", "O9", "Dee", "DOT", "DOTCOM POSTAGE", "-1", "3", "out"),
    ("2026-08-09", "O10", "Ed", "AMZ", "AMAZON FEE", "1", "-7", "out"),
    ("2026-08-10", "O11", None, "A1", "Mug", "5", "2", "in"),
    ("2026-08-11", "O12", None, "A1", "Mug", "3", None, "in"),
    ("2026-08-12", "O13", "Fay", "A1", "Mug", None, "10", "out"),
    ("2026-07-20", "O14", "Fay", "A1", "Mug", "1", None, "out"),
    ("not a date", "O15", "Gus", "A1", "Mug", "2", "10", "out"),
    ("not a date", "O16", "Gus", "A1", "Mug", None, "10", "out"),
    ("2026-09-02", "O17", "Ann", "A1", "Mug", "1", "10", "out"),
]
ANSWERS = OrderConfirmations(line_classes=[
    LineClassAnswer(value="D", field="sku", line_class="discount"),
    LineClassAnswer(value="POST", field="sku", line_class="charge"),
    LineClassAnswer(value="AMZ", field="sku", line_class="cost")])


@pytest.fixture(scope="module")
def metrics() -> MetricsContract:
    df = pd.DataFrame(ROWS, columns=["Day", "Order", "Who", "Sku", "Name", "Qty", "Price", "Type"])
    return assemble_metrics(df, MAPPING, NOW, ANSWERS)


def _terms(terms: IdentityTerms) -> tuple:
    return (terms.gross_sales, terms.returns, terms.discounts, terms.other_deductions, terms.other_revenue,
            terms.net_revenue, terms.returns_on_suggested_keys)


def test_the_months_compared(metrics: MetricsContract) -> None:
    assert (metrics.period.current, metrics.period.previous, metrics.period.previous_complete) == (
        "2026-08", "2026-07", True)


def test_the_identity_of_each_compared_month(metrics: MetricsContract) -> None:
    assert _terms(metrics.core.identity.current) == pytest.approx((30.0, 13.0, 5.0, 2.0, 4.0, 14.0, 3.0))
    assert _terms(metrics.core.identity.previous) == pytest.approx((25.0, 0.0, 0.0, 0.0, 0.0, 25.0, 0.0))
    assert (metrics.core.identity.current.money_moved, metrics.core.identity.previous.money_moved) == (54.0, 25.0)
    assert metrics.core.identity.current.net_revenue == metrics.core.revenue_current


def test_the_identity_is_refused_when_its_terms_do_not_add_up() -> None:
    with pytest.raises(ValueError, match="identity"):
        IdentityTerms(gross_sales=30, returns=13, discounts=5, other_deductions=2, other_revenue=4,
                      net_revenue=15, returns_on_suggested_keys=0, money_moved=54)


def test_what_is_outside_revenue(metrics: MetricsContract) -> None:
    rows = [(r.line_class, r.scope, r.sign, r.lines, r.amount, r.lines_without_amount)
            for r in metrics.core.outside_revenue]
    # Stock received by sign (review 1 #7): line 11 +10; line 12 has no price, its money unknown.
    assert rows == [("cost", "file", None, 1, -7.0, 0), ("cost", "current", None, 1, -7.0, 0),
                    ("stock_in", "file", "positive", 1, 10.0, 0), ("stock_in", "file", "no_money", 1, 0.0, 1),
                    ("stock_in", "current", "positive", 1, 10.0, 0), ("stock_in", "current", "no_money", 1, 0.0, 1)]


def test_nothing_is_unclassified(metrics: MetricsContract) -> None:
    u = metrics.core.unclassified
    assert (u.lines, u.amount, u.share_of_money_moved) == (0, 0.0, 0.0)


def test_the_unmeasurable_lines_by_scope_and_reason(metrics: MetricsContract) -> None:
    rows = [(r.scope, r.reason, r.lines) for r in metrics.core.unmeasurable]
    assert rows == [("file", "no quantity", 2), ("file", "no price", 1), ("current", "no quantity", 1),
                    ("previous", "no price", 1)]


def test_an_undated_line_is_reported_once(metrics: MetricsContract) -> None:
    # Line 15 is undated; line 16, undated too, is unmeasurable and reported there.
    assert metrics.core.undated_lines == 1


def _notes(metrics: MetricsContract) -> dict:
    return {n.code: n for n in metrics.core.notes}


def _measures(note) -> dict:
    return {(m.name, m.scope): (m.lines, m.amount, m.orders, m.keys) for m in note.measures}


def test_the_notes_present_and_in_order(metrics: MetricsContract) -> None:
    assert [n.code for n in metrics.core.notes] == [
        "same_day_cancellations", "returns_booked_as_in", "unconfirmed_suggestions", "unconfirmed_deductions",
        "discounts_in_prices"]


def test_the_same_day_cancellations_note(metrics: MetricsContract) -> None:
    note = _notes(metrics)["same_day_cancellations"]
    assert note.text.startswith("Returns and the return rate include same-day cancellations")
    assert note.figures == ["gross_sales", "returns", "return_rate", "orders", "aov", "customers", "products",
                            "diagnosis"]
    assert _measures(note) == {
        ("returns", "file"): (1, -10.0, 1, None), ("returns", "current"): (1, -10.0, 1, None),
        ("returns", "previous"): (0, 0.0, 0, None),
        ("sales", "file"): (1, 30.0, 1, None), ("sales", "current"): (1, 30.0, 1, None),
        ("sales", "previous"): (0, 0.0, 0, None),
        # Both return lines name their customer and are no pooled code (reviews 2 #2, 3 #1).
        ("returns_unchecked", "file"): (0, 0.0, 0, None),
        ("returns_unchecked", "current"): (0, 0.0, 0, None),
        ("returns_unchecked", "previous"): (0, 0.0, 0, None)}


def test_the_returns_booked_as_in_note(metrics: MetricsContract) -> None:
    note = _notes(metrics)["returns_booked_as_in"]
    assert note.text.startswith('Lines typed "in" are outside revenue as stock received.')
    assert note.figures == ["revenue", "returns", "return_rate", "aov", "units", "customers", "products",
                            "diagnosis"]
    got = _measures(note)
    assert got[("positive", "file")] == (1, 10.0, None, None)
    assert got[("unknown", "current")] == (1, None, None, None)
    assert got[("negative", "file")] == (0, 0.0, None, None)
    assert got[("positive", "previous")] == (0, 0.0, None, None)


def test_the_unconfirmed_suggestions_note(metrics: MetricsContract) -> None:
    note = _notes(metrics)["unconfirmed_suggestions"]
    assert "not confirmed in Review" in note.text
    assert _measures(note) == {
        ("lines", "file"): (2, 2.0, 1, 1), ("lines", "current"): (1, -3.0, 0, 1), ("lines", "previous"): (1, 5.0, 1, 1),
        ("returns", "file"): (1, -3.0, 1, None), ("returns", "current"): (1, -3.0, 1, None),
        ("returns", "previous"): (0, 0.0, 0, None)}


def test_the_unconfirmed_deductions_note(metrics: MetricsContract) -> None:
    note = _notes(metrics)["unconfirmed_deductions"]
    assert note.figures == ["revenue", "other_deductions", "returns", "return_rate", "aov", "customers", "products",
                            "diagnosis"]
    assert _measures(note) == {("lines", "file"): (1, -2.0, None, None), ("lines", "current"): (1, -2.0, None, None),
                               ("lines", "previous"): (0, 0.0, None, None)}


def test_the_discounts_in_prices_note_is_on_every_file(metrics: MetricsContract) -> None:
    note = _notes(metrics)["discounts_in_prices"]
    assert (note.figures, note.measures) == (["gross_sales", "discounts"], [])


def test_other_transaction_types_are_reported_by_value() -> None:
    rows = [("2026-07-01", "A1", "2", "10", "Cash"), ("2026-07-02", "A1", "1", "10", "Card"),
            ("2026-08-01", "A1", "3", "10", "Cash"), ("2026-08-02", "A1", "1", "10", "cash "),
            ("2026-08-03", "A1", "1", "10", "out"), ("2026-09-01", "A1", "1", "10", "Card")]
    df = pd.DataFrame(rows, columns=["Day", "Sku", "Qty", "Price", "Type"])
    mapping = {"Day": "transaction_date", "Sku": "product_name", "Qty": "quantity", "Price": "unit_price",
               "Type": "transaction_type"}
    note = {n.code: n for n in assemble_metrics(df, mapping, NOW).core.notes}["other_transaction_types"]
    # Read by its signs, a line of another type is in every figure a counted line is (review 1 #12).
    assert note.figures == ["revenue", "gross_sales", "returns", "other_deductions", "return_rate", "orders", "aov",
                            "units", "customers", "products", "diagnosis"]
    assert _measures(note) == {
        ("Card", "file"): (2, 20.0, None, None), ("Card", "current"): (0, 0.0, None, None),
        ("Card", "previous"): (1, 10.0, None, None),
        ("Cash", "file"): (3, 60.0, None, None), ("Cash", "current"): (2, 40.0, None, None),
        ("Cash", "previous"): (1, 20.0, None, None)}


def test_a_product_named_with_an_unconfirmed_suggestion(metrics: MetricsContract) -> None:
    # DOT fell from 5 to -3: a biggest decliner, suggested a charge nobody confirmed.
    assert [d.product for d in metrics.products.biggest_decliners or []] == ["DOTCOM POSTAGE"]
    assert metrics.products.suggested_classes == {"DOTCOM POSTAGE": "charge"}


def test_stock_figures_are_not_supported_in_v1_even_with_stock_in_lines(metrics: MetricsContract) -> None:
    assert metrics.products.velocity is None
    assert metrics.products.velocity_reason.startswith("stock figures are not supported in v1")


def test_metrics_json_is_16_0(metrics: MetricsContract) -> None:
    assert metrics.schema_version == "16.2"
    assert MetricsContract.model_validate_json(metrics.model_dump_json()) == metrics
