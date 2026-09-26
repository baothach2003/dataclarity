"""Session 2E-d2 doubt-review cycle 1, written before the fixes.

- F1 (FABRICATE, blocking: Online Retail II's 2011-11 new customers read 190
  for 191): a classed charge had no product key, so a postage refund on a
  customer's first day was "nameless" - the history opened with a refund and
  the customer was never new. The first-day netting keys a classed line by
  its own line key.
- F2 (FABRICATE): P1/P2's "products sold in both periods" counted the
  "(not a product)" bucket, which the product lens's L never holds.
- F5: an amount that overflows (1e200 x 1e200) crashed the schema step.
- F8 (FABRICATE, wording): the adjustment reason claimed its amount
  reconciles the file's total with the revenue shown - untrue beside fees,
  "in" rows or undated lines. It is reported as a reconciling amount.
- F9 (FABRICATE): a left-out adjustment line named its receipt's walk-in
  lines' customer, which an "in" row never does.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import LineClassAnswer, OrderConfirmations
from shared.transactions import parse_transactions
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.frame import history_window
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.inputs import build_run_data
from stages.diagnose.tree import compute_tree
from stages.ingest.non_product_lines import non_product_candidates
from tests.stages.diagnose.test_hypotheses import by_id, step7

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
POST_CHARGE = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])
COLUMNS = ("Date", "Inv", "Cust", "Sku", "Name", "Qty", "Price")


def _frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame([dict(zip(COLUMNS, row, strict=True)) for row in rows])


def test_a_refunded_charge_on_the_first_day_does_not_unmake_a_new_customer() -> None:
    """Zed's first day (August): CUP 3 @ 30 and POST 1 @ 5, the postage
    refunded the same day. He is new with 90, in both stages, classed or not."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
               "Sku": "sku", "Name": "product_name", "Inv": "order_id"}
    df = _frame([
        ("2026-07-03", "I1", "Ann", "M1", "MUG", "2", "10"), ("2026-07-03", "I1", "Ann", "POST", "POSTAGE", "1", "5"),
        ("2026-08-05", "I2", "Zed", "C1", "CUP", "3", "30"), ("2026-08-05", "I2", "Zed", "POST", "POSTAGE", "1", "5"),
        ("2026-08-05", "C3", "Zed", "POST", "POSTAGE", "-1", "5"), ("2026-08-06", "I4", "Ann", "M1", "MUG", "1", "10"),
        ("2026-09-01", "I5", "Ann", "M1", "MUG", "1", "10"),
    ])

    metrics = assemble_metrics(df, mapping, NOW, POST_CHARGE)
    data = build_run_data(df, mapping, metrics, POST_CHARGE)
    bridge = compute_tree(data, history_window(data)).customers

    split = metrics.customers.new_vs_returning
    assert (split.new_customers, split.new_revenue) == (1, pytest.approx(90.0))
    assert (bridge.new, bridge.resurrected) == (pytest.approx(90.0), 0.0)


def test_the_charges_bucket_is_no_product_sold_in_both_periods() -> None:
    """A catalogue that rotates every month, postage in each: no product is
    sold in both months, so P1 and P2 cannot be judged."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Cust": "customer",
               "Sku": "sku", "Name": "product_name"}
    rows = []
    for year, month in [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 7)]:
        for day in range(1, 28, 3):
            rows += [(f"{year}-{month:02d}-{day:02d}", None, f"c{day}", f"S{month}", f"ITEM {year} {month}", "1", "20"),
                     (f"{year}-{month:02d}-{day:02d}", None, f"c{day}", "POST", "POSTAGE", "1", "5")]
    for day in range(1, 28):
        rows += [(f"2026-07-{day:02d}", None, f"c{day}", sku, name, "1", price)
                 for sku, name, price in (("A", "ALPHA", "20"), ("B", "BETA", "15"), ("POST", "POSTAGE", "5"))]
        rows += [(f"2026-08-{day:02d}", None, f"c{day}", sku, name, "1", price)
                 for sku, name, price in (("C", "GAMMA", "12"), ("D", "DELTA", "10"), ("POST", "POSTAGE", "9"))]
    rows.append(("2026-09-01", None, "c1", "C", "GAMMA", "1", "25"))
    df = _frame(rows).drop(columns="Inv")
    metrics = assemble_metrics(df, mapping, NOW, POST_CHARGE)

    results = by_id(evaluate_hypotheses(step7(build_run_data(df, mapping, metrics, POST_CHARGE))))

    for hypothesis in ("P1", "P2"):
        assert (results[hypothesis].verdict, results[hypothesis].evidence) == (
            "inconclusive", {"products_in_both_periods": 0})


def test_an_overflowing_amount_does_not_crash_the_candidates() -> None:
    mapping = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
               "Name": "product_name"}
    df = pd.DataFrame({"Day": "2026-08-03", "Sku": ["POST", "POST"], "Name": "POSTAGE", "Qty": ["1e200", "1"],
                       "Price": ["1e200", "5"]})

    [found] = non_product_candidates(df, mapping)

    assert (found.lines, found.positive) == (1, 5.0)


def test_the_adjustment_reason_says_what_it_is_reported_as() -> None:
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
               "Name": "product_name"}
    df = pd.DataFrame({"Date": ["2026-07-20", "2026-08-03", "2026-09-01"], "Sku": ["B", "M1", "M1"],
                       "Name": ["Adjust bad debt", "MUG", "MUG"], "Qty": "1", "Price": ["-15", "10", "10"]})
    bad_debt = OrderConfirmations(line_classes=[LineClassAnswer(value="B", field="sku", line_class="adjustment")])

    [row] = assemble_metrics(df, mapping, NOW, bad_debt).core.non_product

    assert row.reason == ("1 line classed in Review as an accounting adjustment is left out of revenue "
                          "and of every figure, and reported here as a reconciling amount")


def test_a_left_out_line_names_no_receipt() -> None:
    """Receipt R9: a walk-in MUG line and a bad-debt line under Dee. Classed
    an adjustment, the bad-debt line is left out as an "in" row is - and an
    "in" row never names a receipt's other lines."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
               "Name": "product_name", "Cust": "customer", "Inv": "order_id"}
    rows = [(f"2026-08-0{i}", f"R{i}", f"c{i}", "M1", "MUG", "1", "10") for i in range(1, 9)]
    rows += [("2026-08-09", "R9", None, "M1", "MUG", "5", "10"),
             ("2026-08-09", "R9", "Dee", "B", "Adjust bad debt", "1", "-15")]
    bad_debt = OrderConfirmations(line_classes=[LineClassAnswer(value="B", field="sku", line_class="adjustment")])

    parsed = parse_transactions(_frame(rows), mapping, bad_debt)

    assert parsed.orders_basis == "order_id"
    assert pd.isna(parsed.customers.iloc[8])
