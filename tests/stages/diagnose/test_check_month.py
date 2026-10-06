"""diagnosis.json 18.7 (the report redesign, Thach Q39, Q40; his pattern of
2026-10-06: the meaning is data written by stage 3, never inferred by stage
5): each caution or block says which month it is about - the current month,
the previous month, or the previous month's coverage - and the headline says
whether it is rule 6's offsetting case. Additive: no check's status, no
headline's rule or message changes."""

from datetime import date

import pytest

from stages.diagnose.trust_checks import d2_price_level, d3_flagged_rows
from tests.stages.diagnose.diagnose_fixtures import daily_rows, row, run_data
from tests.stages.diagnose.test_2en_headline import _headline, _moved
from tests.stages.diagnose.test_frame_and_trust import _two_period_prices
from tests.stages.diagnose.test_hypotheses import step7


def _d1(rows):
    return next(check for check in step7(run_data(rows)).trust.checks if check.id == "D1")


def test_a_previous_month_the_file_covers_only_part_of_is_coverage() -> None:
    check = _d1(daily_rows(date(2011, 1, 15), date(2011, 2, 28)))

    assert (check.status, check.month) == ("blocked", "coverage")


def test_a_gap_in_the_previous_month_is_about_the_previous_month() -> None:
    rows = daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3,
                      skip=tuple(date(2011, 2, d) for d in range(10, 22)))

    check = _d1(rows)

    assert (check.status, check.month) == ("caution", "previous")


def test_a_gap_in_the_current_month_is_about_the_current_month() -> None:
    rows = daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3,
                      skip=tuple(date(2011, 3, d) for d in range(10, 16)))

    check = _d1(rows)

    assert (check.status, check.month) == ("caution", "current")


def test_a_current_month_with_most_days_empty_blocks_about_the_current_month() -> None:
    rows = daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3,
                      skip=tuple(date(2011, 3, d) for d in range(2, 30)))

    check = _d1(rows)

    assert (check.status, check.month) == ("blocked", "current")


def test_an_ok_check_names_no_month() -> None:
    check = _d1(daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3))

    assert (check.status, check.month) == ("ok", None)


def test_d2_and_d3_caution_about_the_current_month() -> None:
    prev = {f"P{i}": 10.0 + i for i in range(20)}
    d2 = d2_price_level(run_data(_two_period_prices(prev, {k: v * 100 for k, v in prev.items()})))
    rows = [row(date(2011, 10, day)) for day in range(1, 11)] + [row(date(2011, 11, day)) for day in range(1, 11)]
    rows.append(row(date(2011, 11, 30)))
    for entry, flag in zip(rows, ["False"] * 10 + ["True"] * 5 + ["False"] * 6, strict=True):
        entry["__flag_negative__Qty"] = flag
    d3 = d3_flagged_rows(run_data(rows))

    assert (d2.status, d2.month, d3.status, d3.month) == ("caution", "current", "caution", "current")


def test_only_the_offsetting_case_is_offsetting() -> None:
    offsetting = _headline(_moved(1_000.0, 800.0), P1=("supported", -600.0), P2=("ruled_out", 380.0))
    tie = _headline(_moved(1_000.0, 800.0), B1=("supported", -180.0), P5=("supported", -180.0))

    assert (offsetting.rule, offsetting.offsetting) == (6, True)
    assert tie.offsetting is None  # assemble writes False for every other headline


def test_a_diagnosis_marks_only_the_offsetting_case() -> None:
    from stages.diagnose.assemble import diagnose
    from tests.stages.diagnose.test_redesign_year_ago_hedge import FOURTEEN, NOW, daily_months

    headline = diagnose(run_data(daily_months(FOURTEEN)), NOW).headline

    assert headline.rule != 6 or headline.hypothesis_id is not None
    assert headline.offsetting is False


def test_an_offsetting_mark_on_another_rule_is_refused() -> None:
    from pydantic import ValidationError

    from contracts.diagnosis import Headline

    with pytest.raises(ValidationError, match="offsetting"):
        Headline(rule=5, hypothesis_id=None, lens=None, named=["T1"], offsetting=True, message="m")


def test_an_18_7_file_says_both_and_an_earlier_one_cannot() -> None:
    import copy

    from pydantic import ValidationError

    from contracts.diagnosis import DiagnosisContract
    from tests.stages.report.real_runs import files

    payload = copy.deepcopy(files("kaggle")["diagnosis.json"])
    payload["schema_version"] = "18.7"
    payload["headline"]["offsetting"] = False
    DiagnosisContract.model_validate(payload)
    for change in ({"headline": payload["headline"] | {"offsetting": None}},
                   {"schema_version": "18.6"},
                   {"trust": payload["trust"] | {"checks": [payload["trust"]["checks"][0] | {"month": "current"}]
                                                 + payload["trust"]["checks"][1:]}},
                   {"headline": payload["headline"] | {"rule": 6, "hypothesis_id": None, "lens": None,
                                                       "named": None, "offsetting": False}}):
        with pytest.raises(ValidationError):
            DiagnosisContract.model_validate(payload | change)
