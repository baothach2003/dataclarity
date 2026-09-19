from typing import Any

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract


def diagnosis_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 7.
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-18T04:16:00Z",
        "model_used": "claude-sonnet-5",
        "decomposition": {
            "metric": "revenue",
            "change_abs": -140000.0,
            "change_pct": -10.9,
            "factors": [
                {"factor": "active_customers", "contribution_abs": -102300.0,
                 "contribution_pct": 73.1, "value_current": 812, "value_previous": 905},
                {"factor": "purchase_frequency", "contribution_abs": -21400.0,
                 "contribution_pct": 15.3, "value_current": 2.24, "value_previous": 2.15},
                {"factor": "aov", "contribution_abs": -16300.0, "contribution_pct": 11.6,
                 "value_current": 631.9, "value_previous": 661.5},
            ],
            "method": "multiplicative decomposition, sequential substitution",
        },
        "ai_findings": {
            "headline": "Revenue fell 10.9% driven mainly by customer count",
            "root_cause": {
                "driver": "loss of 93 active customers, concentrated in the At-risk segment",
                "evidence": "active_customers 905 -> 812; At-risk segment grew 129 -> 168",
                "secondary": ["AOV down 4.5% in Home Decor"],
            },
            "ruled_out": [
                {"hypothesis": "price increases drove customers away",
                 "evidence_against": "median unit_price unchanged at 8.5"}
            ],
        },
    }


def test_accepts_documented_example() -> None:
    diagnosis = DiagnosisContract.model_validate(diagnosis_payload())

    factors = diagnosis.decomposition.factors
    assert [f.factor for f in factors] == ["active_customers", "purchase_frequency", "aov"]
    assert factors[0].value_previous == 905
    assert diagnosis.ai_findings is not None
    assert diagnosis.ai_findings.root_cause.secondary == ["AOV down 4.5% in Home Decor"]


def test_rejects_missing_decomposition() -> None:
    payload = diagnosis_payload()
    del payload["decomposition"]

    with pytest.raises(ValidationError, match="decomposition"):
        DiagnosisContract.model_validate(payload)


def test_rejects_factor_missing_contribution_abs() -> None:
    payload = diagnosis_payload()
    del payload["decomposition"]["factors"][0]["contribution_abs"]

    with pytest.raises(ValidationError, match="contribution_abs"):
        DiagnosisContract.model_validate(payload)


def test_rejects_root_cause_missing_evidence() -> None:
    payload = diagnosis_payload()
    del payload["ai_findings"]["root_cause"]["evidence"]

    with pytest.raises(ValidationError, match="evidence"):
        DiagnosisContract.model_validate(payload)


def test_rejects_ruled_out_entry_missing_evidence_against() -> None:
    payload = diagnosis_payload()
    del payload["ai_findings"]["ruled_out"][0]["evidence_against"]

    with pytest.raises(ValidationError, match="evidence_against"):
        DiagnosisContract.model_validate(payload)


def test_rejects_secondary_that_is_not_a_list() -> None:
    payload = diagnosis_payload()
    payload["ai_findings"]["root_cause"]["secondary"] = "AOV down 4.5%"

    with pytest.raises(ValidationError, match="secondary"):
        DiagnosisContract.model_validate(payload)


# --- degraded mode (CONTRACTS.md section 7, AI_PIPELINE.md section 9) --------


def test_accepts_degraded_file_with_null_ai_blocks() -> None:
    payload = diagnosis_payload()
    payload.update({"model_used": None, "ai_findings": None})

    diagnosis = DiagnosisContract.model_validate(payload)

    assert diagnosis.ai_findings is None
    assert diagnosis.decomposition.change_abs == -140000.0


def test_rejects_missing_ai_findings_key() -> None:
    # A dropped key must not parse as a degraded run: null is a value.
    payload = diagnosis_payload()
    del payload["ai_findings"]

    with pytest.raises(ValidationError, match="ai_findings"):
        DiagnosisContract.model_validate(payload)


def test_rejects_findings_without_model_used() -> None:
    payload = diagnosis_payload()
    payload["model_used"] = None

    with pytest.raises(ValidationError, match="both null or both filled"):
        DiagnosisContract.model_validate(payload)


def test_rejects_model_used_without_findings() -> None:
    payload = diagnosis_payload()
    payload["ai_findings"] = None

    with pytest.raises(ValidationError, match="both null or both filled"):
        DiagnosisContract.model_validate(payload)
