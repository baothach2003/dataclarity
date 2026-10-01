"""2E-u6 (Thach, 2026-10-02; 2E-u F6): the lines dated after the upload are
reported where the dates the file covers are shown - report.json 2.2 carries
the count and reason, the HTML report says it right after "The file covers".
Written before the code."""

from contracts.report import ReportContract
from stages.report.builder import SCHEMA_VERSION
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import build, metrics_data

REASON = ("1 line is dated after this file was uploaded - later than 2011-12-20 on any clock - the latest 2042-02-10, so it is "
          "left out of choosing the months compared and the dates the file covers; its revenue (10.00) stays "
          "in its own month, outside both compared months.")


def _after_upload(metrics: dict) -> dict:
    metrics["period"]["upload_cutoff"] = "2011-12-20"
    return metrics


def test_report_json_carries_the_count_and_the_reason() -> None:
    report = build(_after_upload(metrics_data(future_lines=1, future_revenue=10.0, future_lines_reason=REASON)))
    numbers = report.layer_1_numbers
    assert (numbers.future_lines, numbers.future_lines_reason) == (1, REASON)
    assert SCHEMA_VERSION == "2.2"


def test_the_page_says_it_beside_the_dates_the_file_covers() -> None:
    page = Page(render_html(build(_after_upload(metrics_data(future_lines=1, future_revenue=10.0,
                                                              future_lines_reason=REASON)))))
    numbers = page.section("numbers")
    covers = numbers.index("The file covers")
    # Right after it: before the trust badge and the figures.
    assert covers < numbers.index(REASON) < numbers.index("Data trust")


def test_nothing_is_said_when_no_line_is_after_the_upload() -> None:
    report = build()
    assert (report.layer_1_numbers.future_lines, report.layer_1_numbers.future_lines_reason) == (0, None)
    assert "uploaded" not in Page(render_html(report)).section("numbers")


def test_a_report_written_before_2eu6_still_reads() -> None:
    payload = build().model_dump(mode="json")
    payload["schema_version"] = "2.1"
    del payload["layer_1_numbers"]["future_lines"]
    del payload["layer_1_numbers"]["future_lines_reason"]
    assert ReportContract.model_validate(payload).layer_1_numbers.future_lines == 0


def test_the_months_end_at_the_upload() -> None:
    """A month after the upload is no gap to draw ("a closed month or missing
    data" for 2012-01 to 2042-01 would be false): the months shown end with
    the last date the period covers; the line's revenue is in the reason."""
    metrics = metrics_data((("2011-10", 1290000.0), ("2011-11", 1150000.0), ("2011-12", 300000.0),
                            ("2042-02", 10.0)), future_lines=1, future_revenue=10.0, future_lines_reason=REASON)
    metrics["period"]["upload_cutoff"] = "2011-12-20"
    months = [m.period for m in build(metrics).layer_1_numbers.revenue_by_month]
    assert months == ["2011-10", "2011-11", "2011-12"]


def test_a_file_without_an_upload_cutoff_keeps_every_month() -> None:
    metrics = metrics_data((("2011-11", 1150000.0), ("2012-01", 300000.0)))
    assert [m.period for m in build(metrics).layer_1_numbers.revenue_by_month] == ["2011-11", "2011-12", "2012-01"]


def test_a_file_dated_entirely_after_the_upload_says_so_where_it_withholds_the_month() -> None:
    metrics = metrics_data((("2042-01", 10.0), ("2042-02", 20.0)), future_lines=2, future_revenue=30.0,
                           future_lines_reason="2 lines are dated after the day this file was uploaded")
    metrics["period"]["upload_cutoff"] = "2011-12-20"
    kpi = build(metrics).layer_1_numbers.kpis[0]
    assert kpi.current is None
    assert kpi.current_reason == "every line counted in revenue is dated after the day this file was uploaded"


def test_a_typo_later_in_the_uploads_month_draws_no_empty_months() -> None:
    """2E-u6 review 1, #4: the data ends in 2023-06, the file was uploaded on
    2026-09-10 and one line is typed 2026-09-20 - cut at the upload's month,
    the list drew 2023-07 to 2026-08 as closed months or missing data."""
    metrics = metrics_data((("2023-05", 100.0), ("2023-06", 100.0), ("2026-09", 10.0)), future_lines=1,
                           future_revenue=10.0, future_lines_reason=REASON)
    metrics["period"].update({"current": "2023-06", "previous": "2023-05", "data_start": "2023-05-01",
                              "data_end": "2023-06-30", "upload_cutoff": "2026-09-10"})
    # The month list alone: the fixture's diagnosis compares other months.
    from contracts.metrics import MetricsContract
    from stages.report.layers import _months

    assert [m.period for m in _months(MetricsContract.model_validate(metrics))] == ["2023-05", "2023-06"]
