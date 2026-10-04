"""Session 5B, review 1's cases: every free-text field escaped (a sweep, not
a list), numbers that show as zero show no sign, signals worded by their
rule and formatted by their unit, the forecast's own notes whenever it has
them, a withheld month's lines still shown, no empty chart, and every part
of the page the tests had not pinned."""

import copy
from typing import Any

from pydantic import ValidationError

from contracts.report import ReportContract
from stages.report.html_parts import change, evidence_value, money, ratio, share
from stages.report.html_report import render_html
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics import metrics_payload
from tests.contracts.test_metrics_reasons import _partial
from tests.stages.report.html_probe import Page
from tests.stages.report.report_fixtures import REVENUE_NOTE, SAME_DAY, build, cleaning_data, metrics_data

MARK = "<i>x</i>"


def _rich() -> dict[str, Any]:
    """A report with every block filled: the file's notes, lines in no
    figure, the classes given, a note stage 3 carries too, suggested
    classes, a narration and recommendations."""
    notes = metrics_payload()["core"]["notes"] + [SAME_DAY, REVENUE_NOTE]
    metrics = metrics_data(
        notes=notes, undated_lines=5, undated_lines_reason="5 lines carry no date",
        unmeasurable=[{"scope": "current", "reason": "no price", "lines": 4}],
        non_product=[{"line_class": "charge", "lines": 3, "amount": 30.0, "amount_current": 20.0,
                      "amount_previous": 10.0, "reason": "a charge the customer paid"}],
        outside_revenue=[{"line_class": "cost", "scope": "file", "sign": None, "lines": 2, "amount": -5.0,
                          "lines_without_amount": 0}])
    diagnosis = diagnosis_payload()
    diagnosis["notes"].append(SAME_DAY)
    diagnosis["localization"]["dimensions"].append({
        "name": "product", "members": [], "other": {"name": "Other", "rev_prev": 0.0, "rev_cur": 0.0, "delta": 0.0,
                                                     "share_of_change": 0.0},
        "new_members": ["POSTAGE"], "removed_members": []})
    diagnosis["suggested_classes"] = {"POSTAGE": "charge"}
    forecast = forecast_payload()
    forecast["forecast"] |= {"history_note": "The history starts at 2011-07.", "season_note": "No season: a ramp.",
                             "season_years": None}
    payload: dict[str, Any] = build(metrics=metrics, diagnosis=diagnosis, forecast=forecast,
                                    cleaning=cleaning_data()).model_dump(mode="json")
    return payload


