"""Report redesign step 1 (Thach, 2026-10-05): diagnosis.json 18.4's
`year_ago` (T2's two figures as a fact block - its evidence keys are not a
consumer field) and `headline.hedge` (which of rule 4's two sentences stage
3 chose). docs/REPORT_REDESIGN.md 1.1, 1.3 and 2; method
C:/Users/Happy/redesign-step1-method.txt M3, M4."""

from datetime import date

import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract, Headline
from stages.diagnose.assemble import SCHEMA_VERSION, diagnose
from stages.diagnose.headline import PLAIN_HEDGE, SEASON_HEDGE, choose_headline
from stages.diagnose.step7_inputs import Changes
from tests.stages.diagnose.diagnose_fixtures import NOW, daily_months, daily_rows, row, run_data
from tests.stages.diagnose.test_headline import catalog, tree, trust

FOURTEEN = {f"2023-{m:02d}": 1_000.0 + 10 * m for m in range(1, 13)} | {"2024-01": 1_150.0, "2024-02": 1_240.0}


def test_year_ago_holds_the_pair_t2_reads() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW)
    t2 = next(h for h in found.hypotheses if h.id == "T2")

    assert (found.year_ago.previous, found.year_ago.current) == ("2023-01", "2023-02")
    assert (found.year_ago.revenue_previous, found.year_ago.revenue_current) == (
        pytest.approx(t2.evidence["ly_prev"], abs=1e-9), pytest.approx(t2.evidence["ly_cur"], abs=1e-9))
    assert found.year_ago.revenue_current == pytest.approx(1_020.0, abs=1e-6)
    assert found.year_ago_reason is None


def test_no_year_ago_pair_is_null_with_t2s_reason() -> None:
    short = {f"2024-{m:02d}": 1_000.0 + m for m in range(1, 6)}
    found = diagnose(run_data(daily_months(short)), NOW)

    assert found.year_ago is None
    assert found.year_ago_reason == "the year-ago pair is not in the data"


def test_a_year_ago_month_only_partly_in_the_file_is_no_pair() -> None:
    # The file starts on 15 January 2023: last year's January is half a month, so the frame names no pair
    # and no half month is stated as a month's revenue (cycle 2 #6).
    rows = daily_rows(date(2023, 1, 15), date(2024, 2, 29))
    found = diagnose(run_data(rows), NOW)

    assert (found.frame.year_ago_previous, found.year_ago) == (None, None)
    assert found.year_ago_reason == "the year-ago pair is not in the data"


def test_t2_and_the_year_ago_block_say_a_missing_pair_in_one_set_of_words() -> None:
    from contracts.diagnosis import NO_YEAR_AGO_PAIR

    short = {f"2024-{m:02d}": 1_000.0 + m for m in range(1, 6)}
    found = diagnose(run_data(daily_months(short)), NOW)
    t2 = next(h for h in found.hypotheses if h.id == "T2")

    assert t2.evidence["reason"] == found.year_ago_reason == NO_YEAR_AGO_PAIR


def test_a_blocked_run_has_no_year_ago() -> None:
    found = diagnose(run_data(daily_rows(date(2011, 1, 15), date(2011, 2, 28))), NOW)

    assert found.trust.verdict == "blocked"
    assert found.year_ago is None and found.year_ago_reason == "the diagnosis is blocked"


@pytest.mark.parametrize("claimed,hedge,sentence", [(True, "seasonal", SEASON_HEDGE), (False, "plain", PLAIN_HEDGE)])
def test_rule_4_names_the_hedge_it_wrote(claimed: bool, hedge: str, sentence: str) -> None:
    from tests.stages.diagnose.test_season_fact import _gate, _season

    moved = Changes(1000.0, 840.0, -160.0, -160.0, True,
                    movement=_gate(_season("consistent", gap=2.2)) if claimed else None, season_claimed=claimed)
    masked = choose_headline(trust(), catalog(), tree(True, -480.0, 320.0), moved)

    assert masked.rule == 4
    assert masked.hedge == hedge
    assert masked.message.endswith(sentence)


@pytest.mark.parametrize("rows", [daily_months(FOURTEEN), daily_rows(date(2011, 1, 15), date(2011, 2, 28)),
                                  daily_months({"2024-01": 1_000.0, "2024-02": 1_000.0, "2024-03": 5_000.0})])
def test_every_other_rule_has_no_hedge(rows: list[dict]) -> None:
    found = diagnose(run_data(rows), NOW)

    assert found.headline.rule != 4 and found.headline.hedge is None


def test_a_hedge_that_is_not_the_messages_sentence_is_refused() -> None:
    with pytest.raises(ValidationError, match="ends with"):
        Headline(rule=4, hypothesis_id=None, lens=None, message="... This may be seasonal.", hedge="plain")


def test_year_ago_and_its_reason_together_are_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["year_ago_reason"] = "the year-ago pair is not in the data"

    with pytest.raises(ValidationError, match="year_ago"):
        DiagnosisContract.model_validate(found)


def test_year_ago_months_other_than_the_frames_are_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["year_ago"]["previous"] = "2022-12"

    with pytest.raises(ValidationError, match="frame's year-ago pair"):
        DiagnosisContract.model_validate(found)


def test_no_year_ago_beside_a_frame_that_has_the_pair_is_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["year_ago"], found["year_ago_reason"] = None, "the year-ago pair is not in the data"

    with pytest.raises(ValidationError, match="year_ago_reason"):
        DiagnosisContract.model_validate(found)


