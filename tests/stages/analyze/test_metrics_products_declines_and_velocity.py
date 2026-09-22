import pandas as pd
import pytest

from stages.analyze.metrics_products import compute_product_metrics
from tests.stages.analyze.products_fixtures import MAPPING, MAPPING_WITH_TYPE, frame, period_for

# --- biggest_decliners --------------------------------------------------


def _decliners_scenario() -> pd.DataFrame:
    return frame(
        [
            # X: previous 100 -> current 50 (change -50%)
            {"Date": "2019-12-15", "Qty": "10", "Price": "10.0", "Product": "X"},
            {"Date": "2020-01-15", "Qty": "5", "Price": "10.0", "Product": "X"},
            # Y: previous 100 -> current 0, entirely absent this period (change -100%)
            {"Date": "2019-12-16", "Qty": "20", "Price": "5.0", "Product": "Y"},
            # Z: new this period, no previous revenue -> not a decliner
            {"Date": "2020-01-20", "Qty": "10", "Price": "10.0", "Product": "Z"},
            # W: previous 50 -> current 60, growth -> not a decliner
            {"Date": "2019-12-17", "Qty": "5", "Price": "10.0", "Product": "W"},
            {"Date": "2020-01-18", "Qty": "6", "Price": "10.0", "Product": "W"},
            # anchor: fixes data_end at month-end without affecting any decline
            {"Date": "2020-01-31", "Qty": "1", "Price": "1.0", "Product": "Anchor"},
        ]
    )


def test_biggest_decliners_hand_calculated() -> None:
    df = _decliners_scenario()
    period = period_for(df)
    assert (period.current, period.previous) == ("2020-01", "2019-12")

    products = compute_product_metrics(df, MAPPING, period)

    assert [(d.product, d.revenue_change_pct) for d in products.biggest_decliners] == [
        ("Y", -100.0),
        ("X", -50.0),
    ]


def test_biggest_decliners_caps_at_ten() -> None:
    rows = []
    for i in range(1, 12):  # 11 products, each declining by a distinct i%
        rows.append({"Date": "2019-12-10", "Qty": "1", "Price": "100", "Product": f"D{i}"})
        rows.append({"Date": "2020-01-15", "Qty": "1", "Price": str(100 - i), "Product": f"D{i}"})
    rows.append({"Date": "2020-01-31", "Qty": "1", "Price": "1.0", "Product": "Anchor"})
    df = frame(rows)
    period = period_for(df)

    products = compute_product_metrics(df, MAPPING, period)

    assert len(products.biggest_decliners) == 10  # D1 (smallest decline, -1%) is cut off
    assert products.biggest_decliners[0].product == "D11"  # most negative (-11%) first
    assert products.biggest_decliners[0].revenue_change_pct == pytest.approx(-11.0)
    assert products.biggest_decliners[-1].product == "D2"  # least negative among the surviving 10
    assert products.biggest_decliners[-1].revenue_change_pct == pytest.approx(-2.0)


def test_no_previous_period_data_reports_no_decliners() -> None:
    df = frame(
        [{"Date": "2020-01-31", "Qty": "5", "Price": "10.0", "Product": "A"}]
    )  # every row is in the current period only
    period = period_for(df)

    products = compute_product_metrics(df, MAPPING, period)

    assert products.biggest_decliners == []


# --- velocity / stockout -----------------------------------------------


def _velocity_scenario() -> pd.DataFrame:
    return frame(
        [
            # V: restocked 100 (an "in" row) before the current period, sold 20 in
            # the previous period and 30 in the current period (also fixes
            # data_end at month-end: Jan 31 has 31 days).
            {"Date": "2019-11-01", "Qty": "100", "Price": "5.0", "Product": "V", "Type": "in"},
            {"Date": "2019-12-10", "Qty": "20", "Price": "5.0", "Product": "V", "Type": "out"},
            {"Date": "2020-01-31", "Qty": "30", "Price": "5.0", "Product": "V", "Type": "out"},
            # NeverSold: only ever restocked, never sold -> no current-period
            # units at all, excluded (answers the "only ever an 'in' row" case).
            {"Date": "2019-11-05", "Qty": "20", "Price": "5.0", "Product": "NeverSold", "Type": "in"},
            # ReturnHeavy: current period is a net return, no positive sale -> excluded.
            {"Date": "2020-01-12", "Qty": "-5", "Price": "5.0", "Product": "ReturnHeavy", "Type": "out"},
        ]
    )


def test_velocity_hand_calculated_and_excludes_non_positive_velocity_products() -> None:
    df = _velocity_scenario()
    period = period_for(df, MAPPING_WITH_TYPE)
    assert period.current == "2020-01"

    products = compute_product_metrics(df, MAPPING_WITH_TYPE, period)

    assert len(products.velocity) == 1  # NeverSold and ReturnHeavy both excluded
    v = products.velocity[0]
    assert v.product == "V"
    assert v.units_per_day == pytest.approx(30 / 31)  # 30 units sold in January (31 days)
    # implied stock: 100 in - (20 previous-period out + 30 current-period out) = 50
    assert v.days_to_stockout == pytest.approx(50 / (30 / 31))
