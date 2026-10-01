"""Session 2E-l (Thach, 2026-09-27), the lines outside the products, written
before the change.

- Q7: an invoice holding only charges is NOT an order (orders feed frequency
  and RFM and must be purchases); its money stays in revenue. A charge line is
  no sale and no return: a postage refund is no return line.
- The returns lens carries the charges as a term of their own
  (delta_net = delta_gross - delta_returns - delta_deductions +
  delta_charges); the product lens is products only again, five terms.
- Q4: a key the user says pools many unnamed items ("pooled", Online Retail
  II's M "Manual") stays sale and return lines, but is never ranked as a
  product - it is held with the data gap.

The shop, August the current month (order ids I1..; credit notes C..):
  July   I1 Ann MUG 2 @ 10, I1 Ann POST 1 @ 5, I2 Bob CUP 1 @ 30
  August I3 Ann MUG 1 @ 10, I3 Ann POST 1 @ 8, I4 Bob POST 1 @ 8 (postage
         only), I5 Bob CUP 2 @ 30, I6 Cy CUP 1 @ 30, C7 Cy POST -1 @ 8,
         C8 Bob CUP -1 @ 30
  Sept 1 I9 Ann MUG 1 @ 10
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from contracts.diagnosis import DiagnosisContract, ProductLens, ReturnsLens
from contracts.metrics import MetricsContract
from shared.transactions import parse_transactions
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.diagnose.frame import history_window
from stages.diagnose.inputs import build_run_data
from stages.diagnose.lever import returns_levels
from stages.diagnose.members import NOT_A_PRODUCT_KEY, UNNAMED_PRODUCT_KEY, product_totals
from stages.diagnose.pvm import compute_products
from stages.diagnose.tree import compute_tree

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
LINES = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
         "Sku": "sku", "Name": "product_name"}
ORDERS = {**LINES, "Inv": "order_id"}
CHARGE = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])


def _shop() -> pd.DataFrame:
    rows = [
        ("2026-07-03", "I1", "Ann", "M1", "MUG", "2", "10"), ("2026-07-03", "I1", "Ann", "POST", "POSTAGE", "1", "5"),
        ("2026-07-10", "I2", "Bob", "C1", "CUP", "1", "30"),
        ("2026-08-03", "I3", "Ann", "M1", "MUG", "1", "10"), ("2026-08-03", "I3", "Ann", "POST", "POSTAGE", "1", "8"),
        ("2026-08-04", "I4", "Bob", "POST", "POSTAGE", "1", "8"), ("2026-08-05", "I5", "Bob", "C1", "CUP", "2", "30"),
        ("2026-08-06", "I6", "Cy", "C1", "CUP", "1", "30"), ("2026-08-07", "C7", "Cy", "POST", "POSTAGE", "-1", "8"),
        ("2026-08-08", "C8", "Bob", "C1", "CUP", "-1", "30"), ("2026-09-01", "I9", "Ann", "M1", "MUG", "1", "10"),
    ]
    return pd.DataFrame([dict(zip(("Date", "Inv", "Cust", "Sku", "Name", "Qty", "Price"), row, strict=True))
                         for row in rows])


@pytest.mark.parametrize(("mapping", "unanswered", "classed"), [
    # Lines: 5 sale lines (MUG, POST, POST, CUP, CUP) -> 3 without the postage.
    (LINES, 5, 3),
    # Order ids with a sale line: I3, I4, I5, I6 -> I4 holds only postage.
    (ORDERS, 4, 3),
])
def test_a_charge_is_no_order(mapping: dict[str, str], unanswered: int, classed: int) -> None:
    plain = assemble_metrics(_shop(), mapping, NOW).core
    charged = assemble_metrics(_shop(), mapping, NOW, CHARGE).core

    assert (plain.orders_current, charged.orders_current) == (unanswered, classed)
    # 10 + 8 + 8 + 60 + 30 - 8 - 30: the money stays.
    assert (plain.revenue_current, charged.revenue_current) == (pytest.approx(78.0), pytest.approx(78.0))
    assert charged.aov_current == pytest.approx(78.0 / 3)


def test_a_postage_refund_is_no_return_line() -> None:
    plain = assemble_metrics(_shop(), LINES, NOW).core
    charged = assemble_metrics(_shop(), LINES, NOW, CHARGE).core

    # Returns: the POST and the CUP refunds (2 of 5), then the CUP only (1 of 3).
    assert (plain.return_rate_current, charged.return_rate_current) == (pytest.approx(0.4), pytest.approx(1 / 3))


def test_the_charge_reason_says_it_is_no_order() -> None:
    [row] = assemble_metrics(_shop(), LINES, NOW, CHARGE).core.non_product

    # POST: I1, I3, I4 and C7.
    assert row.reason == ("4 lines classed in Review as charges paid by the customer stay in revenue, "
                          "are no order, and are in no product table")


def _data(confirmations: OrderConfirmations | None = CHARGE):
    metrics = assemble_metrics(_shop(), LINES, NOW, confirmations)
    return build_run_data(_shop(), LINES, metrics, confirmations)


def test_the_returns_lens_carries_the_charges() -> None:
    levels = returns_levels(_data())

    # August: gross 10 + 60 + 30 = 100, returns 30, charges 8 + 8 - 8 = 8;
    # July: gross 20 + 30 = 50, charges 5. 100 - 30 - 0 + 8 = 78.
    assert (levels["gross_cur"], levels["returns_cur"], levels["deductions_cur"], levels["charges_cur"]) == (
        pytest.approx(100.0), pytest.approx(30.0), 0.0, pytest.approx(8.0))
    assert (levels["gross_prev"], levels["charges_prev"]) == (pytest.approx(50.0), pytest.approx(5.0))


def test_the_tree_reconciles_with_the_charges_term() -> None:
    data = _data()

    tree = compute_tree(data, history_window(data))

    assert (tree.returns.charges_prev, tree.returns.charges_cur) == (pytest.approx(5.0), pytest.approx(8.0))


def test_the_product_lens_is_products_only_again() -> None:
    lens = compute_products(_data())

    # MUG 20 -> 10, CUP 30 -> 90: gross 50 -> 100.
    assert lens.volume + lens.mix + lens.price + lens.new_products + lens.discontinued_products == pytest.approx(50.0)
    assert "non_product" not in ProductLens.model_fields
    assert {"charges_prev", "charges_cur"} <= set(ReturnsLens.model_fields)


# --- pooled items (Q4) ------------------------------------------------------------------

POOLED = OrderConfirmations(line_classes=[LineClassAnswer(value="M", field="sku", line_class="pooled")])


def _pooled_shop() -> pd.DataFrame:
    """July: MUG 2 @ 10, M "Manual" 1 @ 40. August: MUG 1 @ 10, M 3 @ 50,
    M -1 @ 50 (a refund). September 1: MUG."""
    rows = [("2026-07-03", "Ann", "M1", "MUG", "2", "10"), ("2026-07-04", "Bob", "M", "Manual", "1", "40"),
            ("2026-08-03", "Ann", "M1", "MUG", "1", "10"), ("2026-08-04", "Bob", "M", "Manual", "3", "50"),
            ("2026-08-05", "Bob", "M", "Manual", "-1", "50"), ("2026-09-01", "Ann", "M1", "MUG", "1", "10")]
    return pd.DataFrame([dict(zip(("Date", "Cust", "Sku", "Name", "Qty", "Price"), row, strict=True)) for row in rows])


def test_pooled_lines_are_sales_and_returns_in_every_figure() -> None:
    plain = assemble_metrics(_pooled_shop(), LINES, NOW).core
    pooled = assemble_metrics(_pooled_shop(), LINES, NOW, POOLED).core

    # August: 10 + 150 - 50 = 110; 2 sale lines, 1 return line.
    for core in (plain, pooled):
        assert (core.revenue_current, core.orders_current, core.return_rate_current) == (
            pytest.approx(110.0), 2, pytest.approx(0.5))


def test_pooled_lines_are_never_ranked_as_a_product() -> None:
    plain = assemble_metrics(_pooled_shop(), LINES, NOW).products
    pooled = assemble_metrics(_pooled_shop(), LINES, NOW, POOLED).products

    assert [p.product for p in plain.top_products] == ["Manual", "MUG"]
    assert [p.product for p in pooled.top_products] == ["MUG"]


def test_pooled_lines_are_held_with_the_data_gap_in_stage_3() -> None:
    metrics = assemble_metrics(_pooled_shop(), LINES, NOW, POOLED)
    totals = product_totals(build_run_data(_pooled_shop(), LINES, metrics, POOLED))

    assert (totals.rev_prev[UNNAMED_PRODUCT_KEY], totals.rev_cur[UNNAMED_PRODUCT_KEY]) == (
        pytest.approx(40.0), pytest.approx(100.0))
    assert NOT_A_PRODUCT_KEY not in totals.rev_cur.index


def test_pooled_lines_are_listed_with_their_reason() -> None:
    [row] = assemble_metrics(_pooled_shop(), LINES, NOW, POOLED).core.non_product

    assert (row.line_class, row.lines, row.amount) == ("pooled", 3, pytest.approx(140.0))
    assert row.reason == ("3 lines classed in Review as pooled items (many items under one code) are "
                          "sales and returns in every figure, but no product table ranks them")


def test_the_tree_reconciles_with_pooled_lines() -> None:
    """Pooled lines are gross sales: the product lens holds them (in the
    unnamed bucket), or it would not add up to the change in gross."""
    metrics = assemble_metrics(_pooled_shop(), LINES, NOW, POOLED)
    data = build_run_data(_pooled_shop(), LINES, metrics, POOLED)

    tree = compute_tree(data, history_window(data))

    # Gross July 20 + 40 = 60, August 10 + 150 = 160.
    assert tree.returns.gross_cur - tree.returns.gross_prev == pytest.approx(100.0)


def test_a_line_with_a_sku_never_takes_another_skus_class() -> None:
    """A return rung on SKU M2 but named "POSTAGE": "postage" maps to POST
    alone among the sales, yet only a line WITHOUT a SKU takes the class of
    the SKU its name maps to."""
    df = pd.DataFrame([{"Date": "2026-08-03", "Cust": "Ann", "Sku": sku, "Name": "POSTAGE", "Qty": qty,
                        "Price": "5"} for sku, qty in (("POST", "1"), ("M2", "-1"))])

    parsed = parse_transactions(df, LINES, CHARGE)

    assert parsed.line_class.fillna("product").tolist() == ["charge", "product"]


def test_versions() -> None:
    assert SCHEMA_VERSION == "16.0"  # 12.0 in 2E-l; 13.0 in 2E-i; 14.0 in 2E-j; 15.0 in 2E-o; 16.0 since 2E-t1
    assert MetricsContract.supported_major == 16
    assert DiagnosisContract.supported_major == 18  # 18 since 3E1b; 17 since 2E-t2; 12 in 2E-m; 13 in 2E-n; 14 in 2E-i; 15 in 2E-j; 16 since 2E-o
