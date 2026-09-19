from collections.abc import Callable
from typing import Any

import pytest
from pydantic import BaseModel

import contracts
from tests.contracts import (
    test_cleaning,
    test_diagnosis,
    test_forecast,
    test_metrics,
    test_profile,
    test_report,
)

EXAMPLES: list[tuple[type[BaseModel], Callable[[], dict[str, Any]]]] = [
    (contracts.ProfileContract, test_profile.profile_payload),
    (contracts.SchemaInferenceContract, test_profile.inference_payload),
    (contracts.CleaningPlanContract, test_cleaning.plan_payload),
    (contracts.CleaningReportContract, test_cleaning.report_payload),
    (contracts.MetricsContract, test_metrics.metrics_payload),
    (contracts.DiagnosisContract, test_diagnosis.diagnosis_payload),
    (contracts.ForecastContract, test_forecast.forecast_payload),
    (contracts.ReportContract, test_report.report_payload),
]


def test_package_exports_one_model_per_contract_file() -> None:
    # CONTRACTS.md section 1: nine JSON files, and plan_proposed / plan_final
    # share one schema, so eight models.
    assert sorted(contracts.__all__) == sorted(model.__name__ for model, _ in EXAMPLES)


@pytest.mark.parametrize(
    ("model", "payload"), EXAMPLES, ids=[model.__name__ for model, _ in EXAMPLES]
)
def test_json_round_trip_is_lossless(
    model: type[BaseModel], payload: Callable[[], dict[str, Any]]
) -> None:
    # Stages exchange these as JSON files: what one stage writes, the next must
    # read back unchanged.
    original = model.model_validate(payload())

    reread = model.model_validate_json(original.model_dump_json())

    assert reread == original
