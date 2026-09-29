"""Session 4A (ninth run): when stage 4's forecast claims a season, and the
band's errors when it does. Every expected figure is computed by hand in
the comment beside it; T(k) and SEASON (mean 1, November 1.6, February 0.7)
from forecast_fixtures.

SPECS 7.5: seasonality claimed only with two full cycles and a gap between
the strongest and weakest month above 40% - read as (strongest - weakest) /
strongest, the most cautious reading (4A review 2 #9). And never a season
the data cannot tell from something else (CLAUDE.md 3.3a): not a trend, not
noise, not one big month, not a step between two years.
"""

import math

import pytest

from stages.predict.forecast import forecast
from stages.predict.seasonality import (
    RAMP_NOTE,
    _agreement,
    _cycles,
    _ramp,
    detrended,
    indices,
    refusal,
    season,
    season_reading,
)
from tests.stages.predict.forecast_fixtures import NONE, SEASON, SEASONAL, metrics_for, months_from



def _season_of(values: list[float], start: str = "2024-01") -> list[dict[str, float]] | None:
    return season(sorted(months_from(start, values)), values)


def test_growth_alone_is_no_season() -> None:
    # 5% growth a month for two years: the same month a year later is
    # always 1.05^12 higher, so the trend is log(1.05) a month and every
    # month reads 1.0 against it (review 1 #1: the year's mean read it as one).
    values = [100 * 1.05 ** i for i in range(24)]
    assert detrended(values) == pytest.approx([1.0] * 24)
    assert _season_of(values) is None


def test_two_full_cycles_of_one_season_claim_it() -> None:
    # Both years 100 x SEASON, no trend: the indices are SEASON. The level of
    # October-December, each over its index, is 100; January-March 2026 are
    # 100 x 0.8, 0.7, 0.9. Each year's errors come from the other year's
    # indices - the same - so every error is 0 and the band has no width.
    block = forecast(metrics_for(months_from("2024-01", [100 * p for p in SEASON * 2]), current="2025-12"))
    assert block.method == SEASONAL
    assert [(p.period, round(p.low, 6), round(p.point, 6), round(p.high, 6)) for p in block.revenue] == [
        ("2026-01", 80.0, 80.0, 80.0), ("2026-02", 70.0, 70.0, 70.0), ("2026-03", 90.0, 90.0, 90.0)]


def test_a_season_and_a_trend_are_told_apart() -> None:
    # The same season on 3% growth a month: the same month a year later is
    # 1.03^12 higher every time, so the trend is log(1.03) a month and the
    # months against it are SEASON again, up to a common scale.
    values = [100 * p * 1.03 ** i for i, p in enumerate(SEASON * 2)]
    ratios = detrended(values)
    assert [r / ratios[0] for r in ratios] == pytest.approx([p / SEASON[0] for p in SEASON * 2])
    assert _season_of(values) is not None


@pytest.mark.parametrize(("strongest", "claimed"), [(1.6, False), (5 / 3, False), (1.7, True)])
def test_the_gap_must_exceed_40_percent_of_the_strongest_month(strongest: float, claimed: bool) -> None:
    # Eleven months at 1, December at `strongest`, both years: the gap is
    # (x - 1) / x - 0.375 for 1.6, exactly 0.4 for 5/3 (not above it: review
    # 1 #8), 0.412 for 1.7. The years agree fully, and one high month is no
    # steady ramp (a line explains 0.23 of the logs).
    values = [100 * p for p in ([1.0] * 11 + [strongest]) * 2]
    assert (_season_of(values) is not None) is claimed


def test_a_gap_of_exactly_40_percent_is_not_above_it_whatever_the_rounding() -> None:
    # Eleven months at 60, December at 100: (100 - 60) / 100 = 0.4 exactly,
    # which floats compute as 0.4 + 4.4e-16 - a tie, not a season.
    assert _season_of([60.0] * 11 + [100.0] + [60.0] * 11 + [100.0]) is None


@pytest.mark.parametrize(("oldest", "claimed"), [(SEASON, True), (SEASON[::-1], False)])
def test_every_whole_year_counts_not_only_the_last_two(oldest: list[float], claimed: bool) -> None:
    # 36 months: the two latest years 100 x SEASON, the oldest the same or
    # reversed. Three whole years are counted; a reversed oldest year runs
    # against the others, so the years no longer agree and no season is
    # claimed - though the last two alone would claim one.
    values = [100 * p for p in oldest + SEASON + SEASON]
    assert (_season_of(values, "2023-01") is not None) is claimed
    assert _season_of(values[-24:]) is not None


