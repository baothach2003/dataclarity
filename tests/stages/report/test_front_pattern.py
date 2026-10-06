"""Thach's pattern (2026-10-06): every fabrication in step 3 came from stage 5
guessing what a stage 3 result means - the meaning is DATA written by stage 3,
never inferred; where wording a result needs meaning the data does not
carry, the front says less. His answers Q39-Q43, D2, orders or lines, and
D1-D3 in one line - each test written before the code, each failing on it.
docs/REPORT_REDESIGN.md sections 10 and 12."""

import copy
import re

from contracts.report_front import FRONT_BANNED
from stages.diagnose.catalog import BY_ID
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import build_real, files

NOT_AVAILABLE = "Suggested actions are not available for this report."


def _18_7(run: str = "kaggle") -> dict:
    diagnosis = copy.deepcopy(files(run)["diagnosis.json"])
    diagnosis["schema_version"] = "18.7"
    diagnosis["headline"]["offsetting"] = False
    return diagnosis


def _blocked(diagnosis: dict, check: dict) -> dict:
    diagnosis["trust"]["verdict"] = "blocked"
    diagnosis["trust"]["checks"][0] |= check
    diagnosis.update({"calendar": None, "signals": None, "tree": None, "localization": None, "year_ago": None,
                      "year_ago_reason": "the diagnosis is blocked"})
    diagnosis["headline"] = {"rule": 1, "hypothesis_id": None, "lens": None, "message": "m", "offsetting": False}
    return diagnosis


def _front_text(report) -> str:
    return Page(render_html(report)).front_text


# --- Q39: which month a check is about is stage 3's -------------------------------------------------------


def test_a_block_on_the_previous_months_coverage_names_the_previous_month() -> None:
    diagnosis = _blocked(_18_7(), {"status": "blocked", "month": "coverage", "message": "m"})
    summary = build_real("kaggle", diagnosis=diagnosis).front.summary

    # "Does not show sales across the whole": stage 3 blocks a previous month
    # cut short AND one with no sale at all - "covers only part" fits one.
    assert summary == ["The data cannot support conclusions: the file does not show sales across the whole of "
                       "November 2024, so the two months cannot be compared."]
    assert "December" not in summary[0]


def test_a_block_on_the_current_month_names_the_current_month() -> None:
    diagnosis = _blocked(_18_7(), {"status": "blocked", "month": "current", "message": "m"})

    assert build_real("kaggle", diagnosis=diagnosis).front.summary == [
        "The data cannot support conclusions: at least half the days in December 2024 have no sales at all - "
        "missing data, or days the shop was closed."]


def test_d3s_caution_names_its_month() -> None:
    diagnosis = _18_7()
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][2] |= {"status": "caution", "month": "current", "message": "m"}
    front = build_real("kaggle", diagnosis=diagnosis).front

    assert front.caution == ["Many rows in December 2024 were flagged during cleaning."]
    assert front.data_checks == front.caution  # shown once: the caution opens section 1


def test_a_caution_on_the_previous_month_names_the_previous_month() -> None:
    diagnosis = _18_7()
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][0] |= {"status": "caution", "month": "previous", "message": "m"}

    assert build_real("kaggle", diagnosis=diagnosis).front.caution[0] == (
        "Some days in November 2024 have no sales at all - missing data, or days the shop was closed (the file "
        "cannot tell which).")


def test_no_caution_line_in_the_front_says_this_month_about_another_month() -> None:
    """Thach's safety valve (2026-10-06): the scoped review found the caution
    opener "Some of this month's data may be missing or wrong" beside a
    caution on the PREVIOUS month - that kind of line left the front; the
    appendix keeps the trust verdict and each check's message."""
    diagnosis = _18_7()
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][0] |= {"status": "caution", "month": "previous", "message": "THE CHECK'S MESSAGE"}
    report = build_real("kaggle", diagnosis=diagnosis)
    page = Page(render_html(report))

    assert report.front.caution == ["Some days in November 2024 have no sales at all - missing data, or days the "
                                    "shop was closed (the file cannot tell which)."]
    assert "this month's data" not in page.front_text and "this month's data" not in str(report.front.model_dump())
    assert "Data trust: caution" in page.text and "THE CHECK'S MESSAGE" in page.text  # the appendix keeps it


