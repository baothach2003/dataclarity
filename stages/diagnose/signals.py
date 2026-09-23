"""Step 4: is this change unusual, or is it Tuesday?
(docs/AI_PIPELINE.md section 7.5)

Comparing two points always produces a difference, and a report that explains
every difference is a report that cries wolf. This step puts limits around each
series computed from its own history - a process behaviour (XmR) chart - so the
engine can say "within normal variation" and mean it.

Two detection rules only. More rules catch more, and raise more false alarms;
the engine's credibility rests on the months it says nothing happened.
"""

import pandas as pd

from contracts.diagnosis import Signal
from shared.transactions import customer_identity, is_blank
from stages.diagnose.inputs import RunData, shift_month
from stages.diagnose.numbers import is_negligible
from stages.diagnose.thresholds import (
    XMR_FACTOR,
    XMR_MEDIAN_FACTOR,
    XMR_MIN_BASELINE_POINTS,
    XMR_MIN_SPREAD_RATE,
    XMR_MIN_SPREAD_SHARE,
    XMR_MIN_SPREAD_YOY_POINTS,
    XMR_REL_TOLERANCE,
    XMR_RESIDUE_FLOOR,
    XMR_RUN_LENGTH,
    YOY_LAG_MONTHS,
    YOY_MIN_BASE_SHARE,
    YOY_MODE_MIN_MONTHS,
)

# Every series the step reports on, in output order. `active_customers` and
# `frequency` need a mapped customer column and are dropped without one.
SERIES = (
    "revenue",
    "orders",
    "active_customers",
    "frequency",
    "aov",
    "units_per_order",
    "price_per_unit",
    "return_rate",
)
CUSTOMER_SERIES = ("active_customers", "frequency")
# Series that are a fraction of orders rather than money or a count; they need
# a floor expressed in the same units (see XMR_ABS_FLOOR_RATE).
RATE_SERIES = ("return_rate",)


def compute_signals(data: RunData, history: list[str]) -> list[Signal]:
    table = monthly_series(data)
    current = data.metrics.period.current

    if table.empty or not len(table.columns):
        # A file that starts mid-month has no complete month at all, so there
        # is no series to chart. The contract says "no baseline" is spelled
        # `insufficient_history`, not an empty array - step 5-7 consumers look
        # for the revenue entry and must find one saying so, rather than
        # nothing at all (3B doubt-review finding 6).
        reported = [name for name in SERIES if name not in CUSTOMER_SERIES
                    or data.parsed.reverse.get("customer") is not None]
        return [_no_baseline(name, "level", "too_few_points")
                for name in reported]

    yoy_ready = len(data.complete_months) >= YOY_MODE_MIN_MONTHS
    yoy = _as_yoy(table, history) if yoy_ready else None

    signals = []
    for name in SERIES:
        if name not in table.columns:
            continue
        # Mode is decided per series, on whether YoY actually yields a usable
        # baseline - not on the month count alone. A single zero or missing
        # month in the file's first year leaves one YoY point NaN, and at the
        # threshold that is the difference between eight baseline points and
        # seven: without this fallback, adding a month of history turns a
        # correctly detected collapse into "we cannot say" (3B doubt-review
        # finding 1). It also keeps `mode` honest per row, rather than
        # labelling every series `yoy` while only some of them have limits.
        # ...and on whether the CURRENT month has a year-ago comparator at
        # all. Without this second test a shop that was shut this month last
        # year reports `insufficient_history` on an 80% collapse, because the
        # series it was charted against has no value for the month being
        # judged - while the level chart would have caught it instantly. That
        # is 3B doubt-review finding 1 in its mirror image: that fix asked
        # whether the HISTORY yields usable points and never asked about the
        # month the whole report is about (3D2 doubt-review R3).
        ready = yoy is not None and _usable(yoy[name], history) >= XMR_MIN_BASELINE_POINTS
        if ready and not pd.isna(yoy[name].get(current, float("nan"))):
            signals.append(_signal_for(name, yoy[name], current, history, "yoy"))
        else:
            # Record WHY a series that could have charted year over year is
            # not doing so. The fallback is not always an improvement: on a
            # seasonal shop the level limits are wide enough to swallow a real
            # 50% collapse, so this series says `within` where the
            # year-over-year chart said `below` (3D4 doubt-review C3).
            fallback = _fallback_reason(data, current) if ready else None
            # Level mode, and level mode alone, is what this file supports for
            # this series. The row is DESCRIPTIVE: it is computed, written and
            # shown, and step 7 does not read it as a judgement about the
            # month (contracts.diagnosis.is_verdict, ADR-0006).
            #
            # Session 3D5 gated this fallback instead - refusing a chart too
            # wide to see a halving, then one whose centre sat off the month's
            # own season. Both were deleted by that ADR. The second could not
            # run on a 24-month file at all: the history window holds one
            # prior occurrence of the current calendar month, and that
            # occurrence is the comparator whose failure put the series here.
            signals.append(_signal_for(name, table[name], current, history,
                                       "level", fallback))
    return signals


