"""Step 3's review, fixed (Thach's answers Q33-Q38, 2026-10-05, and the
review's other findings) - written before the fixes, each failing on the
reviewed code. docs/REPORT_REDESIGN.md section 12, step 3."""

import copy
import re

from contracts.report_front import FRONT_BANNED
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import build_real, files, with_actions

NOT_AVAILABLE = ("Suggested actions are not available for this report: its forecast was made before they existed - "
                 "run the forecast again to see them.")


def _front(run: str = "kaggle", **replaced):
    return build_real(run, **replaced).front


def _lines(front, kind: str) -> list[str]:
    return next(group.lines for group in front.checklist if group.kind == kind)


def _diagnosis(run: str = "kaggle"):
    return copy.deepcopy(files(run)["diagnosis.json"])


def _headline(diagnosis, **changes):
    diagnosis["schema_version"] = "18.6"
    diagnosis["headline"] |= changes
    return diagnosis


def _banned(text: str) -> list[str]:
    text = " " + text.lower()
    return [w for w in FRONT_BANNED if re.search(rf"(?<![a-z]){re.escape(w)}(?:s|es)?(?![a-z])", text)]


# --- Q34: the words match the field's unit -----------------------------------------------------------------


def test_returning_customers_and_refunds_are_worded_as_money() -> None:
    moved = _lines(_front("demo_classed"), "moved")

    assert "Sales from customers who came back after a break rose: 191,810.45, up from 155,065.58." in moved
    assert "Refunds for returned goods fell: 13,951.29, down from 41,074.29 (a small part)." in moved
    assert not any(line.startswith(("More customers came back", "Fewer returns")) for line in moved)


def test_customers_ordering_more_often_reads_orders_per_customer() -> None:
    # Orders up, but each customer ordering less often: "less often", as the bar says.
    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract
    from shared.claim_lines import Context, match_phrase, moved_line

    data = files("kaggle")
    metrics = MetricsContract.model_validate(data["metrics.json"])
    diagnosis = DiagnosisContract.model_validate(data["diagnosis.json"])
    bridge = diagnosis.tree.lever.bridge
    bars = [bar.model_copy(update={"value_prev": 13.72, "value_cur": 12.32}) if bar.factor == "frequency" else bar
            for bar in bridge.bars]
    ctx = Context(metrics=metrics, tree=diagnosis.tree, bridge=bridge.model_copy(update={"bars": bars}),
                  year_ago=diagnosis.year_ago, code=None)
    b1 = next(h for h in diagnosis.hypotheses if h.id == "B1")

    assert match_phrase(b1, ctx).startswith("customers ordering less often: 25 customers placed an order")
    assert moved_line(b1, ctx).startswith("Customers ordered less often: 343 orders, up from 308")


# --- Q33: sentence C from headline.named ---------------------------------------------------------------------


def test_rule_5_names_the_calendar_from_named() -> None:
    diagnosis = _headline(_diagnosis(), rule=5, hypothesis_id=None, lens=None, named=["T1"])

    assert _front(diagnosis=diagnosis).summary[2] == (
        "The figures match the calendar: December's length and mix of weekdays - worth about +1,274.15.")


def test_rule_5_naming_two_contexts_names_both() -> None:
    diagnosis = _headline(_diagnosis(), rule=5, hypothesis_id=None, lens=None, named=["T1", "T2"])

    assert _front(diagnosis=diagnosis).summary[2] == (
        "The figures match the calendar: December's length and mix of weekdays - worth about +1,274.15; and "
        "equally the same months a year earlier: last year sales also rose between November and December "
        "(34,900.00 to 41,046.00).")


def test_the_offsetting_case_names_its_movements_each_way() -> None:
    diagnosis = _headline(_diagnosis(), rule=6, hypothesis_id=None, lens=None, named=["B1", "P2"])
    diagnosis["schema_version"] = "18.7"  # stage 3 marks the case (Q40); the reader never infers it
    diagnosis["headline"]["offsetting"] = True

    assert _front(diagnosis=diagnosis).summary[2] == (
        "The change is what is left of movements in opposite directions, among them: customers ordering more "
        "often - worth about +4,712.29; customers choosing cheaper products among those sold in both months: "
        "measured product by product, about -1,479.65 - a different measure from the chart, not an amount to add to "
        "it.")  # Q20's caveat wherever P1/P2's amount is printed


def test_a_named_cause_reads_as_a_phrase_never_a_line_lowercased() -> None:
    diagnosis = _headline(_diagnosis(), rule=6, hypothesis_id="P2", lens="product", named=["P2"])

    assert _front(diagnosis=diagnosis).summary[2] == (
        "The figures match customers choosing cheaper products among those sold in both months: measured product "
        "by product, about -1,479.65 - a different measure from the chart, not an amount to add to it.")  # Q20


# --- Q35: a note beside every figure it names ------------------------------------------------------------------


