"""Session 2E in stage 2, written from the symptoms before the fix (Thach's
decisions, 2E). Every expected number is derived by hand in the docstring.

1. A return line is not an order: orders, AOV (net revenue / sale orders),
   return_rate (return lines / sale orders), RFM frequency (sale orders).
2. An incomplete previous month makes every figure whose only purpose is to
   compare the two months unavailable, with a reason; raw totals stay.
3. A percentage against a non-positive base is unavailable; biggest
   decliners rank by the fall in money, so a doubled loss is a decliner and
   a recovery is not.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.analyze.metrics_core import compute_core_metrics
from stages.analyze.rfm import rfm_snapshot

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Product": "product_name", "Cat": "category", "Cust": "customer"}
TYPED = {**MAPPING, "Type": "transaction_type"}


def r(day: str, qty: float, price: float = 10.0, product: str = "Widget",
      cat: str = "A", cust: str = "Alice", kind: str | None = None) -> dict:
    row = {"Date": day, "Qty": str(qty), "Price": str(price), "Product": product,
           "Cat": cat, "Cust": cust}
    if kind is not None:
        row["Type"] = kind
    return row


# --- 1. orders ----------------------------------------------------------------------


def test_a_return_line_is_not_an_order() -> None:
    """November 2011: four sales of 2 x 10 (80) and one return of -1 x 10 (-10).
    Net revenue 70. Orders 4 (was 5). AOV 70 / 4 = 17.5 (was 70 / 5 = 14.0).
    Return rate 1 return / 4 orders = 0.25 (was 1 / 5 = 0.2)."""
    df = pd.DataFrame([r("2011-10-01", 1)]
                      + [r(f"2011-11-{d:02d}", 2) for d in (1, 8, 15, 22)]
                      + [r("2011-11-30", -1)])

    _, core = compute_core_metrics(df, MAPPING, NOW)

    assert core.revenue_current == pytest.approx(70.0)
    assert core.orders_current == 4
    assert core.aov_current == pytest.approx(17.5)
    assert core.return_rate_current == pytest.approx(0.25)


def test_a_zero_quantity_line_is_not_an_order() -> None:
    """Two sales of 1 x 10 and a 0-quantity line on the 30th: orders 2 (was
    3), AOV 20 / 2 = 10 (was 20 / 3 = 6.67)."""
    df = pd.DataFrame([r("2011-10-01", 1), r("2011-11-01", 1), r("2011-11-02", 1),
                       r("2011-11-30", 0)])

    _, core = compute_core_metrics(df, MAPPING, NOW)

    assert (core.orders_current, core.aov_current) == (2, pytest.approx(10.0))
    # Nor is it a return: 0 return lines / 2 orders (mutation check, 2E).
    assert core.return_rate_current == 0.0


def test_rfm_frequency_counts_sale_orders_not_return_lines() -> None:
    """Ann: one sale and three return lines. Bob: two sales. By rows Ann's
    frequency was 4 and Bob's 2; by sale orders it is 1 and 2."""
    table = pd.DataFrame({
        "customer": ["ann", "ann", "ann", "ann", "bob", "bob"],
        "date": pd.to_datetime(["2011-11-01"] * 4 + ["2011-11-02", "2011-11-03"]),
        "revenue": [40.0, -10.0, -10.0, -10.0, 10.0, 10.0],
        "sale": [True, False, False, False, True, True],
    })

    snapshot = rfm_snapshot(table, datetime(2011, 12, 1).date())

    assert snapshot.loc["ann", "frequency"] == 1
    assert snapshot.loc["bob", "frequency"] == 2


# --- 2. an incomplete previous month ----------------------------------------------


def _partial_previous() -> pd.DataFrame:
    """The 3E1 reproduction's shape: one sale a day from 15 January to 28
    February 2011. January (the previous month) holds 17 days."""
    days = pd.date_range("2011-01-15", "2011-02-28").strftime("%Y-%m-%d")
    return pd.DataFrame([r(day, 1) for day in days])


def test_a_partial_previous_month_makes_every_comparison_unavailable() -> None:
    """Revenue 170 -> 280 would read +64.7%. The file cannot say that."""
    metrics = assemble_metrics(_partial_previous(), MAPPING, NOW)
    reason = metrics.period.previous_incomplete_reason

    assert metrics.period.previous_complete is False
    assert "2011-01-01" in reason
    assert metrics.core.revenue_change_pct is None
    assert metrics.core.revenue_change_pct_reason == reason
    assert metrics.products.biggest_decliners is None
    assert metrics.products.biggest_decliners_reason == reason
    assert all(change.contribution_pct is None for change in metrics.by_dimension.category)
    assert metrics.by_dimension.contribution_reason == reason
    assert all(segment.customers_previous is None for segment in metrics.customers.segments)
    assert metrics.customers.customers_previous_reason == reason