def _fallback_reason(data: RunData, current: str) -> str:
    """Was the year-ago month absent, or present but unusable as a base?

    Two different facts about the shop, and step 7 should be able to tell them
    apart: "we were shut that month" is a gap, "that month netted zero or
    below" - or, since 3D6, was too small to divide by - is a business event.

    The test is `months_with_rows`, not the series value, because
    `monthly_series` charts a month holding no rows as 0.0 - so at that layer
    a shut month and a month that genuinely netted zero are identical. That
    fabricated zero is a pre-existing defect in its own right: `inputs.py`
    says "a month with no rows is evidence of a gap, never evidence of what
    normal looks like" (3B finding 2) and then the series is built from
    `complete_months` anyway. Recorded for its own session; here it is enough
    to ask the right source.
    """
    year_ago = shift_month(current, -YOY_LAG_MONTHS)
    return ("unusable_year_ago_base" if year_ago in data.months_with_rows
            else "no_year_ago_value")


def _usable(column: pd.Series, history: list[str]) -> int:
    return int(column.reindex(history).notna().sum())


def _no_baseline(name: str, mode: str, reason: str,
                 fallback: str | None = None) -> Signal:
    """`reason` is required and has no default. It used to default to
    `too_few_points`, so a caller that forgot it got a plausible wrong answer
    instead of an error - which is the defect this field was added to fix,
    reproduced in the helper that reports it (3D5b review R6)."""
    return Signal(series=name, mode=mode, value_cur=None, center=None, lower=None,
                  upper=None, signal="insufficient_history", rule=None,
                  limits_method="mean_moving_range", mode_fallback=fallback,
                  insufficient_reason=reason)


def monthly_series(data: RunData) -> pd.DataFrame:
    """One row per complete month, one column per series, chronological.

    Revenue, orders and active customers are computed exactly as stage 2
    computes them (`shared/transactions.py` decides what a counted row is), so
    the two stages cannot disagree about the same month - the consistency test
    pins that.
    """
    counted = data.parsed.counted
    months = data.months
    customer_col = data.parsed.reverse.get("customer")

    rows = []
    for month in data.complete_months:
        mask = counted & (months == month)
        revenue = float(data.parsed.revenue_amounts[mask].sum())
        orders = int(mask.sum())
        units = float(data.parsed.quantities[mask].sum())
        returns = int((data.parsed.quantities[mask] < 0).sum())

        row: dict[str, float] = {
            "revenue": revenue,
            "orders": float(orders),
            "aov": revenue / orders if orders else 0.0,
            "units_per_order": units / orders if orders else 0.0,
            "price_per_unit": revenue / units if units else 0.0,
            "return_rate": returns / orders if orders else 0.0,
        }
        if customer_col is not None:
            identified = mask & ~is_blank(data.df[customer_col])
            # Normalised identity (3C2), matching stage 2's active_customers:
            # the consistency test compares these two figures directly.
            customers = int(customer_identity(data.df.loc[identified, customer_col]).nunique())
            row["active_customers"] = float(customers)
            row["frequency"] = orders / customers if customers else 0.0
        rows.append(row)

    table = pd.DataFrame(rows, index=pd.Index(data.complete_months, name="month"))
    return table[[name for name in SERIES if name in table.columns]]


