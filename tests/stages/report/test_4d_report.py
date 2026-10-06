"""The report redesign, step 4 as Thach's option (d), in the report: stage 5
prints forecast.json 2.1's code-written suggested actions as stage 4 wrote
them (design 1.4) - each beside its claim's fact, the checklist's own line,
and what to watch - with the notes naming their figures; no AI is counted.
Written before the code."""

import copy

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.assemble import predict
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import build_real, files, with_actions


def _forecast(run: str, code: str | None = None, **replaced: dict) -> dict:
    data = files(run)
    contract = predict(MetricsContract.model_validate(replaced.get("metrics", data["metrics.json"])),
                       DiagnosisContract.model_validate(replaced.get("diagnosis", data["diagnosis.json"])),
                       code=code).contract
    return contract.model_dump(mode="json")


def _cleaning(code: str | None) -> dict:
    cleaning = copy.deepcopy(files("kaggle")["cleaning_report.json"])
    if code:
        cleaning["currency"] = {"code": code, "source": "user", "evidence": None}
    return cleaning


def test_the_actions_stand_beside_their_facts_the_checklists_own_lines() -> None:
    report = build_real("kaggle", forecast=_forecast("kaggle"))
    steps = report.front.next_steps
    lines = [line for group in report.front.checklist for line in group.lines]

    # B1 and B2 moved out of the claims (step 4's scoped review): P2 remains.
    assert (steps.status, steps.sentence, len(steps.items)) == ("list", None, 1)
    assert [item.rests_on in lines for item in steps.items] == [True]
    assert steps.items[0].action == "Show a pricier alternative next to the cheaper products customers chose."
    assert steps.items[0].watch == ("Next month, check: the average price per item (23.25 this month; 24.70 the month "
                                    "before).")


def test_money_in_a_fact_carries_the_code_as_every_amount_does() -> None:
    report = build_real("kaggle", forecast=_forecast("kaggle", "GBP"), cleaning=_cleaning("GBP"))

    assert "about GBP -1,479.65" in report.front.next_steps.items[0].rests_on


def test_no_ai_answer_is_counted_for_the_actions() -> None:
    report = build_real("kaggle", forecast=_forecast("kaggle"))

    assert (report.provenance.ai_calls, report.provenance.models_used) == (0, [])


def test_no_cause_on_the_demo_and_nothing_to_act_on() -> None:
    none = build_real("demo_classed", forecast=_forecast("demo_classed")).front.next_steps
    suppressed = build_real("kaggle", forecast=with_actions("kaggle", "suppressed")).front.next_steps

    assert (none.status, none.sentence) == ("list", "No action is suggested: no single reason stands out in these "
                                                    "figures. Next month, compare sales with the estimate in "
                                                    "section 5.")
    assert (suppressed.status, suppressed.sentence) == (
        "suppressed", "No action is suggested: the figures above that moved have no action this report can suggest.")


def test_a_forecast_without_actions_says_they_are_not_available() -> None:
    sentence = ("Suggested actions are not available for this report: its forecast was made before they existed - "
                "run the forecast again to see them.")
    old = build_real("kaggle").front.next_steps  # the fixture's forecast is 2.0
    off = build_real("kaggle", forecast=with_actions("kaggle", "off")).front.next_steps

    assert (old.status, old.sentence) == ("unavailable", sentence)
    # Not made before (the review).
    assert (off.status, off.sentence) == (
        "off", "Suggested actions are not available for this report: run the forecast again.")


def test_the_appendix_points_to_the_actions_and_never_mentions_an_ai_switch() -> None:
    page = Page(render_html(build_real("kaggle", forecast=_forecast("kaggle"))))
    none = Page(render_html(build_real("demo_classed", forecast=_forecast("demo_classed"))))

    assert "Show a pricier alternative" in page.section("next-steps")
    assert "The suggested actions are in section 4 (What to do next)." in page.section("actions")
    assert ("No AI writes recommendations in this version: suggested actions, when there are any, are written by "
            "code in section 4." in none.section("actions"))
    assert "switched off" not in page.text + none.text


def test_the_notes_naming_the_actions_figures_stand_beside_section_4() -> None:
    notes = copy.deepcopy(files("demo_classed")["diagnosis.json"]["notes"][:1])
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    diagnosis = copy.deepcopy(files("kaggle")["diagnosis.json"])
    metrics["core"]["notes"] = notes
    diagnosis["notes"] = notes
    report = build_real("kaggle", metrics=metrics, diagnosis=diagnosis,
                        forecast=_forecast("kaggle", metrics=metrics, diagnosis=diagnosis))

    assert report.front.notes.next_steps == ["same_day_cancellations"]
    assert "Read these figures with: same day cancellations" in Page(render_html(report)).section("next-steps")


# --- the review, cycle 1 ---------------------------------------------------------------------------------------


def test_off_and_actions_under_no_named_cause_never_say_made_before() -> None:
    # Finding 11: "its forecast was made before they existed" is true only of a forecast before 2.1.
    action = {"claim": "K1", "hypothesis_id": "B1", "fact": "f", "action": "Thank customers.", "why": "w.",
              "watch": "w"}
    off = build_real("kaggle", forecast=with_actions("kaggle", "off")).front.next_steps
    mismatch = build_real("demo_classed", forecast=with_actions("demo_classed", "list", [action])).front.next_steps
    for steps in (off, mismatch):
        assert steps.sentence == "Suggested actions are not available for this report: run the forecast again."


def test_an_older_report_without_a_front_section_is_not_pointed_to_one() -> None:
    # Finding 13: report.json before 2.9 has no front - no section 4 is rendered.
    from contracts.report import ReportContract

    report = build_real("kaggle", forecast=_forecast("kaggle"))
    older = ReportContract.model_construct(**{**dict(report), "front": None})
    actions = Page(render_html(older)).section("actions")

    assert "No AI writes recommendations in this version." in actions and "section 4" not in actions
