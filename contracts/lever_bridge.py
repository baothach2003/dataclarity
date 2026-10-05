"""The lever's waterfall in diagnosis.json (`tree.lever.bridge`, 18.4; the
report redesign, step 1 - docs/REPORT_REDESIGN.md 1.2 and 2; CONTRACTS 7).

Here, out of contracts/diagnosis.py, for file size; the model that ties a
bridge to the lever's levels (`Lever`) stays there. The rounding rule lives
in this module ONCE: stage 3 allocates the cents with it and the contract
recomputes it, so the two cannot drift (doubt-review cycle 2 #4)."""

from decimal import ROUND_FLOOR, Decimal
from typing import Literal, Self

from pydantic import model_validator

from contracts._base import ContractModel
from contracts.lines import refuse_non_finite

BridgeWithheld = Literal["zero_orders", "month_not_positive", "not_to_the_cent"]
SplitWithheld = Literal["refund_lines", "aov_unchanged", "net_units_not_positive"]
# Level 2's reasons for being null, by the code the bridge withholds its split
# with - one copy: stage 3 writes them in `tree.lever.reasons["level2"]`, and
# the contract ties the code to them.
LEVEL2_NULL_REASONS = {
    "net_units_not_positive": "net units are not positive in both periods",
    "aov_unchanged": "AOV did not move, so level-2 effects cannot be scaled",
}


# A term this small beside the largest is float residue (as stage 3's
# RECONCILE tolerances read it), shown as no movement.
RESIDUE = 1e-9


def printed_cents(value: float) -> int:
    """The whole number of cents `f"{value:.2f}"` prints - how stage 5 shows a
    money figure (an exact half cent prints to even). The bridge carries its
    two ends in these cents (`shown_previous`, `shown_current`), so no other
    reader rounds them its own way (doubt-review cycle 2 #2)."""
    return int(Decimal(f"{value:.2f}").scaleb(2))


def floor_cents(value: float) -> int:
    """`value` in cents, rounded down, from its exact decimal repr."""
    return int((Decimal(repr(value)).scaleb(2)).to_integral_value(rounding=ROUND_FLOOR))


def allocate_cents(terms: list[float], total_cents: int) -> list[int] | None:
    """Each term in cents so they sum EXACTLY to `total_cents` - the
    largest-remainder rule (Thach, 2026-10-05, Q2): every term rounded down,
    then the cents left go one each to the terms with the largest remainders,
    a tie to the earlier term. The target is the printed months' difference,
    which can sit a cent UNDER the terms' own sum - a month ending on half a
    cent prints to even (310.375 prints 310.38, 620.125 prints 620.12) - and
    then the terms with the smallest remainders give a cent back, a tie to
    the later term.

    A term of exactly 0 - a factor that did not move - never takes or gives a
    cent: "4 -> 4 customers, +0.01" would state a movement that did not
    happen; nor does a positive term give back the cent that would show it
    below zero (doubt-review cycle 2 #3). Null when one cent each, among the
    terms that may move, cannot reach the target (float residue past a cent,
    at very large amounts) - never a crash, never a bar moved further."""
    # Float residue next to the largest term is no movement: it shows 0.00,
    # never -0.01 for a factor that did not move (cycle 3 #5; the F9 rule).
    scale = max((abs(term) for term in terms), default=0.0)
    terms = [0.0 if abs(term) <= RESIDUE * scale else term for term in terms]
    floors = [floor_cents(term) for term in terms]
    left = total_cents - sum(floors)
    if left == 0:
        return floors
    remainders = [Decimal(repr(term)).scaleb(2) - floor for term, floor in zip(terms, floors, strict=True)]
    if left > 0:
        movable = [index for index, term in enumerate(terms) if term != 0]
        order = sorted(movable, key=lambda index: (-remainders[index], index))
    else:
        movable = [index for index, (term, floor) in enumerate(zip(terms, floors, strict=True))
                   if term != 0 and not (term > 0 and floor <= 0)]
        order = sorted(movable, key=lambda index: (remainders[index], -index))
    if abs(left) > len(order):
        return None
    moved = set(order[:abs(left)])
    step = 1 if left > 0 else -1
    return [floor + (step if index in moved else 0) for index, floor in enumerate(floors)]


