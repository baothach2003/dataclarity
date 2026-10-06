"""Step 3's follow-up (Thach, 2026-10-06: Q44-Q48; docs/REPORT_REDESIGN.md
section 10). Written before the code, each failing on it."""

import copy

from tests.stages.report.real_runs import build_real, files


def _18_7(run: str) -> dict:
    diagnosis = copy.deepcopy(files(run)["diagnosis.json"])
    diagnosis["schema_version"] = "18.7"
    diagnosis["headline"]["offsetting"] = False
    return diagnosis


# --- Q44: the printed figures and the words beside them agree ----------------------------------------------------


def test_beside_a_season_more_than_holds_on_the_printed_changes() -> None:
    # The review: "10.0% ... 12.0%; more than 4 times ... (about 0.50 points)" - printed, 12.0 - 10.0 is exactly
    # 4 x 0.50. The decimals grow until the printed changes say what stage 3 decided.
    diagnosis = _18_7("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 12.049
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.04, "difference_pct": 2.009,
                           "typical_pct": 0.5, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7
    summary = build_real("demo_classed", diagnosis=diagnosis).front.summary

    assert summary[0] == ("This change differs from earlier years: in the 2 earlier years, sales typically rose "
                          "10.04% between these months; this year they rose 12.05%; the difference is more than 4 "
                          "times this shop's typical year-on-year difference (about 0.50 points).")


def test_sentence_a_prints_its_change_at_the_seasons_decimals() -> None:
    # One figure, one printing: B's "this year they rose 12.05%" and A's change agree.
    diagnosis = _18_7("demo_classed")
    diagnosis["headline"]["movement"]["change_pct"] = 12.049
    diagnosis["headline"]["movement"]["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.04,
                                                    "difference_pct": 2.009, "typical_pct": 0.5, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7
    metrics = copy.deepcopy(files("demo_classed")["metrics.json"])
    metrics["core"]["revenue_change_pct"] = 12.049

    assert "(+12.05%)" in build_real("demo_classed", metrics=metrics, diagnosis=diagnosis).front.summary[1]


def test_beside_a_season_at_least_when_the_printed_gap_equals_the_bound() -> None:
    diagnosis = _18_7("demo_classed")
    movement = diagnosis["headline"]["movement"]
    movement["change_pct"] = 12.0
    movement["season"] |= {"band": "excess", "years": 2, "expected_change_pct": 10.0, "difference_pct": 2.0,
                           "typical_pct": 0.5, "beyond_factor": 4.0}
    diagnosis["headline"]["rule"] = 7

    assert "the difference is at least 4 times this shop's typical year-on-year difference (about 0.5 points)" in \
        build_real("demo_classed", diagnosis=diagnosis).front.summary[0]


def test_the_decimals_are_decided_on_the_text_printed() -> None:
    # The review: 4.35 is stored just under 4.35, so it prints "4.3"; deciding on round(4.35 * 10) read it as
    # 4.4, and "+8.7%" stood beside "less than twice ... about 4.3%" (2 x 4.3 = 8.6).
    data = files("kaggle")
    metrics, diagnosis = copy.deepcopy(data["metrics.json"]), _18_7("kaggle")
    diagnosis["headline"]["movement"] |= {"change_pct": 8.69, "typical_pct": 4.35, "singled_out": False}
    diagnosis["headline"] |= {"rule": 7, "hypothesis_id": None, "lens": None, "named": None}
    metrics["core"]["revenue_change_pct"] = 8.69
    summary = build_real("kaggle", metrics=metrics, diagnosis=diagnosis).front.summary

    assert "(about 4.35%)" in summary[0] and "(+8.69%)" in summary[1]


# --- Q45, Q46, Q48 -------------------------------------------------------------------------------------------------


def test_the_data_checks_line_says_they_passed() -> None:
    assert build_real("kaggle").front.data_checks == ["Data checks passed (details in the technical section)."]


def test_t2s_subject_is_the_change_a_year_earlier() -> None:
    diagnosis = _18_7("demo_classed")
    diagnosis["headline"]["movement"]["season"]["years"] = 3
    next(h for h in diagnosis["hypotheses"] if h["id"] == "T2")["verdict"] = "ruled_out"
    lines = [line for group in build_real("demo_classed", diagnosis=diagnosis).front.checklist for line in group.lines]

    assert "The change a year earlier between the same months." in lines
    assert not any("Last year's" in line for line in lines)


def test_t2_without_a_year_ago_pair_says_the_same_subject() -> None:
    # The review: a diagnosis before 18.4 has no year_ago pair; its line kept the old words.
    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract
    from stages.report.front_lines import Context, moved_line

    data = files("demo_classed")
    diagnosis = DiagnosisContract.model_validate(data["diagnosis.json"])
    ctx = Context(metrics=MetricsContract.model_validate(data["metrics.json"]), tree=diagnosis.tree,
                  bridge=diagnosis.tree.lever.bridge, year_ago=None, code=None)
    t2 = next(h for h in diagnosis.hypotheses if h.id == "T2")

    assert moved_line(t2, ctx) == "The change a year earlier between the same months - worth about +141,323.97."


def test_every_caution_line_names_its_own_month_and_no_generic_line_opens_them() -> None:
    for index, month, name in ((0, "current", "December 2024"), (0, "previous", "November 2024"),
                               (1, "current", "December 2024"), (2, "current", "December 2024")):
        diagnosis = _18_7("kaggle")
        diagnosis["trust"]["verdict"] = "caution"
        diagnosis["trust"]["checks"][index] |= {"status": "caution", "month": month, "message": "m"}
        caution = build_real("kaggle", diagnosis=diagnosis).front.caution

        assert len(caution) == 1 and name in caution[0], (index, month, caution)
