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

from collections.abc import Mapping, Sequence
from math import copysign
from statistics import median

from contracts.diagnosis import HeadlineMovement, SeasonBand, SeasonChange, season_band
from shared.numbers import is_negligible, pct_change
from shared.periods import shift_month
from stages.diagnose.thresholds import HEADLINE_MOVEMENT_FACTOR, SEASON_BEYOND_FACTOR, XMR_MIN_BASELINE_POINTS

# The 8 months the engine already asks of a baseline (step 4): 7 movements.
MIN_MOVEMENTS = XMR_MIN_BASELINE_POINTS - 1


def singled_out(change_pct: float, typical_pct: float) -> bool:
    return abs(change_pct) >= HEADLINE_MOVEMENT_FACTOR * typical_pct


def band(gap: float, typical: float) -> SeasonBand:
    """The contract's band (contracts/diagnosis.season_band) at the engine's
    factors: under 2 consistent, 2 to under 4 inconclusive, 4 or more a
    shortfall or an excess (Thach, 2026-10-04)."""
    return season_band(gap, typical, HEADLINE_MOVEMENT_FACTOR, SEASON_BEYOND_FACTOR)


def _gap(this: float, other: float) -> float:
    # Two changes equal but for floating-point residue have no gap: an exactly
    # repeated season read "far above" itself (review 1, M1). Judged on the
    # percent scale too - two changes near 0% made 1e-14 points "large" next
    # to themselves (review 2, #2).
    return 0.0 if is_negligible(this - other, this, other, 100.0) else this - other


def _on_the_bound(gap: float, typical: float) -> float:
    """A gap that is a band's bound but for floating-point residue IS the
    bound: Thach's "2 to under 4" put an exact 2 x on the inconclusive side
    and an exact 4 x on the far side, and residue flipped both (review 2,
    #3: revenue in cents, a gap of exactly 2 x read "within" it)."""
    for factor in (HEADLINE_MOVEMENT_FACTOR, SEASON_BEYOND_FACTOR):
        bound = factor * typical
        if bound and is_negligible(abs(gap) - bound, gap, bound, 100.0):
            return copysign(bound, gap)
    return gap


def compare_with_season(months: Sequence[str], revenue: Mapping[str, float], current: str
                        ) -> SeasonChange | None:
    """This month's change against the same calendar month's change in the
    earlier years of `months` (the season window: consecutive complete months
    through `current`), and the typical size of such a year-on-year
    difference over every other month pair (Thach, 2026-10-03; method:
    C:/Users/Happy/season-fact-method.txt). No seasonal index is estimated,
    so no season is fitted to the months it measures. None when this month or
    the same month a year earlier gives no change (an older year is never
    passed off as last year's), when fewer than MIN_MOVEMENTS differences can
    be measured, or when they are all 0 and this month's is not - the raw
    gate applies then."""
    present = set(months)

    def change(month: str) -> float | None:
        before = shift_month(month, -1)
        if month not in present or before not in present:
            return None
        return pct_change(revenue[month], revenue[before]).value

    now = change(current)
    if now is None or change(shift_month(current, -12)) is None:
        return None
    earlier = [c for k in range(1, len(months) // 12 + 1)
               if (c := change(shift_month(current, -12 * k))) is not None]
    differences = []
    for month in months:
        if month == current:
            continue
        this, year_ago = change(month), change(shift_month(month, -12))
        if this is not None and year_ago is not None:
            differences.append(abs(_gap(this, year_ago)))
    if len(differences) < MIN_MOVEMENTS:
        return None
    expected = median(earlier)
    typical = median(differences)
    gap = _on_the_bound(_gap(now, expected), typical)
    if typical == 0 and gap != 0:
        # Every other month repeated its year-ago change exactly (fixed fees,
        # memberships, rents): a typical of 0 sizes nothing, and every gap,
        # +0.2 points included, read "far" (review 3, #2). No comparison -
        # the raw gate decides. An exact repeat (a gap of 0) still matches.
        return None
    return SeasonChange(expected_change_pct=expected, years=len(earlier), difference_pct=gap, typical_pct=typical,
                        differences=len(differences), band=band(gap, typical), beyond_factor=SEASON_BEYOND_FACTOR)


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
