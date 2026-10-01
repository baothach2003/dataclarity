"""D1's model of a shop's days with no sales (docs/AI_PIPELINE.md 7.3; session
3E1b): which history months teach the pattern, what a month is expected to
hold, and how far beyond that is more than this shop's own variation.

Pure functions of per-month counts, so every boundary can be worked by hand.
The rule was chosen by a sweep fixed before it ran (the 3E1b method,
C:\\Users\\Happy\\3E1b-method.txt, with its amendments): shop shapes x seeds x
current months with nothing missing, against lost days and gapped histories.

- Two expectations. The PATTERN: the weekday zero-rates of the learned
  months (3B) - those whose days beyond the others' weekday pattern stay
  under 3 days: an annual closure is learned for its season but teaches no
  weekday habit (review 3, R1). The SEASON-ADJUSTED one: the pattern plus what the same
  calendar month of other learned years held BEYOND its own pattern, when
  that is positive - a seasonal shop's off-season and an annual closure are
  its own pattern. (Their raw counts, first used, carried the weekdays: an
  October with four Sundays expected the five closed Sundays of its copies,
  and a lost Wednesday hid - review 2, N4.) The trust
  badge reads the second; everything a closure still moves (B1's and T2's
  refusals, the D1 hypothesis and its gap) reads the first: a closed
  Christmas week is no missing data, but December still lost it against
  November (3E1b review 1, F1).
- The spread is this shop's month-to-month variation of zero days: the larger
  of a robust spread of the learned months' leave-one-out excesses (median +
  K x 1.4826 x MAD) and K binomial standard deviations of the month's zero
  days. A fixed 3 days cautioned 27% of shops trading 45% of their days with
  nothing missing, while a shop that never misses a day lost two days unseen
  (2E-u F5). A caution needs at least the FLOOR too: one whole day once a
  full year of months is LEARNED (its annual closures seen), else 3E1's 3
  days (review 2, N1: keyed on candidates, it stayed at one day with seven
  months learned).
- A history month is learned from unless its own excess over the others
  reaches 3E1's 3 days and passes the shop's spread (largest first,
  repeated): a December missing 14 days
  of 31 passed the old "half the median active days" floor and hid a 7-day
  gap (3E1 cycle 4, part B). A gap a month must not teach is days, not a
  holiday: excluded at one day, every bank-holiday month left the learning,
  its own year-ago copy with it, and the next one cautioned (review 2, N1).
  No compared month vouches for anything: a gap
  repeated in the same month a year apart cannot be told from a closure, and
  then the badge cautions (CLAUDE.md 3.3a; review 1, F2).
"""

import calendar
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from statistics import median

from stages.diagnose.thresholds import (D1_BLOCK_SHARE, D1_CAUTION_MIN_DAYS, D1_CAUTION_MIN_DAYS_SHORT,
                                        D1_FULL_YEAR_MONTHS, D1_SPREAD_K)

# The normal-consistent scale of a median absolute deviation.
MAD_SCALE = 1.4826


@dataclass(frozen=True)
class MonthZeros:
    """Per weekday (Monday first): days with no sale, and calendar days."""

    zeros: tuple[int, ...]
    days: tuple[int, ...]

    @property
    def total(self) -> int:
        return sum(self.zeros)

    @property
    def length(self) -> int:
        return sum(self.days)


def count_zeros(traded: set[date], month: str) -> MonthZeros:
    """`traded` holds the dates with at least one sale (7.3: a refund-only
    date is a day without sales)."""
    year, number = int(month[:4]), int(month[5:7])
    zeros, days = [0] * 7, [0] * 7
    for day in range(1, calendar.monthrange(year, number)[1] + 1):
        weekday = date(year, number, day).weekday()
        days[weekday] += 1
        if date(year, number, day) not in traded:
            zeros[weekday] += 1
    return MonthZeros(tuple(zeros), tuple(days))


