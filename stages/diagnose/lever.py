"""Step 5, lever lens: revenue split into the levers a shop can actually pull
(docs/AI_PIPELINE.md section 7.6, docs/DIAGNOSE_DESIGN.md 5.5.2 - 5.5.4).

Level 1 asks how many customers bought, how often, and how much per order.
Level 2 opens the last of those: did the basket get smaller, or did prices
move? Both are Shapley decompositions, so neither answer depends on an order
someone picked (docs/adr/0004).
"""

from dataclasses import dataclass

import pandas as pd

from contracts.diagnosis import Lever, LeverFactor, LeverLevel, Signal
from shared.transactions import customer_identity, is_blank
from stages.diagnose.inputs import RunData, period_mask
from stages.diagnose.shapley import shapley_product
from stages.diagnose.thresholds import MASKED_GROSS_TO_NET, RECONCILE_REL_TOLERANCE

# Level-1 factor names mapped to the step-4 series that tracks the same thing,
# so the masked-shift alert can ask "is any of these actually unusual?".
COMPONENT_SERIES = {
    "customers": "active_customers",
    "frequency": "frequency",
    "orders": "orders",
    "aov": "aov",
}
FIRED = ("above", "below")


@dataclass(frozen=True)
class PeriodTotals:
    """One month's raw totals, from which every lever factor is derived."""

    revenue: float
    orders: int
    customers: int
    units: float


def period_totals(data: RunData, month: str) -> PeriodTotals:
    mask = period_mask(data, month)
    customer_col = data.parsed.reverse.get("customer")
    if customer_col is None:
        customers = 0
    else:
        identified = mask & ~is_blank(data.df[customer_col])
        customers = int(customer_identity(data.df.loc[identified, customer_col]).nunique())
    return PeriodTotals(
        revenue=float(data.parsed.revenue_amounts[mask].sum()),
        orders=int(mask.sum()),
        customers=customers,
        units=float(data.parsed.quantities[mask].sum()),
    )


def compute_lever(data: RunData, signals: list[Signal]) -> Lever:
    previous = period_totals(data, data.metrics.period.previous)
    current = period_totals(data, data.metrics.period.current)
    has_customers = data.parsed.reverse.get("customer") is not None

    reasons: dict[str, str] = {}
    level1 = _level1(previous, current, has_customers, reasons)
    level2 = _level2(previous, current, level1, reasons)
    gross_to_net = _gross_to_net(previous, current, level1, reasons)
    return Lever(
        level1=level1,
        level2=level2,
        gross_to_net=gross_to_net,
        masked_shift_alert=_masked_shift(level1, gross_to_net, signals),
        reasons=reasons,
    )


def _level1(
    previous: PeriodTotals, current: PeriodTotals, has_customers: bool,
    reasons: dict[str, str],
) -> LeverLevel | None:
    """`revenue = customers * frequency * aov`, or `orders * aov`.

    Zero orders in a period leaves AOV as 0/0 and the whole decomposition
    undefined; the lens says so rather than substituting a zero, which would
    report "AOV contributed +50" for a shop's opening month (Thach, 3C).

    Zero *identified customers* with orders present is different: it happens
    when every row of a month has a blank customer, and it is the same
    practical situation as an unmapped customer column - so it takes the same
    two-factor fallback, which is still exact and still informative.
    """
    for label, totals in (("previous", previous), ("current", current)):
        if totals.orders == 0:
            reasons["level1"] = f"zero orders in the {label} period"
            return None

    if has_customers and previous.customers > 0 and current.customers > 0:
        names = ("customers", "frequency", "aov")
        values = {
            period: {
                "customers": float(totals.customers),
                "frequency": totals.orders / totals.customers,
                "aov": totals.revenue / totals.orders,
            }
            for period, totals in (("prev", previous), ("cur", current))
        }
        formula = "customers*frequency*aov"
    else:
        if has_customers:
            reasons["level1_form"] = (
                "no identified customers in one period; "
                "fell back to the two-factor form"
            )
        names = ("orders", "aov")
        values = {
            period: {
                "orders": float(totals.orders),
                "aov": totals.revenue / totals.orders,
            }
            for period, totals in (("prev", previous), ("cur", current))
        }
        formula = "orders*aov"

    contributions = shapley_product(values["prev"], values["cur"])
    return LeverLevel(
        formula=formula,
        factors=[
            LeverFactor(name=name, value_prev=values["prev"][name],
                        value_cur=values["cur"][name], contribution=contributions[name])
            for name in names
        ],
    )


