"""The headline's size test (docs/AI_PIPELINE.md 7.8; session 3E1b, Thach's
decision on 3E2-F1): is this month's change larger than the shop's ordinary
month-to-month movement?

A hypothesis's share is measured against the change itself, so ANY
decomposition of a month that barely moved has a term holding a fifth of it:
on the planted-cause suite every month with nothing planted named a cause (30
of 30 seeds). T3 ("routine variation") is dormant since ADR-0007, so nothing
asked whether the change was larger than usual. This asks it once, for the
headline only: the verdicts and the hypothesis table are unchanged.
"""

from collections.abc import Mapping
from statistics import median

from contracts.diagnosis import HeadlineMovement
from shared.numbers import pct_change
from shared.periods import shift_month
from stages.diagnose.thresholds import HEADLINE_MOVEMENT_FACTOR, XMR_MIN_BASELINE_POINTS

# The 8 months the engine already asks of a baseline (step 4): 7 movements.
MIN_MOVEMENTS = XMR_MIN_BASELINE_POINTS - 1


def singled_out(change_pct: float, typical_pct: float) -> bool:
    return abs(change_pct) >= HEADLINE_MOVEMENT_FACTOR * typical_pct


def measure_movement(history: list[str], revenue: Mapping[str, float], *, revenue_prev: float,
                     revenue_cur: float, scale: float = 0.0) -> HeadlineMovement:
    """`history`: the frame's complete months before the current one (the
    previous month included); `revenue`: each one's net revenue as stage 3
    reads it. A movement is |r(m) - r(m-1)| / r(m-1) for consecutive months
    both in the history, in percent, by stage 2's own rule
    (shared.numbers.pct_change): a month after a non-positive or residue month
    has no base and is skipped. Percent, not money: the sentence states
    percentages, and a growing shop's money movements understate its scale.
    `scale` is the money moved in the compared months, residue's yardstick."""
    months = set(history)
    movements = []
    for month in history:
        before = shift_month(month, -1)
        if before in months:
            moved = pct_change(revenue[month], revenue[before]).value
            if moved is not None:
                movements.append(abs(moved))
    change = pct_change(revenue_cur, revenue_prev, scale)
    count = len(movements)
    if change.value is None:
        return HeadlineMovement(change_pct=None, typical_pct=None, movements=count,
                                factor=HEADLINE_MOVEMENT_FACTOR, singled_out=None,
                                reason=f"this month's change has no percentage: {change.reason}")
    if count < MIN_MOVEMENTS:
        what = "1 month-to-month change" if count == 1 else f"{count} month-to-month changes"
        return HeadlineMovement(change_pct=change.value, typical_pct=None, movements=count,
                                factor=HEADLINE_MOVEMENT_FACTOR, singled_out=None,
                                reason=f"only {what} before it can be measured, and {MIN_MOVEMENTS} "
                                       "are needed")
    typical = median(movements)
    return HeadlineMovement(change_pct=change.value, typical_pct=typical, movements=count,
                            factor=HEADLINE_MOVEMENT_FACTOR, singled_out=singled_out(change.value, typical),
                            reason=None)