def _as_yoy(table: pd.DataFrame, history: list[str]) -> pd.DataFrame:
    """Year-over-year percentage change, which removes seasonality so a
    December is compared with a December.

    A month whose year-ago counterpart is missing has no YoY value: it is left
    NaN rather than folded to 0.0. `pct_change`'s zero-denominator convention
    is right for a headline figure that must show a number, and wrong inside a
    statistical series, where a fabricated 0% would pull the centre line and
    tighten the limits.

    **The base must be POSITIVE, not merely non-zero** (3D4). Dividing by a
    negative month is not a growth rate: two negatives make a confident
    positive, so a shop whose month went from -100 to -200 - twice the loss -
    reported +100% and fired rule 1, the rule step 7 acts on. The mirror is
    worse: a recovery from -100 to +500 divides to -600%, so getting better
    reads as a collapse.

    Which series this reaches: **every series built from signed money**, which
    is `revenue`, `aov`, `units_per_order` and `price_per_unit`. The counts
    (`orders`, `active_customers`, `frequency`) and the `return_rate` fraction
    cannot be negative, so `> 0` is exactly the old `!= 0` for them and
    nothing about them changes.

    `price_per_unit` was claimed in this docstring to be immune, on the
    grounds that it is revenue over units so both parts flip together in a
    refund-heavy month. **That is false**, and the sweep offered as evidence
    could not have shown otherwise - every fixture in it used a single price,
    which makes `price_per_unit` arithmetically constant. Revenue and units
    disagree in sign whenever the refunded items are priced differently from
    the sold ones: one sale of 1 at 1000 against four refunds of 3 at 50
    leaves revenue at +400 and price per unit at -36.36. The base guard is
    load-bearing for four series, not three.

    The base must also be more than floating-point residue, not merely
    positive. `thresholds.py` records that a month whose sales and returns
    cancel leaves 4.4e-16 rather than 0.0, and `> 0` admits that as a
    denominator: a real file produced a year-over-year figure of 7.2e21 per
    cent from a base of 1.4e-17. `is_negligible` is the helper this codebase
    already wrote for "is this difference real", and `numbers.py` says it
    exists "so the next place that divides by a difference inherits the guard
    instead of rediscovering the bug" - this function was the fourth place to
    rediscover it.

    **And the base must be big enough to divide by** (3D6). Positive and more
    than residue still admits 12.50 on a shop turning over 50,000, which
    divides to +399,900% - and since ADR-0006 that is an actionable rule-1
    verdict, on a month where nothing happened, that also fires the
    masked-shift alert. The same base inside the baseline drags the mean
    centre tens of thousands of points away, so every ordinary month fires.
    A base below `YOY_MIN_BASE_SHARE` of the series' typical magnitude is
    refused; `thresholds.py` says why typical is the median of |value| over
    the trading months of `history`, and why the share is a policy rather
    than a measurement.

    Non-finite results are dropped last. A denormal base overflows the
    division: 5e-324 against 1000 gives `inf`, which `pd.isna` does not catch,
    and the contract's finiteness validator would then abort the whole stage
    rather than let one series degrade.

    Since 3D6 two of the older checks are IMPLIED by the share and are kept
    as defence: the floor is positive whenever the history has a trading
    month, so it refuses a negative or zero base, and a base that clears the
    residue test cannot overflow the division. Their mutants survive for that
    reason. The residue test is NOT implied: the floor is a median, so when
    HALF the trading months are themselves residue-sized a residue base
    clears it (3D6 doubt-review cycle 2) - `test_yoy_small_base.py` pins it.

    **Refusing a base is only certainly safe for the CURRENT comparator**,
    where it removes a verdict and nothing else. Refusing a BASELINE base
    removes a point from the chart, which moves the centre either way, and
    the share only removes the cliff below 3%: bases from 3.5% to 25% still
    drag the centre into an actionable verdict. `thresholds.py` lists what
    this guard does not fix; PROJECT_PLAN 3D9 owns it.
    """
    values = {}
    for name in table.columns:
        column = table[name]
        previous = pd.Series(
            [column.get(shift_month(month, -YOY_LAG_MONTHS), float("nan"))
             for month in column.index],
            index=column.index)
        scale = float(column.abs().max() or 0.0)
        # A window with no values has no typical level (NaN), and `>=` against
        # NaN is False, so every base is refused. That is deliberate: a base
        # not known to be big enough is treated as too small, because
        # refusing one only costs a verdict while accepting one can fabricate
        # it. Reached whenever every history month is zero - `return_rate` on
        # a shop with no returns, the commonest case - where it is harmless,
        # because every base is then zero and refused anyway.
        # Over the months the shop TRADED. A month without rows is charted as
        # 0.0, so a stall open four months a year had a median of zero, a
        # floor of zero, and a 12.50 base divided to +399,900% exactly as
        # before this guard existed (3D6 doubt-review).
        magnitude = column.reindex(history).abs()
        typical = float(magnitude[magnitude > 0].median())
        usable = (previous > 0) & (previous >= YOY_MIN_BASE_SHARE * typical) & ~previous.apply(
            lambda base: is_negligible(float(base), scale) if pd.notna(base) else True)
        previous = previous.where(usable)
        change = (column - previous) / previous * 100
        values[name] = change.replace([float("inf"), float("-inf")], float("nan"))
    return pd.DataFrame(values, index=table.index)