def test_a_caution_from_a_check_that_could_not_run_shows_the_data_checks_line() -> None:
    # Stage 3 cautions when a check is inconclusive (the review): no check line, so section 3 says it.
    diagnosis = _18_7()
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][1] |= {"status": "inconclusive", "message": "m"}
    report = build_real("kaggle", diagnosis=diagnosis)

    assert report.front.caution == []
    assert ("Data checks: no problem found in the checks this file allows (details in the technical section)."
            in Page(render_html(report)).section("checked"))


def test_a_check_with_no_month_written_is_said_without_one() -> None:
    # An 18.6 file names no month: the front says less, never guesses this month.
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][0] |= {"status": "caution", "message": "m"}

    line = build_real("kaggle", diagnosis=diagnosis).front.caution[0]
    assert "December" not in line and "November" not in line


# --- D2 and D1-D3 in one line ------------------------------------------------------------------------------


def test_d2s_caution_says_what_it_tests_never_the_wrong_scale() -> None:
    diagnosis = _18_7()
    diagnosis["trust"]["verdict"] = "caution"
    diagnosis["trust"]["checks"][1] |= {"status": "caution", "month": "current", "message": "m"}
    caution = build_real("kaggle", diagnosis=diagnosis).front.caution

    # "Jump or fall": D2 flags a factor below its band as well as above.
    assert caution[0] == ("A sudden price jump or fall across most products in December 2024: a change in the data's "
                          "units or currency, or a deliberate repricing (the file cannot tell which).")
    assert "wrong scale" not in " ".join(caution)


def test_a_check_that_could_not_run_is_no_problem_found_said_as_such() -> None:
    diagnosis = _18_7()
    diagnosis["trust"]["checks"][1] |= {"status": "inconclusive", "message": "m"}
    for hypothesis in diagnosis["hypotheses"]:
        if hypothesis["id"] == "D2":
            hypothesis["verdict"] = "inconclusive"
    front = build_real("kaggle", diagnosis=diagnosis).front
    lines = [line for group in front.checklist for line in group.lines]

    assert front.data_checks == ["Data checks: no problem found in the checks this file allows (details in the "
                                 "technical section)."]
    assert not any("price jump" in line or "wrong scale" in line for line in lines)  # D2: the one line only


def test_the_data_checks_line_is_printed_in_section_3() -> None:
    page = Page(render_html(build_real("kaggle")))

    assert "Data checks: no problem found (details in the technical section)." in page.section("checked")


def test_all_three_data_checks_ok_is_one_line() -> None:
    front = build_real("kaggle").front
    lines = [line for group in front.checklist for line in group.lines]

    assert front.data_checks == ["Data checks: no problem found (details in the technical section)."]
    assert not any("days without sales" in line or "wrong scale" in line or "flagged" in line for line in lines)


# --- orders or lines: the existing rule -----------------------------------------------------------------------


def test_a_file_with_no_order_id_never_says_orders() -> None:
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["core"]["orders_basis"] = "lines"
    diagnosis = _18_7()
    for hypothesis in diagnosis["hypotheses"]:
        if hypothesis["id"] in ("B1", "B2"):
            hypothesis["statement"] = BY_ID[hypothesis["id"]].render(hypothesis["contribution"], "lines")
    report = build_real("kaggle", metrics=metrics, diagnosis=diagnosis)
    text = _front_text(report) + " " + " ".join(_strings(report.front.model_dump()))

    assert re.findall(r"(?i)\border(?:s|ed|ing)?\b", text) == []


# --- a season of several years: never "last year's" ----------------------------------------------------------


def _season(years: int) -> dict:
    diagnosis = _18_7("demo_classed")
    diagnosis["headline"]["movement"]["season"]["years"] = years
    return diagnosis


def test_a_multi_year_season_never_says_last_years() -> None:
    report = build_real("demo_classed", diagnosis=_season(3))
    text = " ".join(_strings(report.front.model_dump()))

    assert "last year's" not in text and "regular pattern" not in text


