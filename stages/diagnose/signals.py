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
from stages.diagnose.thresholds import (
    XMR_ABS_FLOOR_DEFAULT,
    XMR_ABS_FLOOR_RATE,
    XMR_FACTOR,
    XMR_MEDIAN_FACTOR,
    XMR_MIN_BASELINE_POINTS,
    XMR_REL_TOLERANCE,
    XMR_RUN_LENGTH,
    YOY_LAG_MONTHS,
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
        return [_no_baseline(name, "level") for name in reported]

    yoy_ready = len(data.complete_months) >= YOY_MODE_MIN_MONTHS
    yoy = _as_yoy(table) if yoy_ready else None

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
        if yoy is not None and _usable(yoy[name], history) >= XMR_MIN_BASELINE_POINTS:
            signals.append(_signal_for(name, yoy[name], current, history, "yoy"))
        else:
            signals.append(_signal_for(name, table[name], current, history, "level"))
    return signals


def _usable(column: pd.Series, history: list[str]) -> int:
    return int(column.reindex(history).notna().sum())


def _no_baseline(name: str, mode: str) -> Signal:
    return Signal(series=name, mode=mode, value_cur=None, center=None, lower=None,
                  upper=None, signal="insufficient_history", rule=None,
                  limits_method="mean_moving_range")


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


def _as_yoy(table: pd.DataFrame) -> pd.DataFrame:
    """Year-over-year percentage change, which removes seasonality so a
    December is compared with a December.

    A month whose year-ago counterpart is missing, or was zero, has no YoY
    value: it is left NaN rather than folded to 0.0. `pct_change`'s
    zero-denominator convention is right for a headline figure that must show
    a number, and wrong inside a statistical series, where a fabricated 0%
    would pull the centre line and tighten the limits.
    """
    values = {}
    for name in table.columns:
        column = table[name]
        previous = pd.Series(
            [column.get(shift_month(month, -YOY_LAG_MONTHS), float("nan"))
             for month in column.index],
            index=column.index)
        previous = previous.where(previous != 0)
        values[name] = (column - previous) / previous * 100
    return pd.DataFrame(values, index=table.index)


def _signal_for(
    name: str, column: pd.Series, current: str, history: list[str], mode: str
) -> Signal:
    baseline = column.reindex(history).dropna()
    value_cur = column.get(current, float("nan"))

    if len(baseline) < XMR_MIN_BASELINE_POINTS or pd.isna(value_cur):
        return _no_baseline(name, mode)

    center = float(baseline.mean())
    # The moving range of consecutive points is what makes these limits robust
    # to a trend: a slow drift inflates it far less than the standard deviation
    # of the whole series would.
    spread, limits_method = _spread(baseline)
    lower, upper = center - spread, center + spread
    value_cur = float(value_cur)

    signal, rule = _classify(name, value_cur, center, lower, upper, column, current, history)
    return Signal(series=name, mode=mode, value_cur=value_cur, center=center, lower=lower,
                  upper=upper, signal=signal, rule=rule, limits_method=limits_method)


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
    # A point must clear the limit by a real margin. Without one, a baseline
    # that never varied gives zero-width limits and a rounding cent - or the
    # 4.4e-16 a month of cancelling sales and returns leaves behind - is
    # reported as statistically outside them. The relative term alone cannot
    # protect a series centred on zero, which return_rate usually is, so the
    # floor does that (Thach, 3B doubt-review).
    floor = XMR_ABS_FLOOR_RATE if name in RATE_SERIES else XMR_ABS_FLOOR_DEFAULT
    margin = max(XMR_REL_TOLERANCE * abs(center), floor)
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
    if len(run) == XMR_RUN_LENGTH and not any(pd.isna(point) for point in run):
        if all(point > center for point in run):
            return "above", 2
        if all(point < center for point in run):
            return "below", 2
    return "within", None
