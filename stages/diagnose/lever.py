"""Step 5, lever lens: revenue split into the levers a shop can actually pull
(docs/AI_PIPELINE.md section 7.6, docs/DIAGNOSE_DESIGN.md 5.5.2 - 5.5.4).

(DIAGNOSE_DESIGN 5.5.4's masked-shift rule is the frozen 3A record; the live
rule is AI_PIPELINE 7.6 and `_masked_shift` below.)

Level 1 asks how many customers bought, how often, and how much per order.
Level 2 opens the last of those: did the basket get smaller, or did prices
move? Both are Shapley decompositions, so neither answer depends on an order
someone picked (docs/adr/0004).
"""

from dataclasses import dataclass

import pandas as pd

from contracts.diagnosis import Lever, LeverFactor, LeverLevel
from shared.orders import count_orders
from shared.transactions import customer_identity, is_blank
from stages.diagnose.inputs import RunData, period_mask
from stages.diagnose.shapley import shapley_product
from stages.diagnose.numbers import is_negligible, typical_magnitude
from stages.diagnose.thresholds import MASKED_GROSS_TO_NET, MASKED_MIN_CONTRIBUTION_SHARE


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
        # BUYERS - customers with a sale row (2E doubt-review F1): a customer
        # who only returned goods is active (3C) but has no orders, and
        # counting them made frequency fall on refunds alone ("customers
        # bought less often", -3,892 against a -310 change). Stage 2 reports
        # the same count as core.buyers_*; the identity customers x
        # (orders / customers) x AOV is net revenue whichever count is used.
        identified = mask & data.parsed.sale & ~is_blank(data.df[customer_col])
        customers = int(customer_identity(data.df.loc[identified, customer_col]).nunique())
    return PeriodTotals(
        revenue=float(data.parsed.revenue_amounts[mask].sum()),
        # Distinct orders among the sale rows (shared/orders.py, 2E-e): order
        # ids when order_id is mapped, else each sale line - as stage 2 counts.
        orders=count_orders(data.parsed.order_key, mask & data.parsed.sale),
        customers=customers,
        # Sale and return lines' units (shared/transactions.py, 2E-c): a free
        # gift's quantity is not a unit in the basket.
        units=float(data.parsed.units[mask].sum()),
    )


def compute_lever(data: RunData, history: list[str]) -> Lever:
    previous = period_totals(data, data.metrics.period.previous)
    current = period_totals(data, data.metrics.period.current)
    has_customers = data.parsed.reverse.get("customer") is not None

    reasons: dict[str, str] = {}
    level1 = _level1(previous, current, has_customers, reasons)
    level2 = _level2(previous, current, level1, reasons)
    gross_to_net = _gross_to_net(previous, current, level1, reasons)
    typical = typical_magnitude(month_revenue(data, month) for month in history)
    pair = _orders_aov_pair(level1, previous, current)
    alert = _masked_shift(pair, gross_to_net, typical,
                          previous.revenue, current.revenue, reasons)
    return Lever(
        level1=level1,
        level2=level2,
        gross_to_net=gross_to_net,
        masked_shift_alert=alert,
        masked_shift_pair=pair,
        reasons=reasons,
    )