def test_raw_totals_from_a_partial_previous_month_stay() -> None:
    """They are true counts of what the file holds for January: 17 x 10."""
    metrics = assemble_metrics(_partial_previous(), MAPPING, NOW)

    assert metrics.core.revenue_previous == pytest.approx(170.0)
    assert metrics.core.orders_previous == 17


def test_a_stock_in_row_on_the_first_does_not_complete_the_previous_month() -> None:
    """A stock-in row on 1 January is not a sale: January's first counted
    row is still the 15th."""
    df = pd.concat([pd.DataFrame([r("2011-01-01", 100, kind="in")]),
                    _partial_previous().assign(Type="out")])

    metrics = assemble_metrics(df, TYPED, NOW)

    assert metrics.period.previous_complete is False


def test_a_complete_previous_month_reports_its_comparisons() -> None:
    """January from the 1st: revenue 31 x 10 = 310 -> February 28 x 10 = 280:
    (280 - 310) / 310 * 100 = -9.677...%."""
    days = pd.date_range("2011-01-01", "2011-02-28").strftime("%Y-%m-%d")
    metrics = assemble_metrics(pd.DataFrame([r(day, 1) for day in days]), MAPPING, NOW)

    assert metrics.period.previous_complete is True
    assert metrics.period.previous_incomplete_reason is None
    assert metrics.core.revenue_change_pct == pytest.approx(-9.6774, abs=1e-4)
    assert metrics.core.revenue_change_pct_reason is None


# --- 3. non-positive bases -----------------------------------------------------------


def test_revenue_change_pct_is_unavailable_against_a_negative_previous_month() -> None:
    """October nets -100 (a sale of 10 on the 1st and a refund of -110);
    November -200 (10 on the 1st, -210 on the 30th). The percentage was
    (-200 - -100) / -100 * 100 = +100%, a doubled loss read as growth."""
    df = pd.DataFrame([r("2011-10-01", 1), r("2011-10-02", -11),
                       r("2011-11-01", 1), r("2011-11-30", -21)])

    _, core = compute_core_metrics(df, MAPPING, NOW)

    assert (core.revenue_previous, core.revenue_current) == (pytest.approx(-100.0), pytest.approx(-200.0))
    assert core.revenue_change_pct is None
    assert "negative" in core.revenue_change_pct_reason


def test_a_doubled_loss_is_a_decliner_and_a_recovery_is_not() -> None:
    """PROJECT_PLAN 2E. Product Leak: -100 -> -200 (a fall of 100). Product
    Mend: -100 -> +500 (a rise). Product Slide: 100 -> 50 (a fall of 50,
    -50%). The old list dropped Leak (+100%) and ranked Mend first (-600%).
    Now: Leak then Slide, by the fall in money; Leak's percentage is
    unavailable (negative base) and Slide's is -50.0."""
    df = pd.DataFrame([
        r("2011-10-01", 1, product="Leak"), r("2011-10-02", -11, product="Leak"),
        r("2011-11-01", 1, product="Leak"), r("2011-11-30", -21, product="Leak"),
        r("2011-10-01", 1, product="Mend"), r("2011-10-02", -11, product="Mend"),
        r("2011-11-01", 50, product="Mend"),
        r("2011-10-01", 10, product="Slide"), r("2011-11-01", 5, product="Slide"),
        # Flat: 100 -> 100, a change of 0 - not a decline (mutation check, 2E).
        r("2011-10-01", 10, product="Flat"), r("2011-11-01", 10, product="Flat"),
    ])

    decliners = assemble_metrics(df, MAPPING, NOW).products.biggest_decliners

    assert [d.product for d in decliners] == ["Leak", "Slide"]
    assert [d.revenue_change for d in decliners] == [pytest.approx(-100.0), pytest.approx(-50.0)]
    assert decliners[0].revenue_change_pct is None and "negative" in decliners[0].revenue_change_pct_reason
    assert decliners[1].revenue_change_pct == pytest.approx(-50.0)


def test_metrics_json_is_the_current_major_version() -> None:
    # Was "2.0" (the 2E bump); 2E-c bumped it to "3.0" (Thach: orders,
    # buyers, AOV, new customers and RFM scores changed meaning); 2E-c2 to
    # "4.0" (return rate and new customers changed meaning again); 2E-e to
    # "5.0" (orders are order ids when order_id is mapped); 2E-f to "6.0"
    # (first-day netting per product, one order is F = 1, customer fill);
    # 2E-g to "7.0" (product units, labels, the gap, velocity); 2E-h to "8.0"
    # (wall-clock dates, undated lines counted).
    assert SCHEMA_VERSION == "8.0"