def zero_rates(months: Mapping[str, MonthZeros], learned: Iterable[str]) -> tuple[float, ...]:
    """Share of the learned months' dates of each weekday with no sale."""
    zeros, days = [0] * 7, [0] * 7
    for month in learned:
        for weekday in range(7):
            zeros[weekday] += months[month].zeros[weekday]
            days[weekday] += months[month].days[weekday]
    return tuple(z / d if d else 0.0 for z, d in zip(zeros, days))


def pattern_zero_days(months: Mapping[str, MonthZeros], month: str, learned: Iterable[str]) -> float:
    """The weekday pattern's expectation alone."""
    rates = zero_rates(months, learned)
    return sum(rate * days for rate, days in zip(rates, months[month].days))


def expected_zero_days(months: Mapping[str, MonthZeros], month: str, learned: Iterable[str],
                       weekdays: Iterable[str] | None = None) -> float:
    """The pattern's expectation (the weekday rates of `weekdays`, by default
    the learned months) plus the mean of what the same calendar month of
    other learned years held beyond THEIR pattern (scaled by the months'
    lengths), when that is positive. A month never vouches for itself."""
    learned = list(learned)
    weekdays = learned if weekdays is None else list(weekdays)
    pattern = pattern_zero_days(months, month, weekdays)
    same = [other for other in learned if other != month and other[5:7] == month[5:7]]
    if not same:
        return pattern
    length = months[month].length
    beyond = sum((months[other].total - pattern_zero_days(months, other, weekdays)) * length / months[other].length
                 for other in same) / len(same)
    return pattern + max(0.0, beyond)


def loo_excess(months: Mapping[str, MonthZeros], learned: list[str],
               weekdays: list[str] | None = None, *, season: bool = True) -> dict[str, float]:
    """Each learned month's zero days against the expectation the OTHERS
    give - season-adjusted, or the weekday pattern alone with `season` False
    (signed: a month quieter than its pattern counts too)."""
    weekdays = learned if weekdays is None else weekdays
    out: dict[str, float] = {}
    for month in learned:
        rest = [other for other in learned if other != month]
        rates_from = [other for other in weekdays if other != month]
        if not rest:
            out[month] = 0.0
        elif season:
            out[month] = months[month].total - expected_zero_days(months, month, rest, rates_from)
        else:
            out[month] = months[month].total - pattern_zero_days(months, month, rates_from)
    return out


def spread(months: Mapping[str, MonthZeros], month: str, learned: list[str],
           weekdays: list[str] | None = None, *, season: bool = True) -> float:
    """How far beyond its expectation `month` may go and still be this shop's
    ordinary variation (see the module docstring)."""
    weekdays = learned if weekdays is None else weekdays
    excess = list(loo_excess(months, learned, weekdays, season=season).values()) or [0.0]
    centre = median(excess)
    mad = median(abs(value - centre) for value in excess)
    # The binomial floor at the month's OWN expected rate, its season
    # included: an off-season month expecting 28 of 31 zero days varies like
    # one (1-5 trading days), which the in-season weekday rates alone do not
    # say - seasonal shops cautioned 25% with nothing missing once the
    # off-season left the weekday rates (review 3, R1's fix).
    rates = zero_rates(months, weekdays)
    extra = 0.0
    if season:
        extra = (expected_zero_days(months, month, learned, weekdays)
                 - pattern_zero_days(months, month, weekdays)) / months[month].length
    binomial = sum(days * min(1.0, rate + extra) * (1 - min(1.0, rate + extra))
                   for rate, days in zip(rates, months[month].days)) ** 0.5
    return max(centre + D1_SPREAD_K * MAD_SCALE * mad, D1_SPREAD_K * binomial)