def _orders_aov_pair(level1: LeverLevel | None, previous: PeriodTotals,
                     current: PeriodTotals) -> LeverLevel | None:
    """Level 1 re-split as orders x AOV, the pair the masked-shift alert is
    decided on (Thach, 3D6b).

    customers x frequency = orders BY DEFINITION, so whenever orders hold
    steady and the customer count moves, those two factors cancel exactly: ten
    customers ordering once becoming five ordering twice gave customers -750
    against frequency +750 on a flat month, and the alert fired on an identity.
    On that noise structure it fired on 19-39% of months with nothing planted;
    on this pair, 0-2.4%. S6 (customers -40%, AOV +40%) is caught identically
    without noise and 0.2-1.8 points less often with it (scratchpad
    pair_sweep.out). Orders and AOV have no definitional
    link between them. The customers/frequency story stays in level 1,
    descriptive, and in B1 and C1.

    Built from the same period totals level 1 used - the integer order count
    and revenue / orders - not rebuilt as customers x frequency, which gave
    29.000000000000004 for 7 customers placing 29 orders (pair review #8).
    Null exactly when level 1 is (a period with no orders).
    """
    if level1 is None:
        return None
    pair = {period: {"orders": float(totals.orders), "aov": totals.revenue / totals.orders}
            for period, totals in (("prev", previous), ("cur", current))}
    contributions = shapley_product(pair["prev"], pair["cur"])
    return LeverLevel(formula="orders*aov", factors=[
        LeverFactor(name=name, value_prev=pair["prev"][name],
                    value_cur=pair["cur"][name], contribution=contributions[name])
        for name in ("orders", "aov")])


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
    if is_negligible(delta_aov, aov_prev, aov_cur):
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
    if is_negligible(delta_revenue, previous.revenue, current.revenue):
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
    pair: LeverLevel | None, gross_to_net: float | None, typical: float,
    revenue_prev: float, revenue_cur: float, reasons: dict[str, str],
) -> bool | None:
    """A flat total hiding large offsetting movements - the case a "did revenue
    move?" report misses entirely (docs/DIAGNOSE_DESIGN.md 1.2).

    Decided on the tree alone (ADR-0007). It used to need a step-4 signal on a
    component as well, and since no step-4 row is a verdict any more that
    half had nothing left to stand on. What remains, against one FLOOR:

        floor = MASKED_MIN_CONTRIBUTION_SHARE
                * max(typical month, |previous month|, |current month|)

    - MATERIAL: on the orders x AOV pair (`_orders_aov_pair`), one
      contribution of each sign, each at least the floor;
    - FLAT: the revenue change is under MASKED_MIN_CONTRIBUTION_SHARE times
      the larger COMPARED month - not the floor above, which a trough's
      typical month dominates - and `gross_to_net >= MASKED_GROSS_TO_NET`
      (or revenue did not move at all).

    Why the floor takes the LARGEST of the three (Thach, 3D6b doubt-review).
    The typical month alone - median |revenue| over the history's trading
    months - is small against a peak: a trickle off-season shop's typical
    month was 300 against in-season months of 500,000, so a 1% composition
    wiggle cleared a floor of 60, and on a noise model the alert fired on
    15-25% of peak months with nothing planted. The floor must scale with the
    months being compared. It never drops below 20% of the typical month, so a
    bad last month cannot shrink it either - 20% of a bad month is a small
    move on this shop. It scales UP only: in a trough the floor stays at 20%
    of the typical month, so a masked shift there counts only when both
    sides moved by that much - e.g. orders 20 -> 2 against AOV 10 -> 100 on
    a flat 200 - and rarely fires otherwise (0.1% detection of a planted 30%
    shift at 0.3x typical on the sweep's noise model; a rate, not a bound).

    Why flatness needs a bound on the change, measured against the COMPARED
    months. By the ratio alone, a month that went from 1,000 to 2,000 has
    `gross_to_net` 3.5 and is "flat", and headline rule 4 would call a
    doubled month stable. The first version measured the change against the
    materiality floor, and in a trough that floor is 20% of a typical month
    far larger than the months compared: a month that fell 200 -> 50 (-75%)
    passed as flat and fired (pair review #2, a fabrication).

    **The ratio test, kept as Thach's decision states it, and what it does.**
    Over the PAIR it is implied: with P and N the positive and negative sums
    of the pair, the change is P - N (Shapley efficiency) and the pair's
    gross is P + N; both clear the materiality floor, and the change is under
    the flatness bound, which is never larger than that floor, so gross =
    |P - N| + 2 * min(P, N) > 3 * |change| while MASKED_GROSS_TO_NET <= 3
    (pinned by a test). The check itself reads the reported `gross_to_net`,
    over the THREE-factor level 1, and that is NOT implied: its AOV term
    differs from the pair's by a customers-frequency-AOV interaction, and the
    pair review built a case with 2.975 against the pair's 3.05. So it is
    live. It can only REMOVE an alert - the safe direction - and a test pins
    it. An earlier version of this docstring said it never bound, on 12,000
    random draws of which only 338 fired the pair and none sat in a trough.
    Under the shipped bound a targeted search of 400,000 extreme shapes found
    no case where it blocks (lowest ratio among 16,968 firing: 3.43), while
    the same search on the first bound found 169 - measured, not proven.

    With no trading month in the history there is no typical month, the check
    cannot run, and the alert is null with a reason - never false.

    Nothing here establishes that the movement was UNUSUAL, only that it was
    large and cancelled out. A seasonal shoulder month has exactly that shape,
    so headline rule 4 always words it as a movement that may be seasonal.
    """
    if pair is None:
        # Level 1 is null, and its own reason explains this (CONTRACTS 7).
        return None
    if not typical > 0:
        reasons["masked_shift_alert"] = (
            "no complete trading month in the history window, so there is no "
            "typical month to measure a material move against")
        return None
    if revenue_prev <= 0 or revenue_cur <= 0:
        # A month that netted zero or below makes AOV zero or negative, and
        # the Shapley terms of a product then change sign: a shop whose
        # customers went 10 -> 100 while revenue went -500 -> +300 had a
        # customers contribution of -2,115, and rule 4 would have told the
        # reader more customers pulled revenue down (3D6b doubt-review cycle 2).
        # The same principle as 3D4's base guard: a non-positive month is not
        # something a multiplicative split can read.
        reasons["masked_shift_alert"] = (
            "a compared month netted zero or below, so its multiplicative "
            "split cannot be read as offsetting movements")
        return None
    floor = MASKED_MIN_CONTRIBUTION_SHARE * max(typical, abs(revenue_prev), abs(revenue_cur))
    bound = MASKED_MIN_CONTRIBUTION_SHARE * max(abs(revenue_prev), abs(revenue_cur))
    flat = (abs(revenue_cur - revenue_prev) < bound
            and (gross_to_net is None or gross_to_net >= MASKED_GROSS_TO_NET))
    contributions = [factor.contribution for factor in pair.factors]
    material = (any(value >= floor for value in contributions)
                and any(value <= -floor for value in contributions))
    return flat and material


