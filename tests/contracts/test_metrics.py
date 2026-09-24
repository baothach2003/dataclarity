from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract


def metrics_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 6 ("..." product names filled in).
    return {
        "schema_version": "2.0",
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
                }
            ],
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


# --- schema 2.0 (session 2E): a null says why, and an old file is refused --------

REASON = "the previous month is incomplete"


def _partial(payload: dict) -> dict:
    """The payload as stage 2 writes it for an incomplete previous month."""
    payload["period"].update(previous_complete=False, previous_incomplete_reason=REASON)
    payload["core"].update(revenue_change_pct=None, revenue_change_pct_reason=REASON)
    payload["products"].update(biggest_decliners=None, biggest_decliners_reason=REASON)
    for member in payload["by_dimension"]["country"] + payload["by_dimension"]["category"]:
        member["contribution_pct"] = None
    payload["by_dimension"]["contribution_reason"] = REASON
    for segment in payload["customers"]["segments"]:
        segment["customers_previous"] = None
    payload["customers"]["customers_previous_reason"] = REASON
    return payload


def test_accepts_an_incomplete_previous_month_with_every_reason() -> None:
    metrics = MetricsContract.model_validate(_partial(metrics_payload()))

    assert metrics.core.revenue_change_pct is None
    assert metrics.products.biggest_decliners is None


@pytest.mark.parametrize("block,field,value", [
    ("period", "previous_incomplete_reason", None),
    ("core", "revenue_change_pct_reason", None),
    ("products", "biggest_decliners_reason", None),
    ("by_dimension", "contribution_reason", None),
    ("customers", "customers_previous_reason", None),
])
def test_rejects_a_null_that_does_not_say_why(block, field, value) -> None:
    payload = _partial(metrics_payload())
    payload[block][field] = value

    with pytest.raises(ValidationError, match="reason"):
        MetricsContract.model_validate(payload)


@pytest.mark.parametrize("block,field", [
    ("period", "previous_incomplete_reason"),
    ("core", "revenue_change_pct_reason"),
    ("products", "biggest_decliners_reason"),
    ("by_dimension", "contribution_reason"),
    ("customers", "customers_previous_reason"),
])
def test_rejects_a_reason_beside_a_value(block, field) -> None:
    payload = metrics_payload()
    payload[block][field] = REASON

    with pytest.raises(ValidationError, match="reason"):
        MetricsContract.model_validate(payload)


def test_rejects_a_decliner_percentage_without_its_reason() -> None:
    payload = metrics_payload()
    payload["products"]["biggest_decliners"][0]["revenue_change_pct"] = None

    with pytest.raises(ValidationError, match="reason"):
        MetricsContract.model_validate(payload)


def test_refuses_a_1x_metrics_file_and_says_to_re_analyse() -> None:
    payload = metrics_payload()
    payload["schema_version"] = "1.0"

    with pytest.raises(ValidationError, match="re-analyse this run"):
        MetricsContract.model_validate(payload)


def test_rejects_a_list_comparison_null_for_only_some_members() -> None:
    """contribution_pct is one comparison: available for every member or none
    (mutation check, 2E)."""
    payload = metrics_payload()
    payload["by_dimension"]["category"][0]["contribution_pct"] = None
    payload["by_dimension"]["contribution_reason"] = REASON

    with pytest.raises(ValidationError, match="some members only"):
        MetricsContract.model_validate(payload)


@pytest.mark.parametrize("block,field", [
    ("core", "aov_current"), ("core", "aov_previous"),
    ("core", "return_rate_current"), ("core", "return_rate_previous"),
    ("products.pareto", "concentration_pct"),
])
def test_a_ratio_null_needs_its_reason_and_a_value_refuses_one(block, field) -> None:
    """Every ratio whose denominator can be zero follows the one pairing rule
    (2E, superseding 2A's 0.0) - mutation check Z8/Z9."""
    def target(payload: dict) -> dict:
        node = payload
        for key in block.split("."):
            node = node[key]
        return node

    null_without_reason = metrics_payload()
    target(null_without_reason)[field] = None
    with pytest.raises(ValidationError, match="reason"):
        MetricsContract.model_validate(null_without_reason)

    reason_beside_value = metrics_payload()
    target(reason_beside_value)[f"{field}_reason" if block == "core"
                                else "concentration_reason"] = REASON
    with pytest.raises(ValidationError, match="reason"):
        MetricsContract.model_validate(reason_beside_value)