def _paths(node: Any, path: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    if isinstance(node, dict):
        return [p for key, value in node.items() for p in _paths(value, (*path, key))]
    if isinstance(node, list):
        return [p for index, value in enumerate(node) for p in _paths(value, (*path, index))]
    return [path] if isinstance(node, str) else []


def _at(node: Any, path: tuple[Any, ...]) -> Any:
    for key in path[:-1]:
        node = node[key]
    return node


def test_every_free_text_field_the_contract_accepts_markup_in_is_escaped() -> None:
    # 5B review 1 #7: a sweep - every string leaf, and every free key (a
    # product, an evidence key), marked one at a time; kept when report.json
    # still validates (so the contract allows it), then one page rendered.
    payload, marked = _rich(), 0
    for path in _paths(payload):
        trial = copy.deepcopy(payload)
        _at(trial, path)[path[-1]] += MARK
        try:
            ReportContract.model_validate(trial)
        except ValidationError:
            continue
        payload, marked = trial, marked + 1
    for block in (payload["layer_2_causes"]["suggested_classes"], payload["layer_2_causes"]["hypotheses"][0]["evidence"]):
        for key in list(block):
            block[key + MARK] = block.pop(key)
    # 2.5: the evidence text words the evidence key by key, so its printed keys carry the mark too.
    first = payload["layer_2_causes"]["hypotheses"][0]
    first["evidence_text"] = [f"{key}: {line.split(': ', 1)[1]}" for key, line in zip(first["evidence"], first["evidence_text"])]
    html = render_html(ReportContract.model_validate(payload))
    page = Page(html)
    assert marked > 40
    assert "i" not in {name for name, _ in page.tags}
    assert len(page.scripts) == 3
    assert html.count("&lt;i&gt;x&lt;/i&gt;") > 40


def test_the_suggested_classes_claim_nothing_the_report_does_not_say() -> None:
    # 5B review 1 #1: "counted as sales" was the renderer's own, and false.
    causes = Page(render_html(ReportContract.model_validate(_rich()))).section("causes")
    assert "Classes suggested for these products that nobody confirmed in Review Product Suggested class POSTAGE " \
           "charge" in causes
    assert "counted as" not in causes


def test_a_signal_is_worded_by_the_rule_that_fired_and_formatted_by_its_unit() -> None:
    # 5B review 1 #2 and #9: rule 2 is a run on one side of the centre, its
    # value inside the limits; orders are counts, the return rate a ratio,
    # a year-over-year row a percent.
    diagnosis = diagnosis_payload()
    diagnosis["signals"] = [
        {"series": "revenue", "mode": "level", "value_cur": 1150000.0, "center": 1000000.0, "lower": 800000.0,
         "upper": 1200000.0, "signal": "above", "rule": 2, "limits_method": "median_moving_range"},
        {"series": "orders", "mode": "level", "value_cur": 1234.0, "center": 1000.5, "lower": 900.0, "upper": 1100.0,
         "signal": "above", "rule": 1, "limits_method": "median_moving_range"},
        {"series": "return_rate", "mode": "level", "value_cur": 0.0042, "center": 0.002, "lower": 0.001,
         "upper": 0.003, "signal": "above", "rule": 1, "limits_method": "median_moving_range"},
        {"series": "aov", "mode": "yoy", "value_cur": -3.25, "center": 2.0, "lower": -1.0, "upper": 5.0,
         "signal": "below", "rule": 1, "limits_method": "median_moving_range"},
        {"series": "frequency", "mode": "level", "value_cur": None, "center": None, "lower": None, "upper": None,
         "signal": "insufficient_history", "rule": None, "limits_method": "median_moving_range",
         "insufficient_reason": "too_few_points"}]
    causes = Page(render_html(build(diagnosis=diagnosis))).section("causes")
    for row in ("Revenue level 1,150,000.00 1,000,000.00 800,000.00 1,200,000.00 above the centre for a run of months",
                "Orders level 1,234.0 1,000.5 900.0 1,100.0 above the upper limit",
                "Return rate level 0.004 0.002 0.001 0.003 above the upper limit",
                "Average order value yoy -3.2% +2.0% -1.0% +5.0% below the lower limit",
                "Orders per customer level no chart: too few months"):
        assert row in causes


def test_numbers_that_show_as_zero_show_no_sign() -> None:
    # 5B review 1 #4: -0.0 in a file, or a small negative rounded away.
    assert [money(-0.004), ratio(-0.0004), share(-0.00113), change(-0.04), money(-0.0), change(0.0)] == [
        "0.00", "0.000", "0%", "0.0%", "0.00", "0.0%"]
    assert (money(-0.01), change(-0.05), change(0.06)) == ("-0.01", "-0.1%", "+0.1%")
    assert [evidence_value(v) for v in (-0.0, [-0.0, 0.017439447368361054], None, True, 1234, "CAFÉ CRÈME")] == [
        "0", "[0.0, 0.01744]", "none", "yes", "1,234", "CAFÉ CRÈME"]


def test_the_forecasts_own_notes_stand_beside_it_once_even_without_a_forecast() -> None:
    # 5B review 1 #3 and #12.
    forecast = forecast_payload()
    forecast["forecast"].update({"revenue": [], "horizon_periods": 0, "insufficient_history": True,
                                 "months_used": 1, "season_note": None, "season_years": None,
                                 "history_note": "The history starts at 2011-11: 2011-10 holds no revenue."})
    actions = Page(render_html(build(forecast=forecast))).section("actions")
    assert ("There is too little history for a forecast: 1 complete month, and 3 are needed. The history starts at "
            "2011-11: 2011-10 holds no revenue.") in actions
    page = Page(render_html(ReportContract.model_validate(_rich())))
    assert page.text.count("The history starts at 2011-07.") == 1 and page.text.count("No season: a ramp.") == 1
    # Beside the forecast chart, once (5B review 2 #4).
    actions = page.section("actions")
    assert actions.count("Read with: unconfirmed suggestions") == 1 and "Read the forecast with" not in actions


def test_a_withheld_current_month_still_shows_its_lines_and_says_why_its_amounts_are_not() -> None:
    # 5B review 1 #5: the reason points at rows the page must show.
    unmeasurable = [{"scope": "current", "reason": "no price", "lines": 37691}]
    non_product = [{"line_class": "charge", "lines": 762, "amount": 80594.09, "amount_current": 0.0,
                    "amount_previous": 11063.98, "reason": "a charge the customer paid"}]
    metrics = metrics_data(months=(("2011-09", 1000000.0), ("2011-10", 1290000.0), ("2011-12", 300000.0)),
                           unmeasurable=unmeasurable, non_product=non_product)
    numbers = Page(render_html(build(metrics=metrics))).section("numbers")
    assert "no line dated in 2011-11 can be measured - see the lines in no figure" in numbers
    assert "current no price 37,691" in numbers
    assert "charge 762 80,594.09 withheld, with the current month's figures 11,063.98" in numbers
    part = Page(render_html(build(metrics=_partial(metrics_data(non_product=non_product))))).section("numbers")
    assert "charge 762 80,594.09 0.00 not compared - see why above" in part


def test_no_empty_chart_and_no_empty_table() -> None:
    # 5B review 1 #11: a file whose only month is partial draws nothing.
    metrics = _partial(metrics_data(months=(("2011-11", 490614.86), ("2011-12", 170647.13))))
    metrics["period"]["data_start"] = "2011-11-10"
    page = Page(render_html(build(metrics=metrics)))
    assert "chart-revenue_trend" not in page.ids() and len(page.scripts) == 2
    assert "No month of the file is covered whole and holds revenue, so none is drawn." in page.section("numbers")
    assert page.section("numbers").count("Whole month") == 1


def test_every_part_of_the_numbers_is_on_the_page() -> None:
    # 5B review 1 #7: current_note, undated lines, the unmeasurable lines,
    # the classes given, the months table, a month's null reason, the notes
    # beside the chart, the file's quality, the generation time.
    rich = ReportContract.model_validate(_rich())
    page = Page(render_html(rich))
    numbers = page.section("numbers")
    for shown in ("5 lines carry no date", "current no price 4", "charge 3 30.00 20.00 10.00 a charge the customer paid",
                  "cost file 2 -5.00 0", "Revenue by month Month Revenue Whole month 2011-09 1,000,000.00 yes",
                  "Read with: unconfirmed suggestions", "Changes that did something: 2."):
        assert shown in page.text
    assert numbers.count("5 lines carry no date") == 1
    assert "generated 2026-09-29 00:00 UTC" in page.text
    gap = metrics_data(months=(("2011-08", 900000.0), ("2011-10", 1290000.0), ("2011-11", 1150000.0)))
    assert "2011-09 no line counted in revenue is dated in it" in Page(render_html(build(metrics=gap))).section(
        "numbers")
    starts = _partial(metrics_data(months=(("2011-11", 490614.86), ("2011-12", 170647.13))))
    starts["period"]["data_start"] = "2011-11-10"
    assert "The file starts on 2011-11-10, part-way through 2011-11" in Page(
        render_html(build(metrics=starts))).section("numbers")


def test_a_note_both_files_carry_is_anchored_once_and_linked_from_the_causes() -> None:
    page = Page(render_html(ReportContract.model_validate(_rich())))
    assert page.ids().count("note-same_day_cancellations") == 1
    assert "Notes on the diagnosis Read with: same day cancellations" in page.section("causes")


def test_a_month_grain_files_first_forecast_month_is_said_without_a_day() -> None:
    metrics = metrics_data()
    metrics["period"] |= {"month_grain": True, "data_end": "2011-12-01"}
    actions = Page(render_html(build(metrics=metrics))).section("actions")
    assert "The file already holds a line for 2011-12: its revenue so far is not compared with the forecast." in actions


def test_a_chart_month_with_anything_after_it_is_refused() -> None:
    report = build()
    report.charts[0].series[0].x[0] = "2011-09\n"
    try:
        render_html(report)
    except ValueError as refused:
        assert "months" in str(refused)
    else:
        raise AssertionError("a month followed by a newline reached Plotly")


def test_nested_evidence_keeps_its_text_as_written() -> None:
    # 5B review 1 #13: a product list, accents and all.
    assert evidence_value([{"product": "CAFÉ CRÈME", "share": 0.2}]) == '[{"product": "CAFÉ CRÈME", "share": 0.2}]'


def test_a_file_with_no_month_of_revenue_has_no_months_table() -> None:
    page = Page(render_html(build(metrics=metrics_data(months=()))))
    assert "Whole month" not in page.section("numbers")
