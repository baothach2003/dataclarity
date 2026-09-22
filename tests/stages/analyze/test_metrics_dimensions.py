from datetime import UTC, datetime

import pandas as pd
import pytest

from stages.analyze.metrics_core import compute_core_metrics
from stages.analyze.metrics_dimensions import compute_dimension_metrics

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

MAPPING = {
    "Date": "transaction_date",
    "Qty": "quantity",
    "Price": "unit_price",
    "Product": "product_name",
    "Cat": "category",
}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _dimension_scenario() -> pd.DataFrame:
    return frame(
        [
            # current period (2020-01): A=30, B=70 (B's row also fixes data_end at month-end)
            {"Date": "2020-01-10", "Qty": "3", "Price": "10.0", "Product": "X", "Cat": "A"},
            {"Date": "2020-01-31", "Qty": "7", "Price": "10.0", "Product": "Y", "Cat": "B"},
            # previous period (2019-12): A=50, B=50, plus 100 unattributed (blank category)
            {"Date": "2019-12-10", "Qty": "5", "Price": "10.0", "Product": "X", "Cat": "A"},
            {"Date": "2019-12-11", "Qty": "5", "Price": "10.0", "Product": "Y", "Cat": "B"},
            {"Date": "2019-12-12", "Qty": "10", "Price": "10.0", "Product": "Z", "Cat": ""},
        ]
    )


def test_dimension_metrics_hand_calculated() -> None:
    df = _dimension_scenario()
    period, core = compute_core_metrics(df, MAPPING, now=NOW)
    assert (period.current, period.previous) == ("2020-01", "2019-12")
    # current: 30 (A) + 70 (B) = 100; previous: 50 (A) + 50 (B) + 100 (unattributed) = 200
    assert (core.revenue_current, core.revenue_previous) == (100.0, 200.0)

    dims = compute_dimension_metrics(df, MAPPING, period, core)

    assert dims.country == []  # no canonical field carries country data, ever
    by_name = {c.name: c for c in dims.category}
    assert set(by_name) == {"A", "B"}  # the blank-category row is not a third member

    assert (by_name["A"].revenue_current, by_name["A"].revenue_previous) == (30.0, 50.0)
    # total_change = 100 - 200 = -100; A's change = 30 - 50 = -20 -> -20 / -100 * 100 = 20.0
    assert by_name["A"].contribution_pct == pytest.approx(20.0)

    assert (by_name["B"].revenue_current, by_name["B"].revenue_previous) == (70.0, 50.0)
    # B's change = 70 - 50 = +20 -> 20 / -100 * 100 = -20.0 (grew while the total declined)
    assert by_name["B"].contribution_pct == pytest.approx(-20.0)


def test_category_is_normalized_for_whitespace_and_case() -> None:
    df = frame(
        [
            {"Date": "2020-01-10", "Qty": "2", "Price": "10.0", "Product": "X", "Cat": "Home Decor"},
            {"Date": "2020-01-31", "Qty": "3", "Price": "10.0", "Product": "Y", "Cat": " home decor"},
        ]
    )
    period, core = compute_core_metrics(df, MAPPING, now=NOW)

    dims = compute_dimension_metrics(df, MAPPING, period, core)

    assert len(dims.category) == 1
    assert dims.category[0].name == "Home Decor"  # first-seen spelling
    assert dims.category[0].revenue_current == 50.0  # 20 + 30, grouped despite the formatting noise


def test_unmapped_category_reports_an_empty_list() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "category"}
    df = frame([{"Date": "2020-01-31", "Qty": "1", "Price": "10.0", "Product": "X"}])
    period, core = compute_core_metrics(df, mapping, now=NOW)

    dims = compute_dimension_metrics(df, mapping, period, core)

    assert dims.category == []
    assert dims.country == []


def test_zero_total_change_uses_the_zero_denominator_convention() -> None:
    df = frame(
        [
            {"Date": "2020-01-31", "Qty": "1", "Price": "10.0", "Product": "X", "Cat": "A"},
            {"Date": "2019-12-10", "Qty": "1", "Price": "10.0", "Product": "X", "Cat": "A"},
        ]
    )
    period, core = compute_core_metrics(df, MAPPING, now=NOW)
    assert core.revenue_current == core.revenue_previous  # both 10.0 -> total_change 0

    dims = compute_dimension_metrics(df, MAPPING, period, core)

    assert dims.category[0].contribution_pct == 0.0