def weekday_months(months: Mapping[str, MonthZeros], learned: list[str]) -> list[str]:
    """The learned months the weekday rates come from: not one whose zero days
    beyond the OTHERS' weekday pattern reach 3E1's 3 days and their spread,
    largest first, repeated. An annual closure is learned for its season -
    the same month of other years expects it - but its days are no weekday
    habit: spread over every weekday, a shop closed 1-21 August every year
    expected 1.8 zero days in May, a day lost there was no excess, B1's
    refusal lifted and B1 took the headline (3E1b review 3, R1)."""
    kept = list(learned)
    while len(kept) > 1:
        excess = loo_excess(months, kept, season=False)
        worst = max(kept, key=lambda month: excess[month])
        rest = [month for month in kept if month != worst]
        if not cautions(excess[worst], spread(months, worst, rest, season=False), D1_CAUTION_MIN_DAYS_SHORT):
            break
        kept = rest
    return kept


def floor_for(learned: int) -> float:
    """One whole day once a full year of LEARNED months can have shown the
    shop's annual closures; 3E1's 3 days before that - a lost day cannot be
    told from a bank holiday the history has not seen (review 1, F3; review
    2, N1; 3.3a)."""
    return D1_CAUTION_MIN_DAYS if learned >= D1_FULL_YEAR_MONTHS else D1_CAUTION_MIN_DAYS_SHORT


def cautions(excess: float, bar: float, floor: float) -> bool:
    """At least the floor, and more than the shop's own spread."""
    return excess >= floor and excess > bar


def learn(months: Mapping[str, MonthZeros], candidates: list[str]) -> tuple[list[str], list[str]]:
    """(learned, excluded): the month with the largest excess over the others
    is excluded while that excess reaches 3E1's 3 days and the rest's spread,
    one at a time - a gap must not teach itself as the shop's pattern, but a
    holiday is no gap. (A cap at half the candidates never bound: a gappy
    history widens its own spread first. A shop that newly closes on Sundays
    has its new months excluded until they are as many as the old regime
    allows - the can't-tell shape of CLAUDE.md 3.3a, worded as a closure;
    review 2, N3.)"""
    learned, excluded = list(candidates), []
    while len(learned) > 1:
        excess = loo_excess(months, learned)
        worst = max(learned, key=lambda month: excess[month])
        rest = [month for month in learned if month != worst]
        if not cautions(excess[worst], spread(months, worst, rest), D1_CAUTION_MIN_DAYS_SHORT):
            break
        learned, excluded = rest, [*excluded, worst]
    return learned, excluded


@dataclass(frozen=True)
class MonthJudgement:
    """One compared month: its zero days; the weekday pattern's expectation
    and the season-adjusted one; the days beyond each (`excess` is what B1,
    T2, the gaps and the D1 hypothesis read, `unexplained` what the badge
    reads); the shop's spread for it; whether it cautions."""

    observed: int
    pattern: float
    expected: float
    excess: float
    unexplained: float
    bar: float
    flagged: bool


@dataclass(frozen=True)
class Judgement:
    learned: list[str]
    excluded: list[str]
    weekdays: list[str]  # the learned months the weekday rates come from (review 3, R1)
    floor: float
    current: MonthJudgement
    previous: MonthJudgement
    blocked: bool  # the current month's unexplained days reach D1_BLOCK_SHARE of it


def judge(months: Mapping[str, MonthZeros], candidates: list[str], current: str,
          previous: str) -> Judgement | None:
    """D1's whole decision on the counts (trust.d1_coverage words it; the
    method's sweep runs this same function). None when no month can teach a
    pattern. Each month against its OWN spread (its days, its weekdays)."""
    learned, excluded = learn(months, candidates)
    if not learned:
        return None
    floor = floor_for(len(learned))
    weekdays = weekday_months(months, learned)

    def one(month: str) -> MonthJudgement:
        observed = months[month].total
        pattern = pattern_zero_days(months, month, weekdays)
        expected = expected_zero_days(months, month, learned, weekdays)
        unexplained = max(0.0, observed - expected)
        bar = spread(months, month, learned, weekdays)
        return MonthJudgement(observed, pattern, expected, max(0.0, observed - pattern), unexplained, bar,
                              cautions(unexplained, bar, floor))

    cur, prev = one(current), one(previous)
    return Judgement(learned, excluded, weekdays, floor, cur, prev,
                     cur.unexplained >= D1_BLOCK_SHARE * months[current].length)