def test_t2_states_the_fact_only_q41() -> None:
    moved = build_real("demo_classed", diagnosis=_season(1)).front.checklist[0].lines

    assert "Last year alone, sales rose between October and November: 518,318.50 to 658,764.09." in moved
    assert not any("regular pattern" in line for line in moved)


# --- the summary links every note naming its figures (the demo finding) -------------------------------------------


def test_the_summary_links_the_notes_naming_its_figures() -> None:
    notes = build_real("demo_classed").front.notes

    assert set(notes.summary) == {"same_day_cancellations", "unconfirmed_suggestions"}


# --- Q42: no AI suggestion of the old format, anywhere ----------------------------------------------------------


def test_no_pre_2_1_ai_text_anywhere_in_the_page() -> None:
    from contracts.cleaning import CleaningReportContract
    from contracts.diagnosis import DiagnosisContract
    from contracts.forecast import ForecastContract
    from contracts.metrics import MetricsContract
    from stages.report.builder import build_report

    data = files("kaggle")
    forecast = copy.deepcopy(data["forecast.json"])
    forecast |= {"model_used": "m", "do_not_do": [{"tempting_action": "OLDTEMPTING", "why_wrong_here": "OLDWHY"}],
                 "recommendations": [{"priority": 1, "insight": "OLDINSIGHT", "cause": "OLDCAUSE",
                                      "action": "OLDACTION", "expected_impact": "OLDIMPACT",
                                      "how_to_measure": "OLDMEASURE", "confidence": 0.8}]}
    report = build_report(run_id="r", source_file="f.csv", metrics=MetricsContract.model_validate(data["metrics.json"]),
                          diagnosis=DiagnosisContract.model_validate(data["diagnosis.json"]),
                          forecast=ForecastContract.model_validate(forecast),
                          cleaning=CleaningReportContract.model_validate(data["cleaning_report.json"]),
                          schema=None, plan_source=None, include_recommendations=True)
    html = render_html(report)

    assert not re.search(r"OLD(TEMPTING|WHY|INSIGHT|CAUSE|ACTION|IMPACT|MEASURE)", html)
    assert report.front.next_steps.sentence == NOT_AVAILABLE


# --- Q43: banned words are stage 4's check; "median" banned ------------------------------------------------------


def test_the_contract_no_longer_refuses_a_front_word_and_median_is_banned() -> None:
    from contracts.forecast import ForecastContract
    from tests.stages.report.real_runs import with_actions

    action = {"claim": "K1", "hypothesis_id": "B1", "fact": "f", "action": "Grow revenue with regulars.",
              "why": "It worked.", "watch": "w"}
    ForecastContract.model_validate(with_actions("kaggle", "list", [action], "m"))
    assert "median" in FRONT_BANNED


# --- the rest of the review -----------------------------------------------------------------------------------------


def test_sentence_c_says_less_when_the_file_does_not_name_the_cause() -> None:
    diagnosis = _18_7()
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": None, "lens": None, "named": ["B1"], "offsetting": True}
    summary = build_real("kaggle", diagnosis=diagnosis).front.summary

    assert summary[-1].startswith("The change is what is left of movements in opposite directions")
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": None, "lens": None, "named": None}
    summary = build_real("kaggle", diagnosis=diagnosis).front.summary
    assert len(summary) == 2 and not any("made before" in line for line in summary)


def test_an_18_6_rule_6_naming_several_is_neither_a_tie_nor_offsetting() -> None:
    # Before 18.7 the file cannot say which: no sentence C (say less), never "the figures match".
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": None, "lens": None, "named": ["B1", "P2"]}
    summary = build_real("kaggle", diagnosis=diagnosis).front.summary

    assert len(summary) == 2 and not any("figures match" in line or "opposite" in line for line in summary)


