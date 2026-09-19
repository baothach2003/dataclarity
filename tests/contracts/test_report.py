from typing import Any

import pytest
from pydantic import ValidationError

from contracts.report import ReportContract


def report_payload() -> dict[str, Any]:
    # The example from docs/CONTRACTS.md section 9 ("..." run_id filled in).
    return {
        "schema_version": "1.0",
        "generated_at": "2026-09-18T04:18:00Z",
        "run_id": "3f0c9a1e-5b7d-4c2e-9a8b-1d2e3f4a5b6c",
        "source_file": "sales_2011.csv",
        "data_quality": {"rows_in": 152430, "rows_out": 151988,
                         "issues_fixed": 7, "warnings": 1},
        "layer_1_numbers": {"...": "selected fields from metrics.json"},
        "layer_2_causes": {"...": "selected fields from diagnosis.json"},
        "layer_3_actions": {"...": "recommendations from forecast.json"},
        "charts": [
            {"id": "revenue_trend", "type": "line", "title": "Revenue by month",
             "series": [{"name": "revenue", "x": ["2011-01"], "y": [690000.0]}]}
        ],
        "provenance": {"stages_run": ["ingest", "analyze", "diagnose", "predict"],
                       "ai_calls": 4, "models_used": ["claude-sonnet-5"]},
    }


def test_accepts_documented_example() -> None:
    report = ReportContract.model_validate(report_payload())

    assert report.data_quality.rows_in - report.data_quality.rows_out == 442
    assert report.charts[0].series[0].y == [690000.0]
    assert report.provenance.ai_calls == 4


def test_layers_keep_arbitrary_nested_content_until_5a() -> None:
    # The layer structure is defined in Phase 5A (CONTRACTS.md section 10).
    payload = report_payload()
    payload["layer_1_numbers"] = {"core": {"revenue_current": 1150000.0}}

    report = ReportContract.model_validate(payload)

    assert report.layer_1_numbers == {"core": {"revenue_current": 1150000.0}}


def test_accepts_degraded_run_with_no_ai_calls() -> None:
    payload = report_payload()
    payload["provenance"].update({"ai_calls": 0, "models_used": []})

    report = ReportContract.model_validate(payload)

    assert report.provenance.models_used == []


def test_rejects_missing_provenance() -> None:
    payload = report_payload()
    del payload["provenance"]

    with pytest.raises(ValidationError, match="provenance"):
        ReportContract.model_validate(payload)


def test_rejects_missing_layer_2_causes() -> None:
    payload = report_payload()
    del payload["layer_2_causes"]

    with pytest.raises(ValidationError, match="layer_2_causes"):
        ReportContract.model_validate(payload)


def test_rejects_layer_that_is_not_an_object() -> None:
    payload = report_payload()
    payload["layer_3_actions"] = ["win-back email"]

    with pytest.raises(ValidationError, match="layer_3_actions"):
        ReportContract.model_validate(payload)


def test_rejects_series_with_mismatched_x_and_y() -> None:
    payload = report_payload()
    payload["charts"][0]["series"][0]["x"] = ["2011-01", "2011-02"]

    with pytest.raises(ValidationError, match="same length"):
        ReportContract.model_validate(payload)


def test_rejects_negative_ai_calls() -> None:
    payload = report_payload()
    payload["provenance"]["ai_calls"] = -1

    with pytest.raises(ValidationError, match="ai_calls"):
        ReportContract.model_validate(payload)


def test_rejects_non_numeric_series_value() -> None:
    payload = report_payload()
    payload["charts"][0]["series"][0]["y"] = ["a lot"]

    with pytest.raises(ValidationError, match="y"):
        ReportContract.model_validate(payload)
