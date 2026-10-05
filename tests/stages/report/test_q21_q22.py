"""Thach's Q21 and Q22 (2026-10-05) in report.json 2.8 and report.html.

Q21: 3F is closed - stage 3 has no narration step in v1 - so report.json says
`narration_status` "not_in_v1" and the page prints no line for it:
"unavailable" reads as a failure, and the step was removed by design.
Q22: the front section prints the bridge's shown change (step 3); the exact
`core.revenue_change` goes to the appendix - the revenue KPI carries it, and
the KPI table (the appendix's, step 3) prints it beside the percentage."""

import pytest
from pydantic import ValidationError

from contracts.report import ReportContract
from stages.report.builder import SCHEMA_VERSION
from stages.report.html_report import render_html
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.report.report_fixtures import build, metrics_data


def _v1(metrics: dict | None = None):
    """A v1 run: stage 3 has no narration step (3F closed), so ai_findings and model_used are null."""
    diagnosis = diagnosis_payload() | {"ai_findings": None, "model_used": None}
    return build(metrics=metrics, diagnosis=diagnosis)


def _metrics_16_2() -> dict:
    # The example's November 1,150,000.00 against October's 1,290,000.00.
    data = metrics_data()
    data["schema_version"] = "16.2"
    data["core"]["revenue_change"] = data["core"]["revenue_current"] - data["core"]["revenue_previous"]
    data["core"]["revenue_change_reason"] = None
    return data


def test_the_version_is_2_8() -> None:
    assert SCHEMA_VERSION == "2.8"  # 2.8: narration_status "not_in_v1" (Q21), the revenue KPI's change (Q22)


def test_with_no_narration_step_the_status_says_not_in_v1() -> None:
    report = _v1()

    assert report.layer_2_causes.narration is None
    assert report.layer_2_causes.narration_status == "not_in_v1"


def test_the_page_prints_no_narration_line_for_a_step_v1_does_not_have() -> None:
    html = render_html(_v1())

    assert "narration is unavailable" not in html
    assert "The AI's reading" not in html


def test_a_report_whose_narration_failed_still_says_so() -> None:
    # A 2.7 report from before Q21: "unavailable" keeps its line.
    data = _v1().model_dump(mode="json")
    data["schema_version"] = "2.7"
    data["layer_2_causes"]["narration_status"] = "unavailable"
    data["layer_1_numbers"]["kpis"][0]["change"] = None

    html = render_html(ReportContract.model_validate(data))

    assert "The AI narration is unavailable for this report." in html


def test_a_report_before_2_8_cannot_say_not_in_v1() -> None:
    data = _v1().model_dump(mode="json")
    data["schema_version"] = "2.7"
    data["layer_1_numbers"]["kpis"][0]["change"] = None

    with pytest.raises(ValidationError, match="not_in_v1"):
        ReportContract.model_validate(data)


def test_the_revenue_kpi_carries_the_exact_change() -> None:
    report = _v1(_metrics_16_2())
    revenue = report.layer_1_numbers.kpis[0]

    assert (revenue.id, revenue.change) == ("revenue", -140_000.0)
    assert all(kpi.change is None for kpi in report.layer_1_numbers.kpis[1:])


def test_the_kpi_table_prints_the_change_beside_its_percentage() -> None:
    html = render_html(_v1(_metrics_16_2()))

    assert "-140,000.00 (-10.9%)" in html


def test_a_metrics_file_before_16_2_has_no_change_to_carry() -> None:
    # The example metrics.json is 16.0: no revenue_change, so the KPI carries none and prints the percentage.
    report = _v1()

    assert report.layer_1_numbers.kpis[0].change is None
    assert "-10.9%" in render_html(report)


def test_only_revenue_carries_a_change() -> None:
    data = _v1(_metrics_16_2()).model_dump(mode="json")
    data["layer_1_numbers"]["kpis"][1]["change"] = 35.0

    with pytest.raises(ValidationError, match="revenue's alone"):
        ReportContract.model_validate(data)
