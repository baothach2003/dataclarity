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

    inputs = NS(data=NS(blank_customer_months=frozenset(), parsed=NS(reverse={"customer": "Cust"})),
                tree=NS(returns=NS(returns_prev=0.0, returns_cur=0.0)),
                trust=NS(checks=[NS(id="D1", status="ok", evidence={
                    "excess_zero_days_cur": 0.5, "excess_zero_days_prev": 0.0})]))

    assert EVIDENCE["B1"](inputs, Changes(1000.0, 800.0, -200.0, -200.0, False)).verdict \
        == "inconclusive"


def test_a_history_month_at_half_the_median_active_days_is_no_longer_learned_from() -> None:
    """3E1's boundary - November with 15 active days of 30 sat AT the old floor
    (half the median, 0.5 x 30) and was learned from - replaced in 3E1b (part
    B: such a month hid a gap). Now, by hand: September and October never miss
    a day, so against them November expects 0 and finds 15 - over one day and
    over their spread of 0 - and is excluded (d1_pattern.learn)."""
    rows = daily_rows(date(2011, 9, 1), date(2012, 1, 31),
                      skip=tuple(date(2011, 11, d) for d in range(16, 31)))

    _, _, _, check = _run(rows)

    assert check.evidence["gapped_history_months"] == ["2011-11"]
    assert check.evidence["learned_months"] == ["2011-09", "2011-10"]


def test_t2_is_refused_when_the_year_ago_previous_month_has_missing_days() -> None:
    """The gap in last year's PREVIOUS month (January 2011) inflates last
    year's move into February just as a gap in February deflates it."""
    rows = daily_rows(date(2010, 1, 1), date(2012, 2, 29),
                      skip=tuple(date(2011, 1, d) for d in range(5, 15)))

    _, verdicts, _, _ = _run(rows)

    assert verdicts["T2"].verdict == "inconclusive"
    assert verdicts["T2"].evidence["excess_zero_days_year_ago_prev"] > 9
