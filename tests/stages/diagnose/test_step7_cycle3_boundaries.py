"""Boundaries of the 3E1 cycle-3 fixes that the mutation check found
unpinned (split from test_step7_cycle3_fixes.py for file size). Each test
kills one surviving mutant: the previous month's gap, a fractional excess
day, the exactly-half learning floor, the year-ago previous month."""

from datetime import date
from types import SimpleNamespace as NS

from stages.diagnose.step7_inputs import Changes
from tests.stages.diagnose.diagnose_fixtures import daily_rows
from tests.stages.diagnose.test_step7_cycle3_fixes import _run


def test_b1_is_refused_on_a_gap_in_the_previous_month_too() -> None:
    """Two days missing in December 2011 (the previous month), under the
    threshold: the rise into January is partly the gap, and B1 would read it
    as customers buying more often."""
    rows = daily_rows(date(2010, 12, 1), date(2012, 1, 31),
                      skip=(date(2011, 12, 10), date(2011, 12, 11)))

    _, verdicts, _, check = _run(rows)

    assert (check.evidence["excess_zero_days_cur"], check.evidence["excess_zero_days_prev"]) == (0.0, 2.0)
    assert verdicts["B1"].verdict == "inconclusive"


def test_b1_is_refused_on_a_fraction_of_an_excess_day() -> None:
    """"Any excess zero day" (Thach, 3E1) includes 0.5: the asymmetry prefers
    refusing a verdict a partial gap could have made."""
    from stages.diagnose.hypothesis_evidence import EVIDENCE

    inputs = NS(data=NS(parsed=NS(reverse={"customer": "Cust"})),
                tree=NS(returns=NS(returns_prev=0.0, returns_cur=0.0)),
                trust=NS(checks=[NS(id="D1", status="ok", evidence={
                    "excess_zero_days_cur": 0.5, "excess_zero_days_prev": 0.0})]))

    assert EVIDENCE["B1"](inputs, Changes(1000.0, 800.0, -200.0, -200.0, False)).verdict \
        == "inconclusive"


def test_a_history_month_with_exactly_half_the_median_active_days_is_learned_from() -> None:
    """The boundary, by hand. History candidates September (30 active days),
    October (31), November (15 of 30; December is the previous month and never
    learned from). Median 30, floor 0.5 x 30 = 15: November's 15 is AT the
    floor and stays. (The max, 31, would give 15.5 and drop it.)"""
    rows = daily_rows(date(2011, 9, 1), date(2012, 1, 31),
                      skip=tuple(date(2011, 11, d) for d in range(16, 31)))

    _, _, _, check = _run(rows)

    assert check.evidence["sparse_history_months"] == []
    assert check.evidence["learned_from_months"] == 3


def test_t2_is_refused_when_the_year_ago_previous_month_has_missing_days() -> None:
    """The gap in last year's PREVIOUS month (January 2011) inflates last
    year's move into February just as a gap in February deflates it."""
    rows = daily_rows(date(2010, 1, 1), date(2012, 2, 29),
                      skip=tuple(date(2011, 1, d) for d in range(5, 15)))

    _, verdicts, _, _ = _run(rows)

    assert verdicts["T2"].verdict == "inconclusive"
    assert verdicts["T2"].evidence["excess_zero_days_year_ago_prev"] > 9
