"""2E-u3 (Thach, 2026-10-02; 2E-u F3), stage 5, written before the code: the
walk-in candidates left unanswered are marked "suggested, not confirmed"
wherever the customer figures they stay in are shown - beside the KPI table
and in the causes (CLAUDE.md 3.3a). report.json 2.2 carries the reason."""

from contracts.report import ReportContract
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import build, metrics_data

REASON = ('The file suggests "Guest" (3 lines, 2 in 2011-11) is a placeholder for walk-ins - suggested, not '
          "confirmed: its lines stay one customer's in every customer figure and cause. Confirm it in Review to "
          "count those lines with no customer.")


def _marked() -> dict:
    metrics = metrics_data()
    metrics["customers"]["unconfirmed_placeholders"] = [
        {"value": "Guest", "lines": 3, "lines_current": 2, "lines_previous": 1}]
    metrics["customers"]["unconfirmed_placeholders_reason"] = REASON
    return metrics


def test_report_json_carries_the_reason() -> None:
    assert build(_marked()).layer_1_numbers.unconfirmed_placeholders_reason == REASON
    assert build().layer_1_numbers.unconfirmed_placeholders_reason is None


def test_the_page_marks_it_beside_the_figures_and_in_the_causes() -> None:
    page = Page(render_html(build(_marked())))
    numbers = page.section("numbers")
    assert numbers.index("Active customers") < numbers.index(REASON)
    assert REASON in page.section("causes")


def test_nothing_is_marked_when_every_candidate_was_answered() -> None:
    page = Page(render_html(build()))
    assert "suggested, not confirmed" not in page.section("numbers") + page.section("causes")


def test_a_report_written_before_2eu3_still_reads() -> None:
    payload = build().model_dump(mode="json")
    del payload["layer_1_numbers"]["unconfirmed_placeholders_reason"]
    assert ReportContract.model_validate(payload).layer_1_numbers.unconfirmed_placeholders_reason is None