def test_a_pattern_the_years_do_not_share_is_no_season() -> None:
    # Year 2 is year 1 reversed: the same months' gap, the opposite pattern -
    # the years' correlation is negative, under 0.6 (review 1 #3).
    values = [100 * p for p in SEASON + SEASON[::-1]]
    months = sorted(months_from("2024-01", values))
    assert _agreement(_cycles(months, detrended(values))) < 0
    assert _season_of(values) is None


def test_one_big_month_is_no_season() -> None:
    # Flat 100 for two years but one month at 400: the same month a year
    # apart changes by log 4 once and by 0 eleven times, so the trend (their
    # median) is 0; the other year does not move at all, so the years
    # cannot agree - 0 by definition, not a correlation of a constant.
    values = [100.0] * 24
    values[12] = 400.0
    months = sorted(months_from("2024-01", values))
    assert _agreement(_cycles(months, detrended(values))) == 0.0
    assert _season_of(values) is None


def test_three_years_agree_as_the_mean_of_each_against_the_others() -> None:
    # Years u, u, v with u and v uncorrelated and of equal spread: each u
    # against the mean (u + v) / 2 correlates 1 / sqrt(2); v against u, 0.
    # The mean: (2 / sqrt(2) + 0) / 3 = sqrt(2) / 3 = 0.4714.
    u = [3.0, 1.0] * 6
    v = [3.0, 3.0, 1.0, 1.0] * 3
    months = [f"{m:02d}" for m in range(1, 13)]
    cycles = [dict(zip(months, u)), dict(zip(months, u)), dict(zip(months, v))]
    assert _agreement(cycles) == pytest.approx(math.sqrt(2) / 3)


@pytest.mark.parametrize("start", ["2024-01", "2023-07"])
def test_a_step_between_the_years_is_no_season(start: str) -> None:
    # 4A review 2 #1: 1000 a month for a year, then 2000. Every month a year
    # later is twice as high, so the trend is log(2) / 12 a month and each
    # year reads as a steady fall against it - Jan 1, ..., Dec 2^(-11/12),
    # a 47% gap, the years in full agreement. With two years the data cannot
    # tell that from growth over a falling season; a straight line explains
    # the logs fully (1.0, at least 0.9), so no season is claimed and the
    # forecast is the level of the last three months, 2000 - and the block
    # says why none was claimed (the standing rule; 4A review 3 #7). The
    # counted year is read in its own order: from July too.
    values = [1000.0] * 12 + [2000.0] * 12
    months = months_from(start, values)
    assert season_reading(sorted(months), values) == (None, RAMP_NOTE)
    block = forecast(metrics_for(months, current=max(months)))
    assert (block.method, block.season_note) == (NONE, RAMP_NOTE)
    assert [p.point for p in block.revenue] == pytest.approx([2000.0] * 3)


def test_a_season_refused_for_another_reason_carries_no_note() -> None:
    # One big month: the years do not agree - no season, and nothing the
    # data cannot tell apart, so no note; a claimed season has none either.
    values = [100.0] * 24
    values[12] = 400.0
    assert season_reading(sorted(months_from("2024-01", values)), values) == (None, None)
    block = forecast(metrics_for(months_from("2024-01", [100 * p for p in SEASON * 2]), current="2025-12"))
    assert (block.method, block.season_note) == (SEASONAL, None)


# Twelve calendar months in order, and a +1 -1 -1 +1 pattern (x3) that no
# straight line through them explains: its sum and its sum against k are 0.
ORDER = [f"{m:02d}" for m in range(1, 13)]
ZIGZAG = [1.0, -1.0, -1.0, 1.0] * 3


@pytest.mark.parametrize(("share", "refused"), [(0.841, None), (0.895, None), (0.905, "ramp"), (0.923, "ramp")])
def test_the_ramp_refusal_is_at_nine_tenths_of_the_logs(share: float, refused: str | None) -> None:
    # Two identical years, ratios exp(s x (k - 5.5) + 0.3 x ZIGZAG): the
    # indices' logs are that plus a constant, and ZIGZAG is uncorrelated with
    # k, so a line explains s^2 x 143 / (s^2 x 143 + 0.09 x 12) of them - the
    # `share` asked for when s^2 = 1.08 x share / (143 x (1 - share)).
    # Claimed under 0.9, refused from it (0.923 is s = 0.3). The gap is far
    # above 40%; the years agree. (A tie at exactly 0.9 is left to floats.)
    s = math.sqrt(1.08 * share / (143 * (1 - share)))
    year = dict(zip(ORDER, (math.exp(s * (k - 5.5) + 0.3 * z) for k, z in enumerate(ZIGZAG)), strict=True))
    assert _ramp(ORDER, indices([year])) == pytest.approx(share)
    assert refusal([year, dict(year)], ORDER) == refused


@pytest.mark.parametrize(("correlation", "refused"), [(0.724, None), (0.605, None), (0.595, "agreement"),
                                                       (0.5625, "agreement")])