def as_shown(cents: int) -> float | None:
    """`cents` as the float a report shows, or None when the float does not
    print back to the same cents (past about 15 significant digits: the
    bridge is then withheld as `not_to_the_cent`, doubt-review cycle 2 #1)."""
    value = cents / 100
    return value if printed_cents(value) == cents else None


class BridgeBar(ContractModel):
    """One bar of the waterfall: a lever term, exact, and the cents it is
    shown at by `allocate_cents` - its term rounded down, or a cent either
    side of that."""

    factor: Literal["customers", "frequency", "orders", "aov", "units_per_order", "price_per_unit"]
    value_prev: float
    value_cur: float
    contribution: float
    shown: float

    @model_validator(mode="after")
    def _shown_within_a_cent(self) -> Self:
        refuse_non_finite(f"bar {self.factor!r}'s figures",
                          (self.value_prev, self.value_cur, self.contribution, self.shown))
        floor = floor_cents(self.contribution)
        # A residue term is shown as 0 (allocate_cents), which is floor + 1 of a
        # tiny negative and its floor otherwise - inside this band.
        if as_shown(printed_cents(self.shown)) != self.shown or printed_cents(self.shown) not in (
                floor - 1, floor, floor + 1):
            raise ValueError(f"bar {self.factor!r} shows {self.shown!r}: not its term {self.contribution!r} rounded "
                             "down, or a cent either side of that, to the cent")
        return self


class LeverBridge(ContractModel):
    """The waterfall the report draws (Thach, 2026-10-05, Q1, Q2): from last
    month's sales to this month's, one bar per lever term. The terms are the
    lever's own (level 1, and level 2's pair in place of AOV when
    `aov_split`); `shown` is `allocate_cents`' result, so the shown bars sum
    EXACTLY to `shown_change` = `shown_current` - `shown_previous`, the two
    months as stage 5 prints them - which a reader draws as the chart's ends,
    never formatting the revenue its own way. The split into items per order
    and price per item is withheld where stage 3 refuses basket size (B2:
    refund lines) or level 2 is null. Not the customer lens's bridge terms
    (`tree.customers`): this is the lever's."""

    revenue_previous: float
    revenue_current: float
    change: float
    shown_previous: float
    shown_current: float
    shown_change: float
    bars: list[BridgeBar]
    aov_split: bool
    aov_split_withheld: SplitWithheld | None

    @model_validator(mode="after")
    def _sums_exactly(self) -> Self:
        refuse_non_finite("the bridge's totals", (self.revenue_previous, self.revenue_current, self.change,
                                                  self.shown_previous, self.shown_current, self.shown_change))
        if self.change != self.revenue_current - self.revenue_previous:
            raise ValueError("bridge.change is revenue_current - revenue_previous")
        ends = (printed_cents(self.revenue_previous), printed_cents(self.revenue_current))
        if (self.shown_previous, self.shown_current) != (as_shown(ends[0]), as_shown(ends[1])):
            raise ValueError("bridge.shown_previous and shown_current are the months as stage 5 prints them")
        if min(ends) <= 0:
            raise ValueError("a bridge is drawn only between months that print above zero (month_not_positive)")
        if self.shown_change != as_shown(ends[1] - ends[0]):
            raise ValueError("bridge.shown_change is the printed months' difference, in whole cents")
        shown = [printed_cents(bar.shown) for bar in self.bars]
        if sum(shown) != ends[1] - ends[0]:
            raise ValueError("the bridge's shown bars do not sum to its shown change")
        if shown != allocate_cents([bar.contribution for bar in self.bars], ends[1] - ends[0]):
            raise ValueError("the bridge's shown bars are not the largest-remainder allocation of its terms")
        names = [bar.factor for bar in self.bars]
        if self.aov_split != (self.aov_split_withheld is None):
            raise ValueError("a bridge withholds the split exactly when it does not draw it")
        tail = ["units_per_order", "price_per_unit"] if self.aov_split else ["aov"]
        if names not in (["customers", "frequency", *tail], ["orders", *tail]):
            raise ValueError(f"bridge bars {names} are not level 1's terms with {tail} for the order value")
        return self