def test_each_section_links_the_notes_naming_its_figures() -> None:
    notes = _front("demo_classed").notes

    # Sentences B and C read the diagnosis, which same_day_cancellations names (the review).
    assert set(notes.summary) == {"same_day_cancellations", "unconfirmed_suggestions"}
    assert set(notes.change) == {"same_day_cancellations", "unconfirmed_suggestions"}
    assert set(notes.checked) == {"same_day_cancellations", "unconfirmed_suggestions"}
    assert notes.next_month == ["unconfirmed_suggestions"]
    page = Page(render_html(build_real("demo_classed")))
    for section in ("summary", "change", "checked", "next-month"):
        assert "unconfirmed suggestions" in page.section(section), section


# --- Q36, the actions guard -----------------------------------------------------------------------------------


def test_a_forecast_from_before_the_actions_is_not_available() -> None:
    from contracts.cleaning import CleaningReportContract
    from contracts.diagnosis import DiagnosisContract
    from contracts.forecast import ForecastContract
    from contracts.metrics import MetricsContract
    from stages.report.builder import build_report

    data = files("kaggle")
    report = build_report(run_id="r", source_file="f.csv", metrics=MetricsContract.model_validate(data["metrics.json"]),
                          diagnosis=DiagnosisContract.model_validate(data["diagnosis.json"]),
                          forecast=ForecastContract.model_validate(data["forecast.json"]),
                          cleaning=CleaningReportContract.model_validate(data["cleaning_report.json"]),
                          schema=None, plan_source=None)

    assert (report.front.next_steps.status, report.front.next_steps.sentence) == ("unavailable", NOT_AVAILABLE)


def test_actions_listed_where_no_cause_is_named_are_not_shown() -> None:
    action = {"claim": "K1", "hypothesis_id": "B1", "fact": "f", "action": "Keep going.", "why": "It worked.",
              "watch": "w"}
    steps = _front("demo_classed", forecast=with_actions("demo_classed", "list", [action])).next_steps

    assert (steps.items, steps.sentence) == (
        [], "Suggested actions are not available for this report: run the forecast again.")


def test_no_action_under_rule_2_says_why_without_contradicting_it() -> None:
    diagnosis = _diagnosis()
    diagnosis["headline"] |= {"rule": 2, "hypothesis_id": None, "lens": None, "message": "m", "named": None}
    steps = _front(diagnosis=diagnosis, forecast=with_actions("kaggle", "list", [])).next_steps

    assert steps.sentence == ("No action is suggested: the change matches days with no sales, a matter of the data "
                              "rather than of the shop. Next month, compare sales with the estimate in section 5.")


# --- Q37: the checks in plain words ------------------------------------------------------------------------------


def test_a_caution_is_worded_by_its_check_and_status() -> None:
    diagnosis = _diagnosis()
    diagnosis["schema_version"] = "18.7"  # the month the check is about (Q39)
    diagnosis["headline"]["offsetting"] = False
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][0] |= {"status": "caution", "month": "current",
                                        "message": "unlike its normal closing pattern; worth roughly 7,532 in revenue"}
    report = build_real("kaggle", diagnosis=diagnosis)

    assert report.front.caution == [  # the opener left the front (safety valve)
        "Some days in December 2024 have no sales at all - missing data, or days the shop was closed (the file "
        "cannot tell which)."]
    page = Page(render_html(report))
    assert _banned(page.front_text) == [] and "normal closing pattern" in page.text


def test_a_blocked_run_says_which_check_in_plain_words_and_draws_no_chart() -> None:
    from tests.contracts.test_diagnosis import diagnosis_payload
    from tests.stages.report.report_fixtures import build

    diagnosis = diagnosis_payload()
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis["trust"]["checks"][0] |= {"status": "blocked", "message": "revenue unlike its normal pattern"}
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None, "message": "m"}
    report = build(diagnosis=diagnosis)

    # A file before 18.7 names no month: the front says less (Q39).
    assert report.front.summary == ["The data cannot support conclusions: the data checks did not pass - see "
                                    "Technical details for which, and why."]
    page = Page(render_html(report))
    assert 'class="sales"' not in render_html(report) and _banned(page.front_text) == []


def test_a_month_not_compared_is_said_in_plain_words() -> None:
    from tests.contracts.test_metrics_reasons import _partial
    from tests.stages.report.report_fixtures import build, metrics_data

    front = build(metrics=_partial(metrics_data())).front

    assert front.summary[1] == "They are not compared with October 2011: the file does not cover October 2011 whole."
    assert _banned(" ".join(front.summary)) == []


# --- Q38: a season of several years -------------------------------------------------------------------------------


