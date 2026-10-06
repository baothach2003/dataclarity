from typing import Any

import pytest
from pydantic import ValidationError

from contracts.report import ReportContract


def report_payload() -> dict[str, Any]:
    """A report.json as stage 5 builds it from the example contract files
    (session 5A defined the layers; tests/stages/report builds them)."""
    from tests.stages.report.report_fixtures import build

    payload: dict[str, Any] = build().model_dump(mode="json")
    return payload


def test_accepts_a_report_as_stage_5_builds_it() -> None:
    report = ReportContract.model_validate(report_payload())

    assert report.data_quality.rows_in - report.data_quality.rows_out == 442
    assert report.charts[0].series[0].y == [1000000.0, 1290000.0, 1150000.0]
    assert report.provenance.ai_calls == 3  # Q42: the free-text recommendations are never shown, nor counted


def test_the_layers_are_typed_since_5a() -> None:
    # Until 5A they held any nested content (CONTRACTS section 10).
    payload = report_payload()
    payload["layer_1_numbers"] = {"core": {"revenue_current": 1150000.0}}

    with pytest.raises(ValidationError, match="layer_1_numbers"):
        ReportContract.model_validate(payload)


def test_a_narration_and_its_status_agree() -> None:
    payload = report_payload()
    payload["layer_2_causes"]["narration_status"] = "unavailable"

    with pytest.raises(ValidationError, match="narration_status"):
        ReportContract.model_validate(payload)


@pytest.mark.parametrize("status", ["switched_off", "unavailable"])
def test_recommendations_are_shown_exactly_when_their_status_says_so(status: str) -> None:
    # Stage 5 never shows them (Q42); the contract's rule holds for any writer.
    payload = report_payload()
    payload["layer_3_actions"] |= {"recommendations_status": status, "do_not_do": [], "recommendations": [{
        "priority": 1, "insight": "i", "cause": "c", "action": "a", "expected_impact": "e", "how_to_measure": "h",
        "confidence_label": "high"}]}

    with pytest.raises(ValidationError, match="shown together"):
        ReportContract.model_validate(payload)


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


# --- the rules the builder follows, held by the file (5A review 1 #14) --------------------------


def _numbers_rejected(payload: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        ReportContract.model_validate(payload)


def test_rejects_a_comparison_with_an_incomplete_previous_month() -> None:
    payload = report_payload()
    numbers = payload["layer_1_numbers"]
    numbers["period"].update(previous_complete=False, previous_incomplete_reason="the previous month is incomplete")
    numbers["revenue_by_month"][1]["complete"] = False
    _numbers_rejected(payload, "compared with an incomplete previous month")


def test_rejects_a_change_on_any_kpi_but_revenue() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["kpis"][1]["change_pct"] = -6.7
    _numbers_rejected(payload, "only revenue's is carried")


def test_rejects_a_month_after_the_current_one_marked_complete() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["revenue_by_month"][-1]["complete"] = True
    _numbers_rejected(payload, "after the current month")


def test_rejects_a_previous_month_drawn_whole_that_the_kpis_do_not_compare() -> None:
    from tests.contracts.test_metrics_reasons import _partial
    from tests.stages.report.report_fixtures import build, metrics_data

    payload: dict[str, Any] = build(metrics=_partial(metrics_data())).model_dump(mode="json")
    payload["layer_1_numbers"]["revenue_by_month"][1]["complete"] = True
    _numbers_rejected(payload, "drawn whole only when the KPIs compare with it")


def test_rejects_a_files_note_in_how_to_read_and_an_always_on_note_beside_a_figure() -> None:
    from tests.contracts.test_metrics import metrics_payload
    from tests.stages.report.report_fixtures import SAME_DAY, build, metrics_data

    def with_both() -> dict[str, Any]:
        metrics = metrics_data(notes=metrics_payload()["core"]["notes"] + [SAME_DAY])
        payload: dict[str, Any] = build(metrics=metrics).model_dump(mode="json")
        return payload

    payload = with_both()
    numbers = payload["layer_1_numbers"]
    assert [n["code"] for n in numbers["how_to_read"]] == ["discounts_in_prices"]
    numbers["how_to_read"].append(numbers["notes"][0])
    _numbers_rejected(payload, "shown once, in how_to_read")
    payload = with_both()
    payload["layer_1_numbers"]["notes"].append(payload["layer_1_numbers"]["how_to_read"][0])
    _numbers_rejected(payload, "shown once, in how_to_read")
    payload = with_both()
    payload["layer_2_causes"]["notes"] = payload["layer_1_numbers"]["how_to_read"]
    _numbers_rejected(payload, "shown once, in how_to_read")


def test_rejects_a_month_with_no_revenue_and_no_reason() -> None:
    payload = report_payload()
    payload["layer_1_numbers"]["revenue_by_month"][0]["revenue"] = None
    _numbers_rejected(payload, "null exactly when its reason says why")


def test_rejects_a_day_for_a_forecast_month_the_file_does_not_hold() -> None:
    payload = report_payload()
    payload["layer_3_actions"]["forecast"]["first_month_in_file"] = False
    _numbers_rejected(payload, "the day the file ends in the first forecast month")
