"""Thach's answers Q56-Q60 (2026-10-06; docs/REPORT_REDESIGN.md section 10).
Written before the code, each failing on it."""

import copy

from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from stages.predict.assemble import predict
from stages.report.html_report import render_html
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import build_real, files


def _18_8(run: str) -> dict:
    diagnosis = copy.deepcopy(files(run)["diagnosis.json"])
    diagnosis["schema_version"] = "18.7"
    diagnosis["headline"]["offsetting"] = False
    return diagnosis


# --- Q57: the season sentence carries its yardstick -----------------------------------------------------------------


def test_the_demos_in_line_sentence_carries_its_yardstick() -> None:
    summary = build_real("demo_unanswered").front.summary

    # Two decimals: at one, stage 3's gap prints 12.1 beside 39.1 - 27.1 = 12.0 (a decision made alone,
    # recorded in section 12 - Thach's example said 12.0 and 8.5).
    assert summary[0] == ("This change is in line with last year's: 39.14% last year, 27.08% this year (one earlier "
                          "year to compare with) - a gap of 12.06 points, within twice this shop's typical gap (8.55 "
                          "points).")


def test_a_season_beyond_its_band_carries_its_gap_and_yardstick() -> None:
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 12.049
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.04, "difference_pct": 2.009,
                           "typical_pct": 0.5, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7

    # Printed at one decimal, 12.0 - 10.0 = 2.0 is exactly 4 x 0.5: "at least" (Q58).
    assert build_real("demo_classed", diagnosis=diagnosis).front.summary[0] == (
        "This change differs from earlier years: in the 2 earlier years, sales typically rose 10.0% between these "
        "months; this year they rose 12.0% - a gap of 2.0 points, at least 4 times this shop's typical gap (0.5 "
        "points).")


# --- Q58: "at least" only when the printed figures are equal -------------------------------------------------------


def test_more_than_when_the_printed_gap_is_more() -> None:
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 12.5
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.0, "difference_pct": 2.5,
                           "typical_pct": 0.5, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7
    sentence = build_real("demo_classed", diagnosis=diagnosis).front.summary[0]

    assert "a gap of 2.5 points, more than 4 times this shop's typical gap (0.5 points)" in sentence


def test_the_reviews_case_reads_at_least_where_the_printed_figures_are_equal() -> None:
    # The stored gap on the bound: at one decimal the printed gap (12.1 - 10.0) is not
    # stage 3's (2.0), so two decimals - where 2.04 is exactly 4 x 0.51.
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 12.08
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.04, "difference_pct": 2.04,
                           "typical_pct": 0.51, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7

    assert "a gap of 2.04 points, at least 4 times this shop's typical gap (0.51 points)" in \
        build_real("demo_classed", diagnosis=diagnosis).front.summary[0]


def test_equal_printed_figures_say_at_least() -> None:
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 12.0
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.0, "difference_pct": 2.0,
                           "typical_pct": 0.5, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7

    assert "a gap of 2.0 points, at least 4 times this shop's typical gap (0.5 points)" in \
        build_real("demo_classed", diagnosis=diagnosis).front.summary[0]


# --- Q56: one change, one printing ------------------------------------------------------------------------------


def test_sentence_a_and_the_season_print_the_change_the_same_way() -> None:
    # The month-to-month test would want two decimals (12.049 against twice 6.02); the
    # season sentence is the one printed, so A prints the change as B does.
    data = files("demo_classed")
    metrics = copy.deepcopy(data["metrics.json"])
    metrics["core"]["revenue_change_pct"] = 12.049
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement |= {"change_pct": 12.049, "typical_pct": 6.02, "singled_out": True, "factor": 2.0}
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 2.0, "difference_pct": 10.049,
                           "typical_pct": 2.0, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7
    summary = build_real("demo_classed", metrics=metrics, diagnosis=diagnosis).front.summary
    printed = [part for part in summary[1].replace(";", " ").split() if part.endswith("%")]

    assert printed[-1] == "12.0%" and "(+12.0%)" in summary[0]


# --- Q59: the data-checks line with its count ------------------------------------------------------------------------


def test_a_check_that_could_not_run_is_counted() -> None:
    diagnosis = _18_8("kaggle")
    diagnosis["trust"]["checks"][1] |= {"status": "inconclusive", "message": "m"}

    assert build_real("kaggle", diagnosis=diagnosis).front.data_checks == [
        "Data checks passed (2 of 3 could run on this file; details in the technical section)."]


# --- Q60: not shown (the scoped review of the fixes still found it false on a common shape; the stop rule) -----


