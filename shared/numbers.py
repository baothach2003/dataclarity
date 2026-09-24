"""Comparing money that came out of floating-point arithmetic - one definition
for every stage (moved here from stages/diagnose/numbers.py in session 2E, so
stage 2's ratios use exactly the guard stage 3's do; a stage may not import
another).

`x == 0` is the wrong question to ask about a figure produced by summing and
subtracting money. Two totals that are equal in the business sense routinely
differ by 1e-17, and every place that divides by such a difference turns that
residue into a headline number: stage 3 produced a gross-to-net ratio of
4.5e15 (3C doubt-review) and a member share of -5.4e15 (3D doubt-review) from
exactly this mistake, because each place wrote its own `== 0` guard.
"""

from typing import NamedTuple

# Relative, because the residue scales with the numbers it came from: an
# absolute epsilon is either meaningless on a shop turning over millions or
# unmeetable on one turning over hundreds (docs/adr/0004). Stage 3 reconciles
# its lenses to this same tolerance (thresholds.RECONCILE_REL_TOLERANCE).
RESIDUE_REL_TOLERANCE = 1e-9


def is_negligible(delta: float, *magnitudes: float) -> bool:
    """Is `delta` nothing but floating-point residue, next to these figures?
    With no magnitude to judge against, falls back to exact zero."""
    scale = max((abs(value) for value in magnitudes), default=0.0)
    if not scale:
        return delta == 0
    return abs(delta) <= RESIDUE_REL_TOLERANCE * scale


class PctChange(NamedTuple):
    """A percentage change, or why there is none."""

    value: float | None
    reason: str | None


def pct_change(current: float, previous: float, *magnitudes: float) -> PctChange:
    """Signed percentage change against a positive base; otherwise
    unavailable, with the reason (Thach, session 2E).

    Against a negative base the sign inverts: -100 -> -200 read +100% (a
    doubled loss as growth) and -100 -> +500 read -600% (a recovery as a
    collapse). Against zero there is nothing to divide by - 2A reported 0.0,
    "nothing moved", which is false when revenue appeared from nothing.
    Against residue the figure is astronomical and meaningless.

    `magnitudes` is the money that moved to produce the two figures (their
    gross): residue is judged against it. Judged only against the two nets, a
    residue base next to a month that also netted to residue was never
    negligible, and 0.1 + 0.2 - 0.3 -> 0 read -100% (2E doubt-review F6)."""
    if previous == 0:
        return PctChange(None, "there is no previous value to compare against, so there "
                               "is no percentage")
    # Residue of either sign before the sign test: a residue base is not a
    # loss, and calling -1e-17 "negative" misdescribed it (F9).
    if is_negligible(previous, current, previous, *magnitudes):
        # "Negligible", not only "residue": a real 0.01 against 31,000,000 is
        # no base either, and calling it float residue was false (F5).
        return PctChange(None, f"the previous value ({previous:.3g}) is floating-point "
                               "residue next to the money compared (under a billionth of "
                               "it), so it is no base for a percentage")
    if previous < 0:
        return PctChange(None, f"the previous value ({previous:,.2f}) is negative, so a "
                               "percentage change against it would invert its sign")
    return PctChange((current - previous) / previous * 100, None)