def _signal_for(
    name: str, column: pd.Series, current: str, history: list[str], mode: str,
    fallback: str | None = None,
) -> Signal:
    baseline = column.reindex(history).dropna()
    value_cur = column.get(current, float("nan"))

    if len(baseline) < XMR_MIN_BASELINE_POINTS:
        return _no_baseline(name, mode, "too_few_points")
    if pd.isna(value_cur):
        # A complete baseline and nothing to judge against it: `aov` on a month
        # with no orders, for instance. Reporting `too_few_points` here would
        # be the one explanation that is not true, and step 7 cannot tell "this
        # shop is too new" from "this shop had no orders last month" if the
        # field says the same thing for both.
        return _no_baseline(name, mode, "no_current_value")

    center = float(baseline.mean())
    # The moving range of consecutive points is what makes these limits robust
    # to a trend: a slow drift inflates it far less than the standard deviation
    # of the whole series would.
    spread, limits_method = _spread(baseline)
    minimum = _minimum_spread(name, mode, center)
    if minimum > spread:
        # The floor can widen a measured chart, so its SIZE is what keeps it
        # honest. At 2% of the centre it silenced a 2% drop on a shop turning
        # over 1,000,000 a month whose ordinary variation is 0.2% - a
        # ten-sigma event and the most important line in that report (3D3
        # doubt-review C1). The floors are now tuned against the cases that
        # must fire as well as the ones that must stay quiet; see
        # thresholds.py.
        spread, limits_method = minimum, "minimum_spread"
    if spread <= 0:
        # No measured variation AND no scale to borrow: a money series whose
        # every baseline month netted exactly zero has neither. Inventing a
        # currency floor here would be picking a number out of the air, and
        # zero-width limits call one cent a special cause, so the honest
        # answer is that this series cannot be charted (3D3 doubt-review R1).
        # The reason is NOT `too_few_points`: the points are all there, and
        # sending a reader after more history would not help (3D5 review R2).
        return _no_baseline(name, mode, "no_measurable_spread", fallback)
    lower, upper = center - spread, center + spread
    value_cur = float(value_cur)

    signal, rule = _classify(name, value_cur, center, lower, upper, column, current, history)
    return Signal(series=name, mode=mode, value_cur=value_cur, center=center, lower=lower,
                  upper=upper, signal=signal, rule=rule, limits_method=limits_method,
                  mode_fallback=fallback)


