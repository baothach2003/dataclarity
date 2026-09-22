"""Step 3: how much of the change is the calendar alone?
(docs/AI_PIPELINE.md section 7.4)

Months are not comparable units. February is 10% shorter than March, and a
month with five Saturdays is worth more than one with four to almost any
retailer. Before asking why revenue moved, this step says how much of the move
is explained by nothing but which days the month happened to contain.

Named `calendar_effect` rather than `calendar` so the module does not shadow
the standard library's `calendar`, which `inputs` uses.
"""

import pandas as pd

from contracts.diagnosis import Calendar
from stages.diagnose.inputs import RunData, days_in_month, month_dates
from stages.diagnose.thresholds import CALENDAR_MIN_WEEKS

WEEKDAY_NAMES = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def compute_calendar(data: RunData, history: list[str]) -> Calendar:
    period = data.metrics.period
    revenue_prev = data.metrics.core.revenue_previous
    change_abs = data.metrics.core.revenue_current - revenue_prev

    weights = _weekday_weights(data, history)
    if weights is None:
        # Not enough history to say what a Saturday is worth here, so fall
        # back to the one calendar fact that needs no history: month length.
        expected_cur = float(days_in_month(period.current))
        expected_prev = float(days_in_month(period.previous))
        method = "day_count"
        evidence: dict[str, object] = {
            "history_days": _history_days(history),
            "reason": f"fewer than {CALENDAR_MIN_WEEKS} weeks of history",
        }
    else:
        expected_cur = _expected_revenue(period.current, weights)
        expected_prev = _expected_revenue(period.previous, weights)
        method = "weekday_weights"
        evidence = {
            "weights": {WEEKDAY_NAMES[day]: round(value, 2) for day, value in weights.items()},
            "weekday_counts_cur": _weekday_counts(period.current),
            "weekday_counts_prev": _weekday_counts(period.previous),
        }

    # A ratio, not a difference: what carries over is how much more (or less)
    # the current month's shape is worth than the previous one's.
    ratio = expected_cur / expected_prev if expected_prev else 1.0
    calendar_effect = revenue_prev * (ratio - 1)

    return Calendar(
        method=method,
        expected_cur=expected_cur,
        expected_prev=expected_prev,
        calendar_effect=calendar_effect,
        calendar_adjusted_change=change_abs - calendar_effect,
        evidence=evidence | {"expected_ratio": round(ratio, 6)},
    )


def _weekday_weights(data: RunData, history: list[str]) -> dict[int, float] | None:
    """**Median** revenue per calendar date of each weekday across the history
    window, zero-revenue dates included.

    Zeros are kept deliberately: a shop that never trades on Sunday should have
    a Sunday weight near zero, and dropping its Sundays would instead give it
    an average Sunday.

    The median, not the mean, is what makes this robust to a gap inside the
    history window - which is what AI_PIPELINE 7.4's "exclude dates inside a D1
    excess gap" was reaching for. That exclusion is not definable: D1 measures
    excess *against* the history window's own pattern, so within history there
    is nothing to call excess by construction. An earlier version of this
    docstring argued the mean was safe anyway, because a hole drags every
    weekday down by the same factor and the ratio below cancels it. The 3B
    doubt-review disproved that with numbers: any run of days whose length is
    not a multiple of seven hits weekdays unevenly, and the cancellation needs
    `count_d(cur) == count_d(prev)`, which is exactly the case where this step
    has nothing to say. A shop whose POS was down on Saturdays for three months
    had 12.6% of its month's movement invented as real decline.

    A median ignores a minority of ruined dates outright: three bad months out
    of twenty-four move it not at all. The cost is that a weekday with
    genuinely two-humped revenue is described by its middle rather than its
    average, which is the right trade for an estimate of "what a Saturday is
    normally worth here".
    """
    if _history_days(history) < CALENDAR_MIN_WEEKS * 7:
        return None

    counted = data.parsed.counted
    by_date = data.parsed.revenue_amounts[counted].groupby(
        data.parsed.dates[counted].dt.normalize()).sum()

    observed: dict[int, list[float]] = {day: [] for day in range(7)}
    for month in history:
        for day in month_dates(month):
            observed[day.weekday()].append(float(by_date.get(day, 0.0)))
    return {
        day: float(pd.Series(values).median()) if values else 0.0
        for day, values in observed.items()
    }


def _expected_revenue(month: str, weights: dict[int, float]) -> float:
    return sum(weights[day.weekday()] for day in month_dates(month))


def _weekday_counts(month: str) -> dict[str, int]:
    counts = dict.fromkeys(WEEKDAY_NAMES, 0)
    for day in month_dates(month):
        counts[WEEKDAY_NAMES[day.weekday()]] += 1
    return counts


def _history_days(history: list[str]) -> int:
    return sum(days_in_month(month) for month in history)


def monthly_revenue_by_date(data: RunData) -> pd.Series:
    """Revenue per calendar date over revenue-counted rows. Exposed for tests
    and for later steps that need the daily series."""
    counted = data.parsed.counted
    return data.parsed.revenue_amounts[counted].groupby(
        data.parsed.dates[counted].dt.normalize()).sum()