def _season(years: int, band: str = "consistent", singled_out: bool = True, difference: float = 0.08,
            typical: float = 13.13) -> dict:
    diagnosis = _diagnosis("demo_classed")
    season = diagnosis["headline"]["movement"]["season"]
    season |= {"years": years, "band": band, "difference_pct": difference, "typical_pct": typical}
    diagnosis["headline"]["movement"]["singled_out"] = singled_out
    return diagnosis


def test_a_season_of_several_years_is_said_without_the_word_median() -> None:
    front = _front("demo_classed", diagnosis=_season(3))

    assert front.summary[0] == ("This change is in line with earlier years: in the 3 earlier years, sales typically "
                                "rose 27.1% between these months; this year they rose 27.2% - a gap of 0.1 points, "
                                "within twice this shop's typical gap (13.1 points).")  # Q57
    assert "median" not in " ".join(front.summary).lower()


# --- the review's other findings ----------------------------------------------------------------------------------


def test_a_shortfall_inside_the_size_test_opens_with_b() -> None:
    diagnosis = _season(1, band="shortfall", singled_out=False, difference=-60.0, typical=13.13)
    diagnosis["headline"]["rule"] = 7
    summary = _front("demo_classed", diagnosis=diagnosis).summary

    assert summary[0].startswith("This change differs from last year's")


def _sized(change: float, typical: float, singled_out: bool) -> tuple[dict, dict]:
    data = files("kaggle")
    metrics, diagnosis = copy.deepcopy(data["metrics.json"]), _diagnosis()
    diagnosis["headline"]["movement"] |= {"change_pct": change, "typical_pct": typical, "singled_out": singled_out}
    metrics["core"]["revenue_change_pct"] = change
    return metrics, diagnosis


def test_the_decimals_never_contradict_the_comparison() -> None:
    metrics, diagnosis = _sized(10.04, 5.03, False)
    diagnosis["headline"] |= {"rule": 7, "hypothesis_id": None, "lens": None, "named": None}
    summary = _front(metrics=metrics, diagnosis=diagnosis).summary

    assert "(+10.04%)" in " ".join(summary)
    assert "That is less than twice this shop's typical month-to-month change (about 5.03%)." in summary


def test_at_the_bound_it_is_at_least_never_more_than() -> None:
    metrics, diagnosis = _sized(10.0, 5.0, True)

    assert "That is at least twice this shop's typical month-to-month change (about 5.0%)." in \
           _front(metrics=metrics, diagnosis=diagnosis).summary


def test_the_charts_top_point_is_inside_the_drawing() -> None:
    for run in ("demo_classed", "demo_unanswered"):
        svg = re.search(r'<svg[^>]*class="sales".*?</svg>', render_html(build_real(run)), re.S).group(0)
        tops = [float(y) for y in re.findall(r'(?:cy|y)="(-?[\d.]+)"', svg)]
        assert min(tops) >= 0, run


def test_a_month_with_no_sales_inside_the_chart_is_said_under_it() -> None:
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["core"]["revenue_by_month"] = [m for m in metrics["core"]["revenue_by_month"] if m["period"] != "2023-06"]

    assert ("June 2023 has no sales in the file - a closed month or missing data, which the file cannot tell apart - "
            "so the line breaks there.") in _front(metrics=metrics).chart_note


def test_the_forecasts_own_notes_are_in_plain_words() -> None:
    from shared.seasonality import RAMP_NOTE

    forecast = copy.deepcopy(files("kaggle")["forecast.json"])
    forecast["forecast"] |= {"history_note": "x", "season_note": RAMP_NOTE}
    next_month = _front(forecast=forecast).next_month

    assert ("It uses the last 36 full months only: an earlier month with no sales (a closed month or missing data, "
            "which the file cannot tell apart) cuts off the months before it.") in next_month
    assert ("No seasonal pattern is assumed: the months rise or fall steadily through the year, which a one-time "
            "change in the shop's level could also explain.") in next_month


def test_the_range_sentence_says_both_ways_it_is_built() -> None:
    assert ("The range is an 80% interval worked out from how far off this method's past estimates were (their root "
            "mean square times Student's t) or, with too few past estimates, from the spread of the months "
            "themselves.") in Page(render_html(build_real("kaggle"))).section("actions")


def test_the_ais_sentence_never_holds_a_front_word() -> None:
    import pytest
    from pydantic import ValidationError

    from contracts.forecast import ForecastContract

    from contracts.forecast_actions import front_word_problems

    # Q43: stage 4's checks refuse it (and retry); the contract keeps digits and signs only.
    assert front_word_problems("Grow revenue with regulars.") == ["it uses revenue"]
    assert front_word_problems("Keep the median in view.") == ["it uses median"]
    action = {"claim": "K1", "hypothesis_id": "B1", "fact": "f", "action": "Grow sales by 5 with regulars.",
              "why": "It worked.", "watch": "w"}
    with pytest.raises(ValidationError, match="refused"):
        ForecastContract.model_validate(with_actions("kaggle", "list", [action], "m"))
