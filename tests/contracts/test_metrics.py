from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract


def metrics_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 6 ("..." product names filled in).
    return {
        "schema_version": "8.0",  # 2E-c: sale; 2E-c2: return; 2E-e: orders by basis; 2E-f: customers; 2E-g: products; 2E-h: dates
        "generated_at": "2026-09-18T04:15:00Z",
        "period": {
            "current": "2011-11",
            "previous": "2011-10",
            "data_start": "2010-12-01",
            "data_end": "2011-12-09",
            "previous_complete": True,
            "previous_incomplete_reason": None,
        },
        "core": {
            "revenue_current": 1150000.0,
            "revenue_previous": 1290000.0,
            "revenue_change_pct": -10.9,
            "revenue_change_pct_reason": None,
            "orders_basis": "order_id",
            "orders_basis_reason": None,
            "orders_current": 1820,
            "orders_previous": 1950,
            "active_customers_current": 812,
            "active_customers_previous": 905,
            "buyers_current": 790,
            "buyers_previous": 884,
            "aov_current": 631.9,
            "aov_current_reason": None,
            "aov_previous": 661.5,
            "aov_previous_reason": None,
            "return_rate_current": 0.042,
            "return_rate_current_reason": None,
            "return_rate_previous": 0.038,
            "return_rate_previous_reason": None,
            "revenue_by_month": [{"period": "2011-01", "revenue": 690000.0}],
            "undated_lines": 0,  # 2E-h
            "undated_lines_reason": None,
        },
        "customers": {
            "rfm_reference_date": "2011-12-10",
            "segments": [
                {
                    "segment": "Champions",
                    "customers": 118,
                    "revenue_share_pct": 34.2,
                    "avg_monetary": 3320.5,
                    "customers_previous": 129,
                }
            ],
            "new_vs_returning": {
                "new_customers": 74,
                "returning_customers": 738,
                "new_revenue": 92000.0,
                "returning_revenue": 1058000.0,
            },
            "customers_previous_reason": None,
            "revenue_share_reason": None,
        },
        "products": {
            "pareto": {
                "products_for_80pct_revenue": 63,
                "total_products": 412,
                "concentration_pct": 15.3,
                "concentration_reason": None,
            },
            "top_products": [
                {
                    "product": "WHITE HANGING HEART T-LIGHT HOLDER",
                    "revenue": 38400.0,
                    "units": 5120,
                }
            ],
            "biggest_decliners": [
                {"product": "REGENCY CAKESTAND 3 TIER", "revenue_change": -2800.0,
                 "revenue_change_pct": -41.2, "revenue_change_pct_reason": None}
            ],
            "biggest_decliners_reason": None,
            "velocity": [
                {
                    "product": "JUMBO BAG RED RETROSPOT",
                    "units_per_day": 12.4,
                    "days_to_stockout": 8.6,
                    "days_to_stockout_reason": None,  # 2E-g
                }
            ],
            "velocity_reason": None,  # 2E-g
        },
        "by_dimension": {
            "country": [
                {
                    "name": "United Kingdom",
                    "revenue_current": 940000.0,
                    "revenue_previous": 1020000.0,
                    "contribution_pct": 57.1,
                }
            ],
            "category": [
                {
                    "name": "Home Decor",
                    "revenue_current": 210000.0,
                    "revenue_previous": 268000.0,
                    "contribution_pct": 41.4,
                }
            ],
            "contribution_reason": None,
        },
    }


def test_accepts_documented_example() -> None:
    metrics = MetricsContract.model_validate(metrics_payload())

    assert metrics.period.data_start == date(2010, 12, 1)
    assert metrics.core.revenue_change_pct == -10.9
    assert metrics.customers.segments[0].customers_previous == 129
    assert metrics.products.pareto.total_products == 412
    assert metrics.by_dimension.country[0].contribution_pct == 57.1


def test_accepts_negative_contribution_pct() -> None:
    # contribution_pct is a signed share of the total change (section 6).
    payload = metrics_payload()
    payload["by_dimension"]["category"][0]["contribution_pct"] = -12.5

    metrics = MetricsContract.model_validate(payload)

    assert metrics.by_dimension.category[0].contribution_pct == -12.5


def test_accepts_empty_lists() -> None:
    payload = metrics_payload()
    payload["core"]["revenue_by_month"] = []
    payload["customers"]["segments"] = []
    payload["products"].update(
        {"top_products": [], "biggest_decliners": [], "velocity": []}
    )
    payload["by_dimension"] = {"country": [], "category": [], "contribution_reason": None}

    metrics = MetricsContract.model_validate(payload)

    assert metrics.products.velocity == []


def test_rejects_missing_core_block() -> None:
    payload = metrics_payload()
    del payload["core"]

    with pytest.raises(ValidationError, match="core"):
        MetricsContract.model_validate(payload)


def test_rejects_missing_by_dimension_category() -> None:
    payload = metrics_payload()
    del payload["by_dimension"]["category"]

    with pytest.raises(ValidationError, match="category"):
        MetricsContract.model_validate(payload)


@pytest.mark.parametrize("period", ["2011-13", "2011-00", "2011-1", "2011/11", "Nov 2011"])
def test_rejects_malformed_period(period: str) -> None:
    payload = metrics_payload()
    payload["period"]["current"] = period

    with pytest.raises(ValidationError, match="current"):
        MetricsContract.model_validate(payload)


def test_rejects_malformed_month_in_revenue_by_month() -> None:
    payload = metrics_payload()
    payload["core"]["revenue_by_month"][0]["period"] = "2011-1"

    with pytest.raises(ValidationError, match="revenue_by_month"):
        MetricsContract.model_validate(payload)


def test_rejects_invalid_data_start_date() -> None:
    payload = metrics_payload()
    payload["period"]["data_start"] = "2010-02-30"

    with pytest.raises(ValidationError, match="data_start"):
        MetricsContract.model_validate(payload)


def test_rejects_negative_order_count() -> None:
    payload = metrics_payload()
    payload["core"]["orders_current"] = -1

    with pytest.raises(ValidationError, match="orders_current"):
        MetricsContract.model_validate(payload)


def test_rejects_concentration_pct_above_100() -> None:
    payload = metrics_payload()
    payload["products"]["pareto"]["concentration_pct"] = 101.0

    with pytest.raises(ValidationError, match="concentration_pct"):
        MetricsContract.model_validate(payload)


def test_rejects_negative_days_to_stockout() -> None:
    payload = metrics_payload()
    payload["products"]["velocity"][0]["days_to_stockout"] = -0.1

    with pytest.raises(ValidationError, match="days_to_stockout"):
        MetricsContract.model_validate(payload)


# Shared with test_metrics_reasons.py and the 2E test files.
REASON = "the previous month is incomplete"
