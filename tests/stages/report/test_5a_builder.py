"""Session 5A (ninth run): stage 5 assembles report.json - three layers
(numbers, causes, actions) selected from the earlier contract files, never
computed (CONTRACTS 9). Written before the code; every expected value is a
field of the hand-built files in report_fixtures.py. Review 1's cases:
test_5a_review.py.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from contracts.lines import NOTE_TEXTS
from contracts.report import ReportContract
from stages.report.builder import report_run
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics import metrics_payload
from tests.contracts.test_metrics_reasons import _partial
from tests.stages.report.report_fixtures import NOW, REVENUE_NOTE, RUN, SAME_DAY, build, run_dir
from tests.stages.report.report_fixtures import metrics_data as _metrics


# --- the numbers ------------------------------------------------------------------------------


def test_the_kpis_are_the_files_figures_side_by_side() -> None:
    kpis = {k.id: k for k in build().layer_1_numbers.kpis}
    assert [k for k in kpis] == ["revenue", "orders", "active_customers", "aov", "return_rate"]
    revenue = kpis["revenue"]
    assert (revenue.label, revenue.unit, revenue.current, revenue.previous, revenue.change_pct) == (
        "Revenue", "money", 1150000.0, 1290000.0, -10.9)
    assert (kpis["orders"].label, kpis["orders"].current, kpis["orders"].previous) == ("Orders", 1820, 1950)
    assert (kpis["aov"].label, kpis["aov"].current, kpis["aov"].previous) == ("Average order value", 631.9, 661.5)
    # A ratio, not a share: returns per sale have no ceiling (metrics.py).
    assert (kpis["return_rate"].unit, kpis["return_rate"].current) == ("ratio", 0.042)
    # No change is computed but revenue's (CONTRACTS 11).
    assert all(k.change_pct is None for k in kpis.values() if k.id != "revenue")


def test_an_incomplete_previous_month_is_never_shown_beside_the_current() -> None:
    # CONTRACTS 11: its values describe part of a month.
    kpis = build(metrics=_partial(_metrics())).layer_1_numbers.kpis
    assert all(k.previous is None and k.previous_reason == "the previous month is incomplete" for k in kpis)
    assert kpis[0].change_pct is None


def test_a_file_without_order_numbers_says_lines() -> None:
    # CONTRACTS 6: basis "lines" is shown as lines and average line value.
    metrics = _metrics(orders_basis="lines", orders_basis_reason="no column holds an order number")
    kpis = {k.id: k.label for k in build(metrics=metrics).layer_1_numbers.kpis}
    assert (kpis["orders"], kpis["aov"]) == ("Lines", "Average line value")


def test_the_months_say_which_are_complete() -> None:
    months = build().layer_1_numbers.revenue_by_month
    assert [(m.period, m.complete) for m in months] == [
        ("2011-09", True), ("2011-10", True), ("2011-11", True), ("2011-12", False)]


def test_a_month_after_the_current_one_is_never_complete() -> None:
    # A month-grain file (2E-j/2E-o) counts every month it holds as covered,
    # the month-to-date one after `period.current` included.
    metrics = _metrics()
    metrics["period"] |= {"month_grain": True, "data_end": "2011-12-01"}
    months = build(metrics=metrics).layer_1_numbers.revenue_by_month
    assert [(m.period, m.complete) for m in months][-2:] == [("2011-11", True), ("2011-12", False)]


def test_a_first_forecast_month_the_file_covers_whole_is_not_partial() -> None:
    metrics = _metrics()
    metrics["period"]["data_end"] = "2011-12-31"
    assert build(metrics=metrics).layer_3_actions.forecast.partial_first_month_until is None


def test_an_always_on_note_is_shown_once_and_a_files_note_beside_what_it_names() -> None:
    # Adjustment 1: discounts_in_prices is on every file - once, in "How to
    # read these figures" (both files carry it); same-day cancellations are
    # this file's, beside orders, AOV and the return rate - not revenue.
    metrics = _metrics(notes=metrics_payload()["core"]["notes"] + [SAME_DAY])
    numbers = build(metrics=metrics).layer_1_numbers
    assert [n.code for n in numbers.how_to_read] == ["discounts_in_prices"]
    assert [n.code for n in numbers.notes] == ["same_day_cancellations"]
    assert numbers.notes[0].text == NOTE_TEXTS["same_day_cancellations"]  # by code, never the file's "t"
    kpis = {k.id: k.notes for k in numbers.kpis}
    assert (kpis["orders"], kpis["aov"], kpis["return_rate"], kpis["revenue"]) == (
        ["same_day_cancellations"], ["same_day_cancellations"], ["same_day_cancellations"], [])


def test_the_trust_badge_stands_beside_the_numbers() -> None:
    trust = build().layer_1_numbers.trust
    assert (trust.verdict, trust.limitations) == ("caution", diagnosis_payload()["trust"]["limitations"])


# --- the causes -------------------------------------------------------------------------------


def test_the_causes_are_the_diagnosis_as_it_stands() -> None:
    causes = build().layer_2_causes
    diagnosis = diagnosis_payload()
    assert causes.headline.message == diagnosis["headline"]["message"]
    assert [h.id for h in causes.hypotheses] == [h["id"] for h in diagnosis["hypotheses"]]
    assert causes.narration is not None and causes.narration_status == "shown"


def test_a_diagnosis_with_no_narration_says_v1_has_none() -> None:
    # Thach, Q21 (report.json 2.8): 3F is closed, so a null narration is "not_in_v1" - nothing failed.
    # "unavailable" (AI_PIPELINE 9) stays for a report from before (test_q21_q22).
    diagnosis = diagnosis_payload()
    diagnosis.update({"ai_findings": None, "model_used": None})
    causes = build(diagnosis=diagnosis).layer_2_causes
    assert (causes.narration, causes.narration_status) == (None, "not_in_v1")


# --- the actions ------------------------------------------------------------------------------


def test_the_forecast_and_the_partial_month_it_starts_in() -> None:
    # The file ends on 9 December 2011 and the first forecast month is
    # December 2011: that month is partly in the file.
    forecast = build().layer_3_actions.forecast
    assert [p.period for p in forecast.points] == ["2011-12", "2012-01", "2012-02"]
    assert (forecast.months_used, forecast.partial_first_month_until) == (36, date(2011, 12, 9))


def test_the_recommendations_are_never_shown() -> None:
    # Thach, Q42: the free-text recommendations - the unchecked format v1
    # switched off because it fabricated numbers - are never shown, even with
    # the file holding them; and no AI writes any in v1 (Q50 (d), Q53).
    held = build().layer_3_actions
    assert (held.recommendations_status, held.recommendations, held.do_not_do) == ("switched_off", None, None)
    forecast = forecast_payload()
    forecast.update({"model_used": None, "recommendations": None, "do_not_do": None})
    empty = build(forecast=forecast).layer_3_actions
    assert (empty.recommendations_status, empty.recommendations) == ("switched_off", None)


def test_the_notes_stand_beside_the_forecast_and_the_recommendations() -> None:
    # CONTRACTS 11: beside the forecast the notes naming revenue; beside the
    # recommendations every note that is not always-on.
    metrics = _metrics(notes=metrics_payload()["core"]["notes"] + [REVENUE_NOTE])
    diagnosis = diagnosis_payload()
    diagnosis["notes"].append(SAME_DAY)  # stage 3's own: beside the recommendations too
    actions = build(metrics=metrics, diagnosis=diagnosis).layer_3_actions
    assert actions.forecast.notes == ["unconfirmed_suggestions"]
    assert sorted(actions.notes) == ["same_day_cancellations", "unconfirmed_suggestions"]


# --- the charts, the provenance, the file's quality ---------------------------------------------


def test_the_charts_are_the_complete_months_and_the_forecast() -> None:
    charts = {c.id: c for c in build().charts}
    trend = charts["revenue_trend"].series[0]
    assert (trend.x, trend.y) == (["2011-09", "2011-10", "2011-11"], [1000000.0, 1290000.0, 1150000.0])
    forecast = {s.name: s for s in charts["forecast"].series}
    assert forecast["point"].x == ["2011-12", "2012-01", "2012-02"]
    assert forecast["low"].y == [p["low"] for p in forecast_payload()["forecast"]["revenue"]]


def test_the_provenance_counts_the_ai_answers_the_files_hold() -> None:
    # A schema inference, an AI-proposed plan, a narration, recommendations.
    provenance = build().provenance
    assert (provenance.stages_run, provenance.ai_calls, provenance.models_used) == (
        ["ingest", "analyze", "diagnose", "predict"], 3, ["claude-sonnet-5"])  # Q42: the free-text recommendations are never shown, nor counted
    assert build(schema=False, plan_source=None).provenance.ai_calls == 1


def test_the_files_quality_is_the_cleaning_reports() -> None:
    # 152,430 rows in, 151,988 out; two changes, one filling 6,402 cells and
    # one dropping 430 rows - both fixed something (review 1 #3: a fill
    # touches cells, not rows); one warning.
    quality = build().data_quality
    assert (quality.rows_in, quality.rows_out, quality.issues_fixed, quality.warnings) == (152430, 151988, 2, 1)


# --- the file ----------------------------------------------------------------------------------


def test_report_run_writes_report_json_and_a_failed_write_leaves_the_old_one(tmp_path: Path) -> None:
    run = run_dir(tmp_path)
    report = report_run(tmp_path, RUN, source_file="sales_2011.csv", now=NOW)
    assert ReportContract.model_validate(json.loads((run / "report.json").read_text(encoding="utf-8"))) == report
    assert report.provenance.ai_calls == 3  # Q42: the free-text recommendations are never shown, nor counted
    before = (run / "report.json").read_bytes()

    class Refused(Exception):
        pass

    def refuse() -> None:
        raise Refused

    with pytest.raises(Refused):
        report_run(tmp_path, RUN, source_file="x.csv", now=NOW, around_write=refuse)
    assert (run / "report.json").read_bytes() == before
