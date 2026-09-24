"""Comparing money that came out of floating-point arithmetic.

`x == 0` is the wrong question to ask about a figure produced by summing and
subtracting money. Two totals that are equal in the business sense routinely
differ by 1e-17, and every place that divides by such a difference turns that
residue into a headline number: stage 3 has now produced a gross-to-net ratio
of 4.5e15 (3C doubt-review) and a member share of -5.4e15 (3D doubt-review)
from exactly this mistake, in two different files, because each one wrote its
own `== 0` guard.

One helper, so the next place that divides by a difference inherits the guard
instead of rediscovering the bug.
"""

from collections.abc import Iterable

import pandas as pd

from stages.diagnose.thresholds import RECONCILE_REL_TOLERANCE, YOY_MIN_BASE_SHARE


def is_negligible(delta: float, *magnitudes: float) -> bool:
    """Is `delta` nothing but floating-point residue, next to these figures?

    Relative, because the residue scales with the numbers it came from: an
    absolute epsilon is either meaningless on a shop turning over millions or
    unmeetable on one turning over hundreds. With no magnitude to judge
    against, falls back to exact zero.
    """
    scale = max((abs(value) for value in magnitudes), default=0.0)
    if not scale:
        return delta == 0
    return abs(delta) <= RECONCILE_REL_TOLERANCE * scale


def typical_magnitude(values: Iterable[float]) -> float:
    """The size of a month this shop actually trades: the median of |value|
    over the non-zero values. NaN when there is none.

    One definition for two callers - the year-over-year base guard (3D6) and
    the masked-shift materiality floor (ADR-0007) - so "typical" cannot mean
    two different things in one diagnosis.

    Non-zero - and more than floating-point residue - because a month without
    rows is charted as 0.0: a stall open four months a year otherwise had a
    typical month of ZERO (3D6 doubt-review).
    A median, so one freak month cannot move it. A magnitude, so a series that
    nets negative in most months still has a size. NaN rather than 0 when
    nothing traded, so a caller comparing against it gets False, never a free
    pass.
    """
    finite = [abs(float(value)) for value in values if pd.notna(value)]
    scale = max(finite, default=0.0)
    # Residue is not trading: a month of cancelling sales and refunds nets
    # 1.4e-17, and an exact `!= 0` counted it, so three such months put the
    # typical month at 5.6e-17 (3D6b doubt-review cycle 2).
    magnitudes = [value for value in finite if not is_negligible(value, scale)]
    return float(pd.Series(magnitudes, dtype=float).median()) if magnitudes else float("nan")


def usable_base(base: float, typical: float, scale: float) -> bool:
    """May `base` - a year-ago month - be divided by? The year-over-year base
    guard (AI_PIPELINE 7.5, sessions 3D4 and 3D6), as ONE predicate.

    Positive (revenue is signed; two negatives divide to a confident
    positive), more than floating-point residue next to `scale`, and at least
    YOY_MIN_BASE_SHARE of `typical` (see `typical_magnitude`). A NaN base or a
    NaN typical fails every comparison and is refused - an unknown base is
    treated as too small, because refusing one only costs a finding while
    accepting one can fabricate it.

    Two callers divide by a year-ago month: step 4's year-over-year series and
    step 7's T2. They share this predicate so its three conditions cannot
    drift between them. Their `scale` arguments differ - step 4 passes the
    series' own maximum, T2 the maximum over the history window - which
    matters only for residue-sized bases (the 3D8 item).
    """
    if pd.isna(base):
        return False
    base = float(base)
    return (base > 0 and base >= YOY_MIN_BASE_SHARE * typical
            and not is_negligible(base, scale))