def test_a_check_ruled_out_on_a_file_with_no_order_id_never_says_order() -> None:
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["core"]["orders_basis"] = "lines"
    diagnosis = _18_7()
    for hypothesis in diagnosis["hypotheses"]:
        if hypothesis["id"] in ("B1", "B2"):
            hypothesis |= {"verdict": "ruled_out", "statement": BY_ID[hypothesis["id"]].render(0.0, "lines")}
    groups = build_real("kaggle", metrics=metrics, diagnosis=diagnosis).front.checklist
    lines = [line for group in groups for line in group.lines]

    assert "Basket size (items per line)." in lines and "How many lines each customer bought." in lines
    assert not [line for line in lines if re.search(r"(?i)order", line)]


def test_an_18_7_tie_is_read_as_a_tie_never_as_offsetting() -> None:
    diagnosis = _18_7()
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": None, "lens": None, "named": ["B1", "T1"],
                              "offsetting": False}
    sentence = build_real("kaggle", diagnosis=diagnosis).front.summary[-1]

    assert sentence.startswith("The figures match customers ordering more often")
    assert "; and equally the calendar" in sentence and "opposite" not in sentence


def test_the_season_gap_is_never_a_figure_the_front_computes() -> None:
    diagnosis = _18_7("demo_classed")
    diagnosis["headline"]["movement"]["season"] |= {"band": "excess", "difference_pct": 18.04, "typical_pct": 4.0}
    diagnosis["headline"]["rule"] = 7
    sentence = build_real("demo_classed", diagnosis=diagnosis).front.summary[0]

    assert "18.0" not in sentence and "points is" not in sentence
    assert "more than 4 times this shop's typical year-on-year difference (about 4.0 points)" in sentence


def test_a_change_that_moved_never_prints_as_zero() -> None:
    data = files("kaggle")
    metrics, diagnosis = copy.deepcopy(data["metrics.json"]), _18_7()
    diagnosis["headline"]["movement"] |= {"change_pct": 0.03, "typical_pct": 4.9, "singled_out": False}
    diagnosis["headline"] |= {"rule": 7, "hypothesis_id": None, "lens": None, "named": None}
    metrics["core"]["revenue_change_pct"] = 0.03

    assert "(+0.03%)" in build_real("kaggle", metrics=metrics, diagnosis=diagnosis).front.summary[1]


def test_more_than_only_when_the_printed_figures_say_so() -> None:
    data = files("kaggle")
    metrics, diagnosis = copy.deepcopy(data["metrics.json"]), _18_7()
    diagnosis["headline"]["movement"] |= {"change_pct": 9.804, "typical_pct": 4.9, "singled_out": True}
    metrics["core"]["revenue_change_pct"] = 9.804
    summary = build_real("kaggle", metrics=metrics, diagnosis=diagnosis).front.summary

    assert "(+9.804%)" in summary[0] and "(about 4.900%)" in summary[1]


def test_lapsed_customers_are_never_worded_as_a_loss_when_they_added() -> None:
    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract
    from stages.report.front_lines import Context, moved_line

    data = files("demo_classed")
    diagnosis = DiagnosisContract.model_validate(data["diagnosis.json"])
    tree = diagnosis.tree
    customers = tree.customers.model_copy(update={"lapsed": 500.0})
    ctx = Context(metrics=MetricsContract.model_validate(data["metrics.json"]),
                  tree=tree.model_copy(update={"customers": customers}), bridge=tree.lever.bridge,
                  year_ago=diagnosis.year_ago, code=None)
    c2 = next(h for h in diagnosis.hypotheses if h.id == "C2").model_copy(update={"verdict": "supported"})

    assert "lost" not in moved_line(c2, ctx)


def test_p1_and_p2_in_sentence_c_keep_q20s_caveat() -> None:
    diagnosis = _18_7()
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": "P2", "lens": "product", "named": ["P2"]}

    assert "a different measure from the chart" in build_real("kaggle", diagnosis=diagnosis).front.summary[-1]


def test_the_appendix_charts_carry_the_code() -> None:
    cleaning = copy.deepcopy(files("kaggle")["cleaning_report.json"])
    cleaning["currency"] = {"code": "GBP", "source": "user", "evidence": None}

    html = render_html(build_real("kaggle", cleaning=cleaning))

    assert len(re.findall(r'"tickprefix":\s*"GBP "', html)) == 2  # the trend and the forecast


def _strings(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for key, item in value.items() if key != "factor" for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []
