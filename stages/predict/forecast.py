"""Stage 4 Predict - the forecast (docs/SPECS.md 7.4-7.5; docs/CONTRACTS.md
section 8's `forecast` block). Computed by code, never by the AI.

Interpretable on purpose: the next months' revenue is a weighted level of
the latest three complete months (the latest counts most), times each
calendar month's seasonality index when the history holds a season
(`shared/seasonality.py` says when it does). The 80% band at h months comes from
the method's own h-months-ahead errors over the history - the log of
actual over forecast when the recent months are positive (so the band
stays above zero and a lag behind a trend counts), in money otherwise;
their root mean square with Student's t for as many errors; a seasonal
year's errors from the OTHER years' indices. Revenue only: the per-product
demand the plan named served the stockout risk, not supported in v1 (4A's
F1). It reads only the consumer contract's 4A fields of metrics.json
(section 11): the period and the revenue by month.
"""

import math
import statistics
from collections.abc import Sequence

from scipy.stats import t as student_t

from contracts.forecast import MIN_HISTORY_MONTHS, ForecastBlock, RevenuePoint
from contracts.metrics import MetricsContract
from shared.periods import shift_month
from shared.seasonality import indices, season_claim, season_reading, season_window

HORIZON = 3  # months after the current one
CONFIDENCE = 0.8
WEIGHTS = (1.0, 2.0, 3.0)  # the three latest months, oldest first
MIN_HISTORY = MIN_HISTORY_MONTHS  # SPECS 7.4: fewer periods than this and no forecast (one copy)
RECENT = 12  # the months whose sign decides log or money errors (4A review 2 #2)
INSUFFICIENT = (f"no forecast: fewer than {MIN_HISTORY_MONTHS} complete months of history run up to the compared month "
                "(SPECS 7.4)")
STOCK_REASON = ("stock figures are not supported in v1: DataClarity v1 analyses sales, not inventory, so no "
                "product has a stockout risk")


def _level(values: Sequence[float]) -> float:
    # Each weight over their total first, so the level of months near the
    # largest float is still one (the 4A fuzz: 5e307 a month summed past it).
    total = sum(WEIGHTS)
    return sum(w / total * v for w, v in zip(WEIGHTS, values[-3:], strict=True))


def _index_for(cycles: list[dict[str, float]] | None, first_counted: int, target: int) -> dict[str, float]:
    """The indices a month's past forecast uses: none without a season; the
    other years' for a month of a counted year (out of sample - 4A review 1
    #2); all the years' for an older month. `seasonality._usable` checks
    exactly these sets: change them together (4A review 3b #8)."""
    if cycles is None:
        return {}
    if target >= first_counted:
        year = (target - first_counted) // 12
        return indices([c for i, c in enumerate(cycles) if i != year])
    return indices(cycles)


def horizon_errors(months: Sequence[str], values: Sequence[float], cycles: list[dict[str, float]] | None,
                   h: int) -> tuple[list[float], bool]:
    """The method's own errors h months ahead over the history: from each
    three months, the month h after them. Logs of actual over forecast
    (`True`) when the recent months are positive - windows with a month
    not positive left out - so a band from them stays above zero and a lag
    grows with h as it does in the data (4A review 2 #2, #3, #6); in money
    otherwise (`False`)."""
    n = len(months)
    first_counted = n - 12 * len(cycles) if cycles else n
    logs = all(value > 0 for value in values[-RECENT:])
    errors = []
    for t in range(3, n - h + 1):
        target = t + h - 1
        index = _index_for(cycles, first_counted, target)
        window = [values[i] / index.get(months[i][5:], 1.0) for i in range(t - 3, t)]
        forecast = _level(window) * index.get(months[target][5:], 1.0)
        if logs:
            if forecast > 0 and values[target] > 0 and all(v > 0 for v in window):
                # A difference of logs: the ratio of two far-apart amounts
                # can round to 0 (the 4A fuzz).
                errors.append(math.log(values[target]) - math.log(forecast))
        else:
            errors.append(values[target] - forecast)
    return errors, logs


def band(values: Sequence[float], errors: Sequence[float], logs: bool, point: float, h: int) -> tuple[float, float]:
    """The 80% band h months ahead: the errors' root mean square times
    Student's t for as many errors - around the point in logs (a band that
    stays above zero) or in money. With fewer than two errors, the
    history's own spread in money, times sqrt(h)."""
    if len(errors) >= 2:
        spread = math.sqrt(sum(e * e for e in errors) / len(errors))
        width = float(student_t.ppf(0.5 + CONFIDENCE / 2, len(errors) - 1)) * spread
        if logs and point > 0:
            try:
                return point * math.exp(-width), point * math.exp(width)
            except OverflowError:
                # A width past e^709 (errors hundreds of orders of magnitude,
                # the 4A fuzz): a high no float carries - refused by the
                # contract as too large.
                return point * math.exp(-width), math.inf
        return point - width, point + width
    try:
        spread = statistics.stdev(values)
    except OverflowError:
        # Amounts of both signs near the largest float (4A review 3 #6): a
        # spread no float carries - refused by the contract as too large.
        spread = math.inf
    width = float(student_t.ppf(0.5 + CONFIDENCE / 2, len(values) - 1)) * spread * math.sqrt(h)
    return point - width, point + width


def points(months: Sequence[str], values: Sequence[float], current: str,
           claim: tuple[list[dict[str, float]] | None, str | None] | None = None,
           ) -> tuple[list[RevenuePoint], int | None, str | None]:
    """The forecast of the HORIZON months after `current`, the full years a
    claimed season was read from (None when none is claimed), and the note
    on the season reading - why none was claimed when the data cannot tell
    it from a step, or that it rests on two years (`seasonality.season_
    reading`). `claim`: the shared claim on these months (`season_claim`),
    read here when given rather than computed again."""
    cycles, season_note = claim if claim is not None else season_reading(months, values)
    found_indices = indices(cycles) if cycles else {}
    level = _level([value / found_indices.get(month[5:], 1.0)
                    for month, value in zip(months, values, strict=True)])
    found = []
    for h in range(1, HORIZON + 1):
        month = shift_month(current, h)
        point = level * found_indices.get(month[5:], 1.0)
        errors, logs = horizon_errors(months, values, cycles, h)
        low, high = band(values, errors, logs, point, h)
        found.append(RevenuePoint(period=month, point=point, low=low, high=high, confidence=CONFIDENCE))
    return found, None if cycles is None else len(cycles), season_note


def history(metrics: MetricsContract) -> tuple[list[tuple[str, float]], str | None]:
    """The forecast's history as (month, revenue) pairs and its note: the one
    window stages 3 and 4 read (`shared/seasonality.season_window`)."""
    months, values, note = season_window(metrics)
    return list(zip(months, values, strict=True)), note


def forecast(metrics: MetricsContract) -> ForecastBlock:
    # The one window and the one claim stage 3 reads too (shared/seasonality).
    months, values, note = season_window(metrics)
    if len(months) < MIN_HISTORY:
        return ForecastBlock(method=INSUFFICIENT, horizon_periods=0, revenue=[], insufficient_history=True,
                             months_used=len(months), history_note=note, season_years=None, season_note=None,
                             products_at_stockout_risk=None, products_at_stockout_risk_reason=STOCK_REASON)
    found, years, season_note = points(months, values, metrics.period.current, season_claim(metrics))
    return ForecastBlock(method=_method(years is not None), horizon_periods=HORIZON, revenue=found,
                         insufficient_history=False, months_used=len(months), history_note=note, season_years=years,
                         season_note=season_note,
                         products_at_stockout_risk=None, products_at_stockout_risk_reason=STOCK_REASON)


def _method(seasonal: bool) -> str:
    base = "weighted moving average of the last 3 complete months (weights 1, 2, 3)"
    return base + (" with a monthly seasonality index" if seasonal else ", no seasonality claimed")
