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

from stages.diagnose.thresholds import RECONCILE_REL_TOLERANCE


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