def _level2(
    previous: PeriodTotals, current: PeriodTotals, level1: LeverLevel | None,
    reasons: dict[str, str],
) -> LeverLevel | None:
    """`aov = units_per_order * price_per_unit`, converted into revenue units.

    The conversion is `phi_aov * phi_k / delta_aov`, which is exact because the
    two level-2 contributions sum to `delta_aov` - so the converted pair sums
    to AOV's own level-1 contribution and the tree stays reconciled.
    """
    if level1 is None:
        reasons["level2"] = "level 1 could not be computed"
        return None
    if previous.units <= 0 or current.units <= 0:
        # Net of returns, a month can legitimately ship fewer units than came
        # back. Units per order is then negative or zero and the split says
        # nothing about prices.
        reasons["level2"] = "net units are not positive in both periods"
        return None

    values = {
        period: {
            "units_per_order": totals.units / totals.orders,
            "price_per_unit": totals.revenue / totals.units,
        }
        for period, totals in (("prev", previous), ("cur", current))
    }
    aov_prev = previous.revenue / previous.orders
    aov_cur = current.revenue / current.orders
    delta_aov = aov_cur - aov_prev
    if _is_negligible(delta_aov, aov_prev, aov_cur):
        # The pair can still be moving in opposite directions here, which is
        # interesting - but the conversion into revenue units divides by this,
        # so the lens reports that it cannot say rather than inventing a scale.
        #
        # The test is relative, not `== 0`: two AOVs that are equal in the
        # business sense differ by float residue often enough that an exact
        # comparison walks straight past. One real file gave delta_aov of
        # -2.8e-17 and the lens dutifully reported that basket size added 4.5p
        # and price removed 4.5p - figures 10^15 times larger than the quantity
        # they decompose (3C doubt-review R1a).
        reasons["level2"] = "AOV did not move, so level-2 effects cannot be scaled"
        return None

    phi_aov = next(f.contribution for f in level1.factors if f.name == "aov")
    contributions = shapley_product(values["prev"], values["cur"])
    return LeverLevel(
        formula="units_per_order*price_per_unit",
        factors=[
            LeverFactor(
                name=name,
                value_prev=values["prev"][name],
                value_cur=values["cur"][name],
                contribution=phi_aov * contributions[name] / delta_aov,
            )
            for name in ("units_per_order", "price_per_unit")
        ],
    )


def _is_negligible(delta: float, previous: float, current: float) -> bool:
    """Is this change nothing but floating-point residue?

    Relative, because these are money figures whose residue scales with them:
    an absolute epsilon is either meaningless on a shop turning over millions
    or unmeetable on one turning over hundreds.
    """
    scale = max(abs(previous), abs(current))
    return abs(delta) <= RECONCILE_REL_TOLERANCE * scale if scale else delta == 0


def _gross_to_net(
    previous: PeriodTotals, current: PeriodTotals, level1: LeverLevel | None,
    reasons: dict[str, str],
) -> float | None:
    """This function owns every reason it is responsible for, including the
    one for an absent level 1: having `_level1` write `reasons["gross_to_net"]`
    made the contract's "every null field carries a reason" rule depend on two
    functions staying in step (3C doubt-review, optional)."""
    if level1 is None:
        reasons["gross_to_net"] = reasons.get("level1", "level 1 could not be computed")
        return None
    delta_revenue = current.revenue - previous.revenue
    if _is_negligible(delta_revenue, previous.revenue, current.revenue):
        # Infinity is not representable in JSON, and this is precisely the
        # masked case: the components moved and the total did not. The guard is
        # relative for the same reason as level 2's - an exact `== 0` let a
        # residue of -5.6e-17 through and produced a gross-to-net ratio of
        # 4.5e15, which would fire the masked-shift alert on a flat month
        # (3C doubt-review R1b).
        reasons["gross_to_net"] = "revenue did not move, so the ratio has no denominator"
        return None
    return sum(abs(factor.contribution) for factor in level1.factors) / abs(delta_revenue)


def _masked_shift(
    level1: LeverLevel | None, gross_to_net: float | None, signals: list[Signal]
) -> bool | None:
    """A flat total hiding large offsetting movements - the case a "did revenue
    move?" report misses entirely (docs/DIAGNOSE_DESIGN.md 1.2).

    Both halves are required. The ratio alone fires on tiny changes, where
    components routinely dwarf a near-zero net; a step-4 signal alone is just
    an unusual month. Together they say: something moved enough to be unusual,
    and the total is hiding it.
    """
    if level1 is None:
        return None
    fired = {signal.series for signal in signals if signal.signal in FIRED}
    moved = any(
        COMPONENT_SERIES[factor.name] in fired for factor in level1.factors
    )
    if gross_to_net is None:  # revenue did not move at all
        return moved
    return gross_to_net >= MASKED_GROSS_TO_NET and moved


def returns_levels(data: RunData) -> dict[str, float]:
    """Gross sales and returns per period, the additive returns lens.

    `returns_*` are positive magnitudes, so `delta_net = delta_gross -
    delta_returns`. A return is a counted row with negative quantity - the one
    signal the canonical schema carries (`shared/transactions.py`).
    """
    levels = {}
    for label, month in (("prev", data.metrics.period.previous),
                         ("cur", data.metrics.period.current)):
        mask = period_mask(data, month)
        quantities = data.parsed.quantities
        amounts = data.parsed.revenue_amounts
        # `+ 0.0` normalises the negative zero that negating an empty sum
        # produces, which would otherwise be written into the contract file
        # literally as `-0.0`.
        levels[f"gross_{label}"] = float(amounts[mask & (quantities > 0)].sum()) + 0.0
        levels[f"returns_{label}"] = -float(amounts[mask & (quantities < 0)].sum()) + 0.0
    return levels


def month_revenue(data: RunData, month: str) -> float:
    return float(data.parsed.revenue_amounts[period_mask(data, month)].sum())


def customer_revenue(data: RunData, month: str, customer_col: str) -> pd.Series:
    """Net revenue per identified customer in one month, returns included.

    Grouped on the normalised identity (3C2): keyed raw, one customer written
    two ways appears in the bridge as two people, and if the two spellings
    fall either side of the period boundary they read as one lapsing and one
    arriving.
    """
    mask = period_mask(data, month) & ~is_blank(data.df[customer_col])
    identity = customer_identity(data.df.loc[mask, customer_col])
    return data.parsed.revenue_amounts[mask].groupby(identity).sum()
