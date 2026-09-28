"""Stage 4 Predict - whether the history holds a season, and its indices
(docs/SPECS.md 7.5; docs/CONTRACTS.md section 8). Split from forecast.py.

A season is claimed only when every test holds (SPECS 7.5 and session 4A's
reviews): two full years; every month positive; measured against the
business's own trend - the median change from a month to the same month a
year later, so neither the season nor one big month bends it; the gap
between the strongest and weakest month above 40% of the strongest; the
same pattern in every year (a correlation), so noise is no season; and not
a steady ramp through the year, which is what a step between two years
looks like - with two years the data cannot tell a step from a season, and
the standing rule (CLAUDE.md 3.3a) never guesses: no season, and a note
saying why. The tests' known limits (a noisy step, a step on top of a
season, one big month at a mild season's peak) are 8D's.
"""

import math
import statistics
from collections.abc import Sequence
from typing import Literal

# SPECS 7.5: a season needs two full cycles, and "the gap between the highest
# and lowest period exceeds 40%" - read as (strongest - weakest) / strongest,
# the most cautious of its readings (4A review 2 #9; Thach may read it
# otherwise). A floating-point tie at 40% is not above it.
SEASONAL_MIN_MONTHS = 24
SEASONAL_MIN_GAP = 0.40
# The same season every year: each year's pattern against the other years'
# (Pearson correlation of the detrended months), at least this - chosen on
# the 4A sweep (noise and a single spike cleared the gap alone).
SEASONAL_MIN_AGREEMENT = 0.6
# A season whose indices climb or fall steadily through the counted year (a
# straight line explains this share of their logs) is the shape a step
# between two years leaves - refused, as the data cannot tell them apart
# (4A review 2 #1).
SEASONAL_MAX_RAMP = 0.9
_TIE = 1e-9
# True wherever it is written (4A review 3b #1): the ramp is measured against
# the business's trend, and the refusal is a policy - a steady pattern CAN be
# a step, not always is.
RAMP_NOTE = ("No season is claimed: measured against the business's trend, the months rise or fall steadily "
             "through the year - a pattern a one-time change of level between the years also leaves, so v1 does "
             "not read it as a season.")

Refusal = Literal["gap", "agreement", "ramp"]


def detrended(values: Sequence[float]) -> list[float] | None:
    """Each month's revenue over the business's own trend: the median change
    of the logarithms from a month to the same month a year later, spread
    over the twelve months - the season cancels in a same-month change, and
    a median ignores one big month (4A review 2 #1). None when a month is
    not positive, or with less than a year and a month."""
    if len(values) < 13 or any(not value > 0 for value in values):
        return None
    logs = [math.log(value) for value in values]
    slope = statistics.median(logs[i] - logs[i - 12] for i in range(12, len(logs))) / 12
    level = statistics.fmean(y - slope * i for i, y in enumerate(logs))
    return [math.exp(y - level - slope * i) for i, y in enumerate(logs)]


def _cycles(months: Sequence[str], ratios: Sequence[float]) -> list[dict[str, float]]:
    """The full 12-month years counted back from the latest month, each as
    {calendar month: ratio}, oldest first."""
    years = len(months) // 12
    found = []
    for year in range(years, 0, -1):
        start = len(months) - 12 * year
        found.append({m[5:]: r for m, r in zip(months[start:start + 12], ratios[start:start + 12], strict=True)})
    return found


def indices(cycles: Sequence[dict[str, float]]) -> dict[str, float]:
    """Each calendar month's mean ratio over `cycles`, scaled to average 1."""
    raw = {month: sum(c[month] for c in cycles) / len(cycles) for month in cycles[0]}
    scale = sum(raw.values()) / 12
    return {month: value / scale for month, value in raw.items()}


def _agreement(cycles: Sequence[dict[str, float]]) -> float:
    """The mean correlation of each year's months with the other years'
    mean; 0 when a year does not move at all."""
    months = sorted(cycles[0])
    found = []
    for index, cycle in enumerate(cycles):
        others = [c for i, c in enumerate(cycles) if i != index]
        this = [cycle[m] for m in months]
        rest = [sum(c[m] for c in others) / len(others) for m in months]
        if statistics.pstdev(this) == 0 or statistics.pstdev(rest) == 0:
            return 0.0
        found.append(statistics.correlation(this, rest))
    return sum(found) / len(found)


def _ramp(order: Sequence[str], found: dict[str, float]) -> float:
    """The share of the indices' logs a straight line through the counted
    year (in its own month order) explains."""
    logs = [math.log(found[month]) for month in order]
    if statistics.pstdev(logs) == 0:
        return 0.0
    return statistics.correlation(list(range(len(logs))), logs) ** 2


def _usable(cycles: Sequence[dict[str, float]]) -> bool:
    """Every index the forecast and its errors divide by - all the years',
    and each set without one year - a positive number a float carries; a
    month hundreds of orders of magnitude under the others is not (the 4A
    fuzz: an index of 0.0 divided by). These are the sets
    `forecast._index_for` uses: change them together (4A review 3b #8)."""
    sets = [list(cycles)] + [[c for j, c in enumerate(cycles) if j != i] for i in range(len(cycles))]
    return all(0 < value < math.inf for found in sets for value in indices(found).values())


def refusal(cycles: Sequence[dict[str, float]], order: Sequence[str]) -> Refusal | None:
    """Which test refuses the season of these years (their calendar months
    in the counted year's `order`), or None when it is claimed. Each test is
    written so a NaN fails it: a NaN is no season."""
    found = indices(cycles)
    strongest, weakest = max(found.values()), min(found.values())
    if not (strongest - weakest) / strongest > SEASONAL_MIN_GAP + _TIE:
        return "gap"
    if not _agreement(cycles) >= SEASONAL_MIN_AGREEMENT:
        return "agreement"
    if not _ramp(order, found) < SEASONAL_MAX_RAMP:
        return "ramp"
    return None


def season_reading(months: Sequence[str], values: Sequence[float]) -> tuple[list[dict[str, float]] | None, str | None]:
    """The years of detrended ratios when the history holds a season, else
    None; and a note when a season was refused because the data cannot tell
    it from a step between the years (the standing rule)."""
    if len(months) < SEASONAL_MIN_MONTHS:
        return None, None
    counted = 12 * (len(months) // 12)
    try:
        ratios = detrended(values[-counted:])
        if ratios is None:
            return None, None
        cycles = _cycles(months[-counted:], ratios)
        if not _usable(cycles):
            return None, None
        refused = refusal(cycles, [m[5:] for m in months[-12:]])
    except (OverflowError, ZeroDivisionError, statistics.StatisticsError):
        # Amounts hundreds of orders of magnitude apart (4A review 2 #11):
        # no season is measured; the figures themselves are refused as too
        # large by the contract if they cannot be carried.
        return None, None
    if refused is None:
        return cycles, None
    return None, RAMP_NOTE if refused == "ramp" else None


def season(months: Sequence[str], values: Sequence[float]) -> list[dict[str, float]] | None:
    """The years of detrended ratios when the history holds a season."""
    return season_reading(months, values)[0]