def _minimum_spread(name: str, mode: str, center: float) -> float:
    """The width to use when the estimators measured no variation at all, in
    the units this series actually carries.

    This is a replacement for an unmeasurable spread, never a minimum applied
    to a measured one - see the caller.

    A chart whose limits have zero width calls every conceivable move a
    special cause, and that is not a rare shape: across a sweep of nine
    series shapes, six of the twenty-three shape/mode combinations had zero
    width - a flat shop, both steady trends in year-over-year mode, and both
    seasonal patterns in year-over-year mode.

    The units matter as much as the size. In year-over-year mode every series
    is a percentage change, so a floor of one millionth - written for money -
    protects nothing, and a floor of one percentage point written for a return
    rate expressed as a fraction means something entirely different (3D2
    doubt-review R4).
    """
    if mode == "yoy":
        return XMR_MIN_SPREAD_YOY_POINTS
    if name in RATE_SERIES:
        return XMR_MIN_SPREAD_RATE
    return XMR_MIN_SPREAD_SHARE * abs(center)


def _spread(baseline: pd.Series) -> tuple[float, str]:
    """Half the width of the limits, and which estimator produced it.

    The median moving range, because one anomalous month contributes two large
    moving ranges: the average absorbs them and the median does not. On 3B's
    finding 3a the average-based limits were about 650 units wide and the
    series could not signal at all; the median gives about 17.

    Falling back to the average when the median is zero is the load-bearing
    part, not a nicety. The median moving range is zero whenever half the
    consecutive pairs are identical - flat, rounded and small-integer series,
    which are common - and zero-width limits call a 0.2% move a special cause.
    Session 3D2 shipped exactly that before this fallback existed. On any
    series where the fallback triggers, the result is bit-for-bit what the
    average alone produced, so this cannot regress a file that works today.
    """
    moving_range = baseline.diff().abs().dropna()
    if not len(moving_range):
        return 0.0, "mean_moving_range"
    median = float(moving_range.median())
    if median > 0:
        return XMR_MEDIAN_FACTOR * median, "median_moving_range"
    return XMR_FACTOR * float(moving_range.mean()), "mean_moving_range"


def _classify(
    name: str, value_cur: float, center: float, lower: float, upper: float,
    column: pd.Series, current: str, history: list[str],
) -> tuple[str, int | None]:
    # The margin now absorbs floating-point residue and nothing else: how
    # small a move is worth reporting is decided by the minimum spread, in the
    # units the series carries. Before 3D3 this one number did both jobs and
    # could do neither well in year-over-year mode.
    margin = max(XMR_REL_TOLERANCE * abs(center), XMR_RESIDUE_FLOOR)
    if value_cur > upper + margin:
        return "above", 1
    if value_cur < lower - margin:
        return "below", 1

    # Rule 2: a run of points on one side of the centre line. Inside the
    # limits every point looks ordinary on its own; a long run does not.
    #
    # Built from the months immediately before `current`, not from a
    # NaN-collapsed list: dropping gaps first would let "eight consecutive
    # points" span far more than eight months (3B doubt-review finding 5). A
    # gap therefore breaks the run, which is the conservative reading.
    recent = column.reindex(history[-(XMR_RUN_LENGTH - 1):]).tolist()
    run = [*recent, value_cur]
    # Each point must sit on its side by more than residue. On a near-constant
    # series the points differ from the centre only by float noise, and
    # without this the side of the line is decided by the last bit.
    if len(run) == XMR_RUN_LENGTH and not any(pd.isna(point) for point in run):
        if all(point > center + margin for point in run):
            return "above", 2
        if all(point < center - margin for point in run):
            return "below", 2
    return "within", None
