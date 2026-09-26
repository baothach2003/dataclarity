"""Session 2E-d2 (Thach), stages 2 and 3, written before the change.

The user classes a product key in Review (confirmations.line_classes):
- charge (postage): stays in revenue and stays a sale or return row - orders,
  AOV and gross are unchanged - but is in no product table;
- discount: a deduction (2E-c) - in revenue, no sale, no return, no product;
  a -1 @ +price discount was a return line (2E-c2 item f);
- cost: left out of revenue and of every figure, as a stock-in line is;
- adjustment: the same, reported as the reconciling amount.
Unanswered, nothing changes. Stage 3's product lens gets a `non_product` term
(the charges' change in gross) and its members a "(not a product)" bucket, so
both still reconcile. metrics.json 11.0, diagnosis.json 10.0.

The shop, on the lines basis (no order id):
  July   Ann MUG 2 @ 10 = 20, Ann POST 1 @ 5 = 5, Bob CUP 1 @ 30 = 30,
         Dee B "Adjust bad debt" 1 @ -15 = -15
  August Ann MUG 1 @ 10 = 10, Ann POST 1 @ 8 = 8, Ann D "Discount" -1 @ 2 = -2,
         Bob CUP 2 @ 30 = 60, Bob POST 1 @ 8 = 8, AMAZONFEE "AMAZON FEE"
         1 @ -4 = -4 (no customer), Cy CUP 1 @ 30 = 30, Bob CUP -1 @ 30 = -30
  Sept 1 Ann MUG 1 @ 10 (August is the current month)
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import CoreMetrics, MetricsContract
from shared.products import product_keys
from shared.transactions import parse_transactions
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.diagnose.frame import history_window
from stages.diagnose.hypotheses import decomposition_gross
from stages.diagnose.inputs import build_run_data
from stages.diagnose.lever import month_revenue, returns_levels
from stages.diagnose.members import product_totals
from stages.diagnose.pvm import compute_products
from stages.diagnose.tree import compute_tree

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
           "Sku": "sku", "Name": "product_name"}
CLASSES = OrderConfirmations(line_classes=[
    LineClassAnswer(value="POST", field="sku", line_class="charge"),
    LineClassAnswer(value="D", field="sku", line_class="discount"),
    LineClassAnswer(value="AMAZONFEE", field="sku", line_class="cost"),
    LineClassAnswer(value="B", field="sku", line_class="adjustment"),
])


def _shop() -> pd.DataFrame:
    rows = [
        ("2026-07-03", "Ann", "M1", "MUG", "2", "10"), ("2026-07-03", "Ann", "POST", "POSTAGE", "1", "5"),
        ("2026-07-10", "Bob", "C1", "CUP", "1", "30"), ("2026-07-20", "Dee", "B", "Adjust bad debt", "1", "-15"),
        ("2026-08-03", "Ann", "M1", "MUG", "1", "10"), ("2026-08-03", "Ann", "POST", "POSTAGE", "1", "8"),
        ("2026-08-03", "Ann", "D", "Discount", "-1", "2"), ("2026-08-05", "Bob", "C1", "CUP", "2", "30"),
        ("2026-08-05", "Bob", "POST", "POSTAGE", "1", "8"), ("2026-08-15", None, "AMAZONFEE", "AMAZON FEE", "1", "-4"),
        ("2026-08-20", "Cy", "C1", "CUP", "1", "30"), ("2026-08-21", "Bob", "C1", "CUP", "-1", "30"),
        ("2026-09-01", "Ann", "M1", "MUG", "1", "10"),
    ]
    return pd.DataFrame([{"Date": d, "Cust": c, "Sku": s, "Name": n, "Qty": q, "Price": p}
                         for d, c, s, n, q, p in rows])


def test_unanswered_every_figure_is_as_today() -> None:
    core = assemble_metrics(_shop(), MAPPING, NOW).core

    assert (core.revenue_current, core.revenue_previous) == (pytest.approx(80.0), pytest.approx(40.0))
    # Sale lines: MUG, POST, CUP, POST, CUP; returns: the D line and the CUP refund.
    assert (core.orders_current, core.return_rate_current) == (5, pytest.approx(0.4))
    assert core.non_product == []


def test_costs_and_adjustments_leave_revenue() -> None:
    core = assemble_metrics(_shop(), MAPPING, NOW, CLASSES).core

    # August 80 without the fee's -4; July 40 without the bad debt's -15.
    assert (core.revenue_current, core.revenue_previous) == (pytest.approx(84.0), pytest.approx(55.0))
    assert [(m.period, m.revenue) for m in core.revenue_by_month][:2] == [
        ("2026-07", pytest.approx(55.0)), ("2026-08", pytest.approx(84.0))]


def test_charges_stay_orders_and_the_discount_is_no_return() -> None:
    core = assemble_metrics(_shop(), MAPPING, NOW, CLASSES).core

    # Still 5 sale lines (the two POST lines among them); one return line now.
    assert (core.orders_current, core.return_rate_current) == (5, pytest.approx(0.2))
    assert core.aov_current == pytest.approx(84.0 / 5)


def test_an_adjustment_line_names_no_active_customer() -> None:
    unanswered = assemble_metrics(_shop(), MAPPING, NOW).core
    classed = assemble_metrics(_shop(), MAPPING, NOW, CLASSES).core

    # July: Ann, Bob and - through the bad debt line only - Dee.
    assert (unanswered.active_customers_previous, classed.active_customers_previous) == (3, 2)


def test_no_classed_line_is_in_a_product_table() -> None:
    unanswered = assemble_metrics(_shop(), MAPPING, NOW).products
    classed = assemble_metrics(_shop(), MAPPING, NOW, CLASSES).products

    # Top products rank revenue above 0 only (the discount and the fee net below).
    assert [p.product for p in unanswered.top_products] == ["CUP", "POSTAGE", "MUG"]
    assert [(p.product, p.revenue) for p in classed.top_products] == [("CUP", 60.0), ("MUG", 10.0)]


def test_the_classed_lines_are_counted_with_their_reasons() -> None:
    rows = assemble_metrics(_shop(), MAPPING, NOW, CLASSES).core.non_product

    assert [(r.line_class, r.lines, r.amount, r.amount_current, r.amount_previous) for r in rows] == [
        ("charge", 3, pytest.approx(21.0), pytest.approx(16.0), pytest.approx(5.0)),
        ("discount", 1, pytest.approx(-2.0), pytest.approx(-2.0), 0.0),
        ("cost", 1, pytest.approx(-4.0), pytest.approx(-4.0), 0.0),
        ("adjustment", 1, pytest.approx(-15.0), 0.0, pytest.approx(-15.0)),
    ]
    assert [r.reason for r in rows] == [
        "3 lines classed in Review as charges paid by the customer stay in revenue and are in no "
        "product table",
        "1 line classed in Review as a discount stays in revenue as a deduction: it is no sale, no "
        "return, and in no product table",
        "1 line classed in Review as a fee or cost is left out of revenue and of every figure",
        # Review F8: "reported as a reconciling amount", not "the difference".
        "1 line classed in Review as an accounting adjustment is left out of revenue and of every "
        "figure, and reported here as a reconciling amount",
    ]


def test_each_class_is_one_row() -> None:
    base = assemble_metrics(_shop(), MAPPING, NOW, CLASSES).core.model_dump()
    rows = base["non_product"]

    with pytest.raises(ValidationError, match="non_product"):
        CoreMetrics.model_validate({**base, "non_product": [rows[0], rows[0]]})
    with pytest.raises(ValidationError):
        CoreMetrics.model_validate({**base, "non_product": [{**rows[0], "lines": 0}]})


def test_an_answer_applies_to_its_field_only() -> None:
    df = pd.DataFrame([{"Date": "2026-08-03", "Cust": "Ann", "Sku": sku, "Name": name, "Qty": "1", "Price": "8"}
                       for sku, name in (("POST", "POSTAGE"), (None, "POST"), ("post ", "POSTAGE"))])

    parsed = parse_transactions(df, MAPPING, CLASSES)

    # By identity (" post " is POST); a line with no SKU is keyed by its name.
    assert parsed.line_class.fillna("product").tolist() == ["charge", "product", "charge"]


def test_a_name_answer_classes_lines_without_a_sku() -> None:
    df = pd.DataFrame([{"Date": "2026-08-03", "Cust": "Ann", "Sku": None, "Name": "Postage ", "Qty": "1",
                        "Price": "8"}])
    answer = OrderConfirmations(line_classes=[LineClassAnswer(value="POSTAGE", field="product_name",
                                                              line_class="charge")])

    assert parse_transactions(df, MAPPING, answer).line_class.tolist() == ["charge"]


# --- stage 3 ---------------------------------------------------------------------------


def _run_data(confirmations: OrderConfirmations | None = CLASSES):
    metrics = assemble_metrics(_shop(), MAPPING, NOW, confirmations)
    return metrics, build_run_data(_shop(), MAPPING, metrics, confirmations)


def test_both_stages_read_the_same_revenue() -> None:
    metrics, data = _run_data()

    assert month_revenue(data, "2026-08") == pytest.approx(metrics.core.revenue_current)
    assert month_revenue(data, "2026-07") == pytest.approx(metrics.core.revenue_previous)


def test_the_discount_is_a_deduction_in_the_returns_lens() -> None:
    _, data = _run_data()

    levels = returns_levels(data)

    # August: gross 10+8+60+8+30 = 116, returns the CUP refund 30, deductions
    # the discount 2 (the fee is out) - 116 - 30 - 2 = 84.
    assert (levels["gross_cur"], levels["returns_cur"], levels["deductions_cur"]) == (
        pytest.approx(116.0), pytest.approx(30.0), pytest.approx(2.0))


def test_the_product_lens_carries_the_charges_as_their_own_term() -> None:
    _, data = _run_data()

    lens = compute_products(data)

    # Gross July 55 (MUG 20, POST 5, CUP 30), August 116 (MUG 10, POST 16,
    # CUP 90): the charges moved 5 -> 16, the products 50 -> 100.
    assert lens.non_product == pytest.approx(11.0)
    parts = lens.volume + lens.mix + lens.price + lens.new_products + lens.discontinued_products
    assert parts == pytest.approx(50.0)


def test_unanswered_the_product_lens_has_no_non_product_term() -> None:
    _, data = _run_data(None)

    assert compute_products(data).non_product == 0.0


def test_the_members_hold_the_classed_lines_in_one_bucket_that_is_no_product() -> None:
    _, data = _run_data()

    totals = product_totals(data)
    [bucket] = [key for key, label in totals.labels.items() if label == "(not a product)"]

    # July: POST 5 (the bad debt is out); August: POST 16 and the discount -2.
    assert (totals.rev_prev[bucket], totals.rev_cur[bucket]) == (pytest.approx(5.0), pytest.approx(14.0))
    assert bucket in totals.gap_keys
    assert float(totals.rev_cur.sum()) == pytest.approx(84.0)


def test_a_name_only_line_does_not_take_a_classed_sku() -> None:
    """Mutation check N6: a refund rung by name takes its name's one SKU
    (2E-f L4) - but a classed SKU names no product, so a name-only POSTAGE
    line stays its own product, not the charge's."""
    df = pd.DataFrame([{"Date": "2026-08-03", "Cust": "Ann", "Sku": sku, "Name": "POSTAGE", "Qty": "1", "Price": "8"}
                       for sku in ("POST", None)])

    keys = product_keys(df, parse_transactions(df, MAPPING, CLASSES))

    assert keys.fillna("none").tolist() == ["none", "name:postage"]


def test_the_whole_tree_reconciles_with_classed_lines() -> None:
    """Mutation check N11: the tree asserts at run time that the product
    lens sums to the change in gross; the charges' term must be in that sum."""
    _, data = _run_data()

    tree = compute_tree(data, history_window(data))

    assert tree.products.non_product == pytest.approx(11.0)


def test_the_product_decomposition_counts_the_charges_term() -> None:
    """Mutation check N12: step 7's scale for a product-lens share is every
    term's size, the charges' too."""
    _, data = _run_data()
    tree = compute_tree(data, history_window(data))
    p = tree.products

    gross = decomposition_gross(tree, "product")

    assert gross == pytest.approx(abs(p.volume) + abs(p.mix) + abs(p.price) + abs(p.new_products)
                                  + abs(p.discontinued_products) + 11.0)


def test_versions() -> None:
    assert SCHEMA_VERSION == "11.0"
    assert MetricsContract.supported_major == 11
    assert DiagnosisContract.supported_major == 10