def test_a_hedge_off_rule_4_is_refused() -> None:
    # The message does end with the plain hedge: only the rule is wrong.
    with pytest.raises(ValidationError, match="rule 4 only"):
        Headline(rule=6, hypothesis_id="B1", lens="lever", message="x " + PLAIN_HEDGE, hedge="plain")


def test_an_18_4_rule_4_without_its_hedge_is_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["headline"] = Headline(rule=4, hypothesis_id=None, lens=None, message="m").model_dump()

    with pytest.raises(ValidationError, match="hedge"):
        DiagnosisContract.model_validate(found)


def test_an_18_4_file_needs_year_ago_or_its_reason() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["year_ago"] = None

    with pytest.raises(ValidationError, match="year_ago"):
        DiagnosisContract.model_validate(found)


def test_an_18_4_file_needs_a_bridge_or_its_withholding() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["tree"]["lever"]["bridge"] = None

    with pytest.raises(ValidationError, match="bridge"):
        DiagnosisContract.model_validate(found)


def test_an_18_3_file_carrying_a_new_field_is_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["schema_version"] = "18.3"

    with pytest.raises(ValidationError, match="before 18.4"):
        DiagnosisContract.model_validate(found)


def test_year_ago_revenue_other_than_t2s_pair_is_refused() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["year_ago"]["revenue_previous"] = 1.0

    with pytest.raises(ValidationError, match="pair T2 reads"):
        DiagnosisContract.model_validate(found)


def test_the_blocked_reason_on_a_run_that_is_not_blocked_is_refused() -> None:
    short = {f"2024-{m:02d}": 1_000.0 + m for m in range(1, 6)}
    found = diagnose(run_data(daily_months(short)), NOW).model_dump()
    found["year_ago_reason"] = "the diagnosis is blocked"

    with pytest.raises(ValidationError, match="year_ago_reason"):
        DiagnosisContract.model_validate(found)


def test_the_no_pair_reason_on_a_blocked_run_is_refused() -> None:
    found = diagnose(run_data(daily_rows(date(2011, 1, 15), date(2011, 2, 28))), NOW).model_dump()
    found["year_ago_reason"] = "the year-ago pair is not in the data"

    with pytest.raises(ValidationError, match="year_ago_reason"):
        DiagnosisContract.model_validate(found)


def test_a_split_withheld_for_refunds_b2_did_not_refuse_on_is_refused() -> None:
    # The same order value both months and no refund: level 2 is null for "aov_unchanged". Calling it
    # "refund_lines" changes nothing else in the bridge - only the tie to B2 can refuse it.
    rows = [row(date(2024, 10, day), qty=1.0, price=10.0, customer=f"C{day % 3}") for day in range(1, 32)]
    rows += [row(date(2024, 11, day), qty=1.0, price=10.0, customer=f"C{day % 4}") for day in range(1, 31)]
    found = diagnose(run_data(rows), NOW).model_dump()
    assert found["tree"]["lever"]["bridge"]["aov_split_withheld"] == "aov_unchanged"
    found["tree"]["lever"]["bridge"]["aov_split_withheld"] = "refund_lines"

    with pytest.raises(ValidationError, match="B2 refuses"):
        DiagnosisContract.model_validate(found)


def test_a_split_drawn_beside_b2s_refund_refusal_is_refused() -> None:
    # The bridge redrawn with the split, its cents allocated by the rule: only the tie to B2 is broken.
    from contracts.lever_bridge import allocate_cents, as_shown, printed_cents
    from tests.stages.diagnose.test_redesign_bridge import _with_a_refund

    found = diagnose(run_data(_with_a_refund()), NOW).model_dump()
    lever = found["tree"]["lever"]
    assert lever["bridge"]["aov_split_withheld"] == "refund_lines" and lever["level2"] is not None
    factors = [f for f in lever["level1"]["factors"] if f["name"] != "aov"] + lever["level2"]["factors"]
    bridge = lever["bridge"]
    total = printed_cents(bridge["revenue_current"]) - printed_cents(bridge["revenue_previous"])
    cents = allocate_cents([f["contribution"] for f in factors], total)
    bridge["bars"] = [{"factor": f["name"], "value_prev": f["value_prev"], "value_cur": f["value_cur"],
                       "contribution": f["contribution"], "shown": as_shown(c)} for f, c in zip(factors, cents)]
    bridge["aov_split"], bridge["aov_split_withheld"] = True, None

    with pytest.raises(ValidationError, match="B2 refuses"):
        DiagnosisContract.model_validate(found)


def test_an_18_3_file_without_the_new_fields_still_loads() -> None:
    found = diagnose(run_data(daily_months(FOURTEEN)), NOW).model_dump()
    found["schema_version"] = "18.3"
    del found["year_ago"], found["year_ago_reason"], found["headline"]["hedge"]
    del found["tree"]["lever"]["bridge"], found["tree"]["lever"]["bridge_withheld"]

    loaded = DiagnosisContract.model_validate(found)

    assert (loaded.year_ago, loaded.tree.lever.bridge, loaded.headline.hedge) == (None, None, None)


def test_the_version_is_18_4() -> None:
    assert SCHEMA_VERSION == "18.4"  # 18.4: bridge, year_ago, hedge (the report redesign, step 1)


def test_report_json_carries_the_headline_so_it_is_2_7() -> None:
    from contracts.report import ReportContract
    from stages.report.builder import SCHEMA_VERSION as REPORT_VERSION

    assert REPORT_VERSION == "2.7"  # 2.7: the headline's hedge (report.json carries the Headline model)
    assert "hedge" in ReportContract.model_fields["layer_2_causes"].annotation.model_fields["headline"].annotation.model_fields
