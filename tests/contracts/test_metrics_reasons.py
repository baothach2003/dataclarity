"""metrics.json 2.0's null-with-reason rules (docs/CONTRACTS.md section 6,
session 2E), split from test_metrics.py in 2E-b for file size - tests moved
unchanged."""

import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from tests.contracts.test_metrics import REASON, metrics_payload


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