def test_the_years_must_agree_at_six_tenths(correlation: float, refused: str | None) -> None:
    # Year 1 = u + a x ZIGZAG, year 2 = u - a x ZIGZAG, u = 1 + 0.5 x
    # [1, 1, -1, -1] (x3) - uncorrelated with ZIGZAG, spread 0.25 x 12 = 3
    # against 12 a^2. Their correlation: (3 - 12 a^2) / (3 + 12 a^2) = (1 -
    # 4 a^2) / (1 + 4 a^2), the `correlation` asked for when 4 a^2 = (1 - c)
    # / (1 + c). Claimed from 0.6, refused under it. The indices are u: a gap
    # of (1.5 - 0.5) / 1.5, and no ramp.
    a = math.sqrt((1 - correlation) / (1 + correlation) / 4)
    u = [1 + 0.5 * g for g in [1.0, 1.0, -1.0, -1.0] * 3]
    one = dict(zip(ORDER, (x + a * z for x, z in zip(u, ZIGZAG, strict=True)), strict=True))
    two = dict(zip(ORDER, (x - a * z for x, z in zip(u, ZIGZAG, strict=True)), strict=True))
    assert _agreement([one, two]) == pytest.approx(correlation)
    assert refusal([one, two], ORDER) == refused


def test_years_that_disagree_are_refused_on_agreement_before_the_ramp() -> None:
    # 4B review 1 #19 (Part B): year 1 falls 1000 x e^(-0.2k), year 2 rises
    # 300 x e^(0.01k) - the years correlate -0.95, and against their trend
    # the indices also ramp (0.97). Agreement is tested before the ramp, so
    # the refusal is "agreement" and carries no step note: years that
    # disagree are no step either.
    values = [1000 * math.exp(-0.2 * k) for k in range(12)] + [300 * math.exp(0.01 * k) for k in range(12)]
    months = sorted(months_from("2024-01", values))
    cycles = _cycles(months, detrended(values))
    assert _agreement(cycles) < 0 and _ramp(ORDER, indices(cycles)) >= 0.9
    assert refusal(cycles, ORDER) == "agreement"
    assert season_reading(months, values) == (None, None)


def test_the_gap_is_tested_first_so_a_small_step_carries_no_note() -> None:
    # 1000 then 1500: against the trend each year falls 1.5^(-k/12) - a gap
    # of 1 - 1.5^(-11/12) = 0.310, under 40%. Refused on the gap, as any
    # 31% season would be: nothing the data cannot tell apart, so no note
    # (the ramp, tested after it, would call it a step).
    values = [1000.0] * 12 + [1500.0] * 12
    months = sorted(months_from("2024-01", values))
    assert refusal(_cycles(months, detrended(values)), ORDER) == "gap"
    assert season_reading(months, values) == (None, None)


def test_amounts_whose_trend_overflows_measure_no_season() -> None:
    # The 4A fuzz: one month at 1e308 among 1e-300s - against the trend it is
    # e^1340, past what a float carries: no season, never a crash.
    values = [1e308] + [1e-300] * 23
    assert _season_of(values) is None


def test_a_zero_or_negative_month_measures_no_season_and_never_crashes() -> None:
    # Review 1 #5: an August of 0 both years divided by zero.
    values = [100 * p for p in SEASON * 2]
    values[7] = values[19] = 0.0
    assert detrended(values) is None  # measured against nothing
    assert forecast(metrics_for(months_from("2024-01", values), current="2025-12")).method == NONE


def test_under_two_cycles_claims_none() -> None:
    assert _season_of([100 * p for p in (SEASON * 2)[:23]]) is None


def test_the_years_are_counted_back_from_the_latest_month() -> None:
    # 30 months: six older months at 500, then 2024-2025 at 100 x SEASON.
    # The season comes from the two years ending at the current month, so
    # January 2026 is 100 x 0.8 = 80 again.
    block = forecast(metrics_for(months_from("2023-07", [500.0] * 6 + [100 * p for p in SEASON * 2]),
                                 current="2025-12"))
    assert block.method == SEASONAL
    assert block.revenue[0].point == pytest.approx(80.0)


def test_a_month_hundreds_of_orders_under_the_others_measures_no_season() -> None:
    # The 4A fuzz: February of year 1 at 5e-324, year 2 at 100 x SEASON. Year
    # 1's own index for February rounds to 0.0 - year 2's errors divided by
    # it. No season is measured (every index a positive number, or none),
    # and the forecast is the plain level: (130 + 320 + 330) / 6 = 130.
    values = [100 * p for p in SEASON] + [100 * p for p in SEASON]
    values[1] = 5e-324
    assert _season_of(values) is None
    block = forecast(metrics_for(months_from("2024-01", values), current="2025-12"))
    assert block.method == NONE and block.revenue[0].point == pytest.approx(130.0)
