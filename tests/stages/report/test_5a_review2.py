"""Session 5A, review 2's cases: the charts carry the cautions and notes of
what they plot, the money outside revenue reaches the report, and every
field of a period and a signal row is carried as the file has it."""

import json
from datetime import date
from pathlib import Path

from stages.report.builder import report_run
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics_reasons import REASON, _partial
from tests.stages.report.report_fixtures import NOW, RUN, build, metrics_data, run_dir


def test_the_charts_carry_the_trust_cautions_of_the_months_they_plot() -> None:
    # Review 2 #2 (the standing rule): a cut-short month is plotted as it
    # stands, so D1's caution stands beside it; an ok check does not.
    message = diagnosis_payload()["trust"]["checks"][0]["message"]
    assert [c.cautions for c in build().charts] == [[message], [message]]
    diagnosis = diagnosis_payload()
    diagnosis["trust"]["checks"][0]["status"] = "ok"
    assert [c.cautions for c in build(diagnosis=diagnosis).charts] == [[], []]


def test_the_forecast_chart_carries_the_forecasts_own_notes() -> None:
    # Review 2 #8 (CONTRACTS 11): history_note and season_note beside it.
    forecast = forecast_payload()
    forecast["forecast"] |= {"history_note": "The history starts at 2011-07.", "season_note": "No season: a ramp.",
                             "season_years": None}
    chart = build(forecast=forecast).charts[1]
    assert (chart.id, chart.note) == ("forecast", "The history starts at 2011-07. No season: a ramp.")
    assert build().charts[1].note is None


def test_the_money_outside_revenue_reaches_the_report() -> None:
    # Review 2 #11: an adjustment is reported as a reconciling amount
    # (CONTRACTS 6) - the report carries where the money went.
    non_product = [{"line_class": "adjustment", "lines": 35, "amount": -38338.77, "amount_current": -1200.0,
                    "amount_previous": 0.0, "reason": "left out of revenue; reported as a reconciling amount"}]
    outside = [{"line_class": "cost", "scope": "file", "sign": None, "lines": 135, "amount": -140866.87,
                "lines_without_amount": 0}]
    numbers = build(metrics=metrics_data(non_product=non_product, outside_revenue=outside)).layer_1_numbers
    assert [(n.line_class, n.lines, n.amount, n.reason) for n in numbers.non_product] == [
        ("adjustment", 35, -38338.77, "left out of revenue; reported as a reconciling amount")]
    assert [(o.line_class, o.scope, o.lines, o.amount) for o in numbers.outside_revenue] == [
        ("cost", "file", 135, -140866.87)]


def test_the_period_is_carried_as_the_file_has_it() -> None:
    period = build(metrics=_partial(metrics_data())).layer_1_numbers.period
    assert (period.current, period.previous, period.data_start, period.data_end, period.previous_complete,
            period.previous_incomplete_reason) == (
        "2011-11", "2011-10", date(2010, 12, 1), date(2011, 12, 9), False, REASON)


def test_revenues_change_says_why_it_is_withheld_for_an_incomplete_month() -> None:
    revenue = build(metrics=_partial(metrics_data())).layer_1_numbers.kpis[0]
    assert (revenue.change_pct, revenue.change_reason, revenue.previous_reason) == (None, REASON, REASON)


def test_every_signal_keeps_its_mode_kind_and_rule() -> None:
    # Review 2 #10: a level row within, a year-over-year row above by rule 1.
    diagnosis = diagnosis_payload()
    diagnosis["signals"].append({"series": "aov", "mode": "yoy", "value_cur": 5.0, "center": 1.0, "lower": 0.0,
                                 "upper": 2.0, "signal": "above", "rule": 1, "limits_method": "median_moving_range"})
    signals = build(diagnosis=diagnosis).layer_2_causes.signals
    assert signals is not None
    assert [(s.series, s.mode, s.signal, s.rule) for s in signals] == [
        ("revenue", "level", "within", None), ("aov", "yoy", "above", 1)]


def test_report_run_reads_a_stage_1_answer_of_a_newer_major_as_absent(tmp_path: Path) -> None:
    # Review 2 #10: a newer major is another version's file too.
    run = run_dir(tmp_path)
    raw = json.loads((run / "schema_inference.json").read_text(encoding="utf-8"))
    (run / "schema_inference.json").write_text(json.dumps(raw | {"schema_version": "9.0"}), encoding="utf-8")
    report = report_run(tmp_path, RUN, source_file="sales_2011.csv", now=NOW)
    assert report.provenance.ai_calls == 2  # Q42: the free-text recommendations are never shown, nor counted
