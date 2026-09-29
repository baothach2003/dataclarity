"""Session 5A, review 1's cases for layer 3 and the file: too short a
history, the first forecast month, the confidence label, the models named,
files of other months, stage 1's AI answers absent or of another major.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from contracts.report import ReportContract
from stages.report.builder import ReportMismatchError, report_run
from stages.report.layers import confidence_label
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.stages.report.report_fixtures import NOW, RUN, build, metrics_data, run_dir

# --- the actions --------------------------------------------------------------------------------


def _insufficient() -> dict:
    forecast = forecast_payload()
    forecast["forecast"].update({"revenue": [], "horizon_periods": 0, "insufficient_history": True,
                                 "months_used": 2, "season_note": None})
    return forecast


def test_too_short_a_history_builds_a_report_with_no_forecast_chart() -> None:
    report = build(forecast=_insufficient())
    forecast = report.layer_3_actions.forecast
    assert (forecast.insufficient_history, forecast.months_used, forecast.points) == (True, 2, [])
    assert (forecast.first_month_in_file, forecast.partial_first_month_until) == (False, None)
    assert [c.id for c in report.charts] == ["revenue_trend"]


def test_a_month_grain_files_first_forecast_month_has_no_day() -> None:
    # Review 1 #11: a month-to-date line dated the 1st (or the month's last
    # day, 2E-o) says nothing of how far the month went.
    for end in ("2011-12-01", "2011-12-31"):
        metrics = metrics_data()
        metrics["period"] |= {"month_grain": True, "data_end": end}
        forecast = build(metrics=metrics).layer_3_actions.forecast
        assert (forecast.first_month_in_file, forecast.partial_first_month_until) == (True, None)


def test_a_forecast_after_the_files_last_month_starts_outside_it() -> None:
    # The file ends on 30 November: December is wholly a forecast.
    metrics = metrics_data(months=(("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0)))
    metrics["period"]["data_end"] = "2011-11-30"
    forecast = build(metrics=metrics).layer_3_actions.forecast
    assert (forecast.first_month_in_file, forecast.partial_first_month_until) == (False, None)


def test_a_day_grain_file_says_the_day_it_ends() -> None:
    forecast = build().layer_3_actions.forecast
    assert (forecast.first_month_in_file, forecast.partial_first_month_until) == (True, date(2011, 12, 9))


@pytest.mark.parametrize("confidence,label", [
    (1.0, "high"), (0.7, "high"), (0.69, "medium"), (0.4, "medium"), (0.39, "low"), (0.0, "low")])
def test_confidence_is_a_label(confidence: float, label: str) -> None:
    assert confidence_label(confidence) == label


def test_a_recommendation_shows_its_confidence_as_a_label_never_a_figure() -> None:
    # Review 1 #6: the fixture's 0.7 is "high"; no figure is carried.
    report = build()
    recommendations = report.layer_3_actions.recommendations
    assert recommendations is not None and [r.confidence_label for r in recommendations] == ["high"]
    dumped = json.loads(report.model_dump_json())["layer_3_actions"]["recommendations"][0]
    assert "confidence" not in dumped
    assert dumped["action"] == forecast_payload()["recommendations"][0]["action"]


def test_the_models_named_are_those_of_the_answers_shown() -> None:
    # Hidden recommendations name no model.
    forecast = forecast_payload() | {"model_used": "claude-haiku-4-5"}
    assert build(forecast=forecast).provenance.models_used == ["claude-haiku-4-5", "claude-sonnet-5"]
    assert build(forecast=forecast, include_recommendations=False).provenance.models_used == ["claude-sonnet-5"]
    assert build(forecast=forecast, schema=False, include_recommendations=False,
                 diagnosis=diagnosis_payload() | {"ai_findings": None, "model_used": None}).provenance.models_used == []


# --- the files agree ----------------------------------------------------------------------------


def test_a_diagnosis_of_other_months_is_refused() -> None:
    # Review 1 #8: another comparison's badge and headline beside these KPIs.
    diagnosis = diagnosis_payload()
    diagnosis["frame"] |= {"current": "2011-08", "previous": "2011-07"}
    with pytest.raises(ReportMismatchError, match="2011-08 against 2011-07"):
        build(diagnosis=diagnosis)


def test_a_forecast_of_other_months_is_refused() -> None:
    forecast = forecast_payload()
    for point, month in zip(forecast["forecast"]["revenue"], ("2012-01", "2012-02", "2012-03")):
        point["period"] = month
    with pytest.raises(ReportMismatchError, match="starts at 2012-01"):
        build(forecast=forecast)


# --- the file -----------------------------------------------------------------------------------


def test_report_run_without_stage_1s_ai_answers(tmp_path: Path) -> None:
    # Stage 1's AI gave no answer: only the narration and recommendations.
    run_dir(tmp_path, optional=False)
    report = report_run(tmp_path, RUN, source_file="sales_2011.csv", include_recommendations=True, now=NOW)
    assert (report.provenance.ai_calls, report.provenance.models_used) == (2, ["claude-sonnet-5"])


def test_report_run_reads_a_stage_1_answer_of_another_major_as_absent(tmp_path: Path) -> None:
    # Review 1 #15: they feed only the provenance.
    run = run_dir(tmp_path)
    for name in ("schema_inference.json", "plan_proposed.json"):
        raw = json.loads((run / name).read_text(encoding="utf-8"))
        (run / name).write_text(json.dumps(raw | {"schema_version": "0.9"}), encoding="utf-8")
    report = report_run(tmp_path, RUN, source_file="sales_2011.csv", include_recommendations=True, now=NOW)
    assert report.provenance.ai_calls == 2
    assert ReportContract.model_validate_json((run / "report.json").read_text(encoding="utf-8")) == report