def _actions_with(changes: dict[str, dict]) -> dict:
    data = files("kaggle")
    diagnosis = copy.deepcopy(data["diagnosis.json"])
    diagnosis["schema_version"] = "18.8"
    diagnosis["headline"] |= {"rule": 6, "hypothesis_id": "R1", "lens": None, "named": ["R1"], "hedge": None,
                              "offsetting": False}
    for h in diagnosis["hypotheses"]:
        h |= changes.get(h["id"], {})
        if h.get("member") is not None:
            h["evidence"]["top_member"] = h["member"]
    forecast = predict(MetricsContract.model_validate(data["metrics.json"]),
                       DiagnosisContract.model_validate(diagnosis)).contract.model_dump(mode="json")
    return {"diagnosis": diagnosis, "forecast": forecast}


_WITH_R1 = {"R1": {"verdict": "supported", "member": "Blue Mug"},
            "P2": {"against_the_change": False, "share": 0.0, "contribution": 0.0}}


def test_no_line_before_the_actions_whatever_the_calendar_and_the_year_before() -> None:
    # The cases the reviews named: the Kaggle run as stage 4 writes it (an action against the change), the
    # year before at 1.48 times the change beside the calendar, the calendar alone, the year before alone.
    data = files("kaggle")
    kaggle = predict(MetricsContract.model_validate(data["metrics.json"]),
                     DiagnosisContract.model_validate(data["diagnosis.json"])).contract.model_dump(mode="json")
    cases = [{"forecast": kaggle},
             _actions_with(_WITH_R1),  # the fixture's T1 0.26, T2 1.48
             _actions_with(_WITH_R1 | {"T2": {"verdict": "ruled_out"}}),
             _actions_with(_WITH_R1 | {"T1": {"verdict": "ruled_out"}, "T2": {"share": 0.5}})]
    for case in cases:
        report = build_real("kaggle", **case)
        steps = Page(render_html(report)).section("next-steps")

        assert report.front.next_steps.items
        assert "Part of this change matches" not in steps and "about the rest" not in steps
        assert "lead" not in report.front.next_steps.model_dump()


# --- the scoped review: no precision agrees - the sentence says less, never prints at four decimals ---------------


def test_a_season_gap_no_precision_prints_as_the_subtraction_is_not_printed() -> None:
    # The review's case: at every precision up to 4 the printed gap is not 103.57.. - 88.83.. as printed.
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 88.83643761331413
    movement["season"] |= {"band": "consistent", "years": 1, "expected_change_pct": 103.57286379176026,
                           "difference_pct": 103.57286379176026 - 88.83643761331413, "typical_pct": 9.85177212813136}
    diagnosis["headline"]["rule"] = 7
    summary = build_real("demo_classed", diagnosis=diagnosis).front.summary

    assert summary[0] == ("This change is in line with last year's: 103.6% last year, 88.8% this year (one earlier "
                          "year to compare with).")
    assert "(+27.2%)" in summary[1]  # sentence A at the one decimal B printed


def test_a_band_word_no_precision_supports_is_not_printed() -> None:
    # The review: "a gap of 2.5554 points, at least 4 times ... (0.6389 points)" - 4 x 0.6389 = 2.5556.
    diagnosis = _18_8("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 28.131083831103325
    movement["season"] |= {"band": "excess", "years": 1, "expected_change_pct": 25.575635280983818,
                           "difference_pct": 28.131083831103325 - 25.575635280983818,
                           "typical_pct": 0.6388559201911689, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7
    sentence = build_real("demo_classed", diagnosis=diagnosis).front.summary[0]

    assert sentence == ("This change differs from last year's: 25.6% last year, 28.1% this year (one earlier year to "
                        "compare with).")


def test_a_month_to_month_word_no_precision_supports_is_not_printed() -> None:
    # The review's shape: 0.29999 is under twice 0.149999, but printed at 1-4 decimals it is never under
    # (0.30 = 2 x 0.15).
    data = files("kaggle")
    metrics, diagnosis = copy.deepcopy(data["metrics.json"]), _18_8("kaggle")
    diagnosis["headline"]["movement"] |= {"change_pct": 0.29999, "typical_pct": 0.149999, "singled_out": False}
    diagnosis["headline"] |= {"rule": 7, "hypothesis_id": None, "lens": None, "named": None}
    metrics["core"]["revenue_change_pct"] = 0.29999
    summary = build_real("kaggle", metrics=metrics, diagnosis=diagnosis).front.summary

    assert not any("typical month-to-month change" in line for line in summary)
    assert "(+0.3%)" in summary[0]


def test_a_typical_change_too_small_to_print_is_not_printed() -> None:
    data = files("kaggle")
    metrics, diagnosis = copy.deepcopy(data["metrics.json"]), _18_8("kaggle")
    diagnosis["headline"]["movement"] |= {"change_pct": 9.8, "typical_pct": 0.00004, "singled_out": True}
    metrics["core"]["revenue_change_pct"] = 9.8
    summary = build_real("kaggle", metrics=metrics, diagnosis=diagnosis).front.summary

    assert not any("0.0000" in line for line in summary)