def returns_levels(data: RunData) -> dict[str, float]:
    """Gross sales, returns and deductions per period, the additive returns
    lens: `delta_net = delta_gross - delta_returns - delta_deductions`.

    The three are `shared/transactions.py`'s sale, return and deduction rows.
    Gross used to be every quantity > 0 row, so a refund booked at a negative
    price sat inside gross sales and the product lens read it as a price cut -
    P1 headlined "like-for-like prices changed" when none had (2E-b review).
    A deduction (a coupon, a discount, a write-off) is neither a sale nor a
    return, so it has a term of its own and no hypothesis in v1: a change it
    carries stays unexplained (Thach, 2E-c).
    """
    levels = {}
    parsed = data.parsed
    for label, month in (("prev", data.metrics.period.previous),
                         ("cur", data.metrics.period.current)):
        mask = period_mask(data, month)
        amounts = parsed.revenue_amounts
        # `+ 0.0` normalises the negative zero that negating an empty sum
        # produces, which would otherwise be written into the contract file
        # literally as `-0.0`.
        levels[f"gross_{label}"] = float(amounts[mask & parsed.sale].sum()) + 0.0
        levels[f"returns_{label}"] = -float(amounts[mask & parsed.returned].sum()) + 0.0
        levels[f"deductions_{label}"] = -float(amounts[mask & parsed.deduction].sum()) + 0.0
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
