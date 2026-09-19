from typing import Any

import pytest
from pydantic import ValidationError

from contracts.forecast import ForecastContract


def forecast_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 8 ("..." product name filled in).
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-18T04:17:00Z",
        "model_used": "claude-sonnet-5",
        "forecast": {
            "method": "weighted moving average with monthly seasonality index",
            "horizon_periods": 3,
            "revenue": [
                {"period": "2011-12", "point": 1210000.0, "low": 1040000.0,
                 "high": 1380000.0, "confidence": 0.8}
            ],
            "insufficient_history": False,
            "products_at_stockout_risk": [
                {"product": "JUMBO BAG RED RETROSPOT", "days_to_stockout": 8.6,
                 "suggested_reorder_units": 420}
            ],
        },
        "recommendations": [
            {
                "priority": 1,
                "insight": "At-risk segment grew from 129 to 168 customers",
                "cause": "customer count is 73.1% of the revenue decline",
                "action": "win-back email to the 168 At-risk customers with a 14-day offer",
                "expected_impact": "168 x avg_monetary 890 x 15% reactivation = ~22,400",
                "how_to_measure": "reactivation rate and revenue from that cohort, 30 days",
                "confidence": 0.7,
            }
        ],
        "do_not_do": [
            {"tempting_action": "discount to Champions",
             "why_wrong_here": "Champions revenue share is stable at 34.2%"}
        ],
    }


def test_accepts_documented_example() -> None:
    contract = ForecastContract.model_validate(forecast_payload())

    assert contract.forecast.revenue[0].point == 1210000.0
    assert contract.forecast.products_at_stockout_risk[0].suggested_reorder_units == 420
    assert contract.recommendations is not None
    assert contract.recommendations[0].priority == 1


def test_accepts_insufficient_history_with_no_revenue_points() -> None:
    payload = forecast_payload()
    payload["forecast"].update({"insufficient_history": True, "revenue": []})

    contract = ForecastContract.model_validate(payload)

    assert contract.forecast.insufficient_history is True


def test_accepts_point_on_interval_bound() -> None:
    payload = forecast_payload()
    payload["forecast"]["revenue"][0].update({"low": 1210000.0, "high": 1210000.0})

    contract = ForecastContract.model_validate(payload)

    assert contract.forecast.revenue[0].low == contract.forecast.revenue[0].point


def test_rejects_missing_forecast_block() -> None:
    payload = forecast_payload()
    del payload["forecast"]

    with pytest.raises(ValidationError, match="forecast"):
        ForecastContract.model_validate(payload)


def test_rejects_point_outside_its_interval() -> None:
    payload = forecast_payload()
    payload["forecast"]["revenue"][0]["point"] = 1400000.0  # above high 1380000

    with pytest.raises(ValidationError, match="low <= point <= high"):
        ForecastContract.model_validate(payload)


def test_rejects_malformed_forecast_period() -> None:
    payload = forecast_payload()
    payload["forecast"]["revenue"][0]["period"] = "2011-12-01"

    with pytest.raises(ValidationError, match="period"):
        ForecastContract.model_validate(payload)


@pytest.mark.parametrize("confidence", [-0.1, 1.5])
def test_rejects_recommendation_confidence_outside_unit_interval(
    confidence: float,
) -> None:
    payload = forecast_payload()
    payload["recommendations"][0]["confidence"] = confidence

    with pytest.raises(ValidationError, match="confidence"):
        ForecastContract.model_validate(payload)


def test_rejects_priority_zero() -> None:
    payload = forecast_payload()
    payload["recommendations"][0]["priority"] = 0

    with pytest.raises(ValidationError, match="priority"):
        ForecastContract.model_validate(payload)


def test_rejects_recommendation_missing_expected_impact() -> None:
    payload = forecast_payload()
    del payload["recommendations"][0]["expected_impact"]

    with pytest.raises(ValidationError, match="expected_impact"):
        ForecastContract.model_validate(payload)


def test_rejects_negative_reorder_units() -> None:
    payload = forecast_payload()
    payload["forecast"]["products_at_stockout_risk"][0]["suggested_reorder_units"] = -5

    with pytest.raises(ValidationError, match="suggested_reorder_units"):
        ForecastContract.model_validate(payload)


# --- degraded mode (CONTRACTS.md section 8, AI_PIPELINE.md section 9) --------


def test_accepts_degraded_file_with_null_ai_blocks() -> None:
    payload = forecast_payload()
    payload.update({"model_used": None, "recommendations": None, "do_not_do": None})

    contract = ForecastContract.model_validate(payload)

    assert contract.recommendations is None
    assert contract.forecast.horizon_periods == 3


def test_rejects_missing_recommendations_key() -> None:
    # A dropped key must not parse as a degraded run: null is a value.
    payload = forecast_payload()
    del payload["recommendations"]

    with pytest.raises(ValidationError, match="recommendations"):
        ForecastContract.model_validate(payload)


@pytest.mark.parametrize("nulled", ["model_used", "recommendations", "do_not_do"])
def test_rejects_partially_null_ai_blocks(nulled: str) -> None:
    payload = forecast_payload()
    payload[nulled] = None

    with pytest.raises(ValidationError, match="all null or all filled"):
        ForecastContract.model_validate(payload)
