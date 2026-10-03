"""Session 4A (ninth run): a season's errors are out of sample - each
counted year's from the other years' indices, an older month's from all of
them - and the forecast and band they give. Split from test_4a_season.py;
every expected figure is computed by hand in the comment beside it.
"""

import math

import pytest

from stages.predict.forecast import forecast, horizon_errors
from shared.seasonality import season
from tests.stages.predict.forecast_fixtures import SEASON, SEASONAL, T, metrics_for, months_from

# Year 1 is 100 x SEASON; year 2 the same with November 30% higher (208).
# Year-over-year changes: eleven 0 and one log(1.3) - the median 0, no trend.
# Year 1's indices alone are SEASON; year 2's are its months over their mean,
# (12 + 0.48) / 12 = 1.04; both years': (SEASON + year 2) / 2 over 1.02 -
# November (1.6 + 2.08) / 2 / 1.02 = 1.84 / 1.02.
YEAR_2 = [*SEASON[:10], 1.6 * 1.3, SEASON[11]]
TWO_YEARS = [100 * p for p in SEASON + YEAR_2]


def test_each_years_errors_come_from_the_other_years_indices() -> None:
    # Review 1 #2: indices from the same year hid the band's true width.
    # One month ahead, months 4-24 (21 errors), each a log of actual over
    # forecast:
    # - year 1 with year 2's indices: a month over its index is 104 - Aug
    #   90 x 1.04 / 0.9 - so each forecast is 104 x its index = 100 x SEASON,
    #   error 0; except November: 160 against 104 x 2.08 / 1.04 = 208,
    #   log(10/13); and December, after November's 160 x 1.04 / 2.08 = 80:
    #   level (104 + 208 + 240) / 6 = 92, x 1.1 / 1.04 = 97.3077, log(26/23);
    # - year 2 with year 1's (SEASON): every window of year 1's months and
    #   year 2's before November reads 100, error 0; November 208 against
    #   160, log(1.3); December after November's 130: level (100 + 200 +
    #   390) / 6 = 115, x 1.1 = 126.5 against 110, log(20/23).
    months = sorted(months_from("2024-01", TWO_YEARS))
    cycles = season(months, TWO_YEARS)
    assert cycles is not None
    errors, logs = horizon_errors(months, TWO_YEARS, cycles, 1)
    expected = [0.0] * 7 + [math.log(10 / 13), math.log(26 / 23)] + [0.0] * 10 + [math.log(1.3), math.log(20 / 23)]
    assert logs is True
    assert errors == pytest.approx(expected, abs=1e-12)


def test_the_forecast_and_band_of_that_season() -> None:
    # The level from both years' indices: October 130 / (1.3 / 1.02) = 102,
    # November 208 / (1.84 / 1.02) = 2652 / 23, December 102; (102 + 2 x
    # 2652 / 23 + 3 x 102) / 6 = 2448 / 23. January 2026: x 0.8 / 1.02 =
    # 1920 / 23 = 83.478. The band one month ahead: the 21 errors above,
    # root mean square sqrt((2 log(1.3)^2 + log(26/23)^2 + log(20/23)^2) / 21)
    # = 0.090563, with T(20).
    block = forecast(metrics_for(months_from("2024-01", TWO_YEARS), current="2025-12"))
    assert block.method == SEASONAL
    assert [p.point for p in block.revenue] == pytest.approx([1920 / 23, 1680 / 23, 2160 / 23])
    spread = math.sqrt((2 * math.log(1.3) ** 2 + math.log(26 / 23) ** 2 + math.log(20 / 23) ** 2) / 21)
    first = block.revenue[0]
    assert (first.low, first.high) == pytest.approx((1920 / 23 * math.exp(-T[20] * spread),
                                                     1920 / 23 * math.exp(T[20] * spread)))


def test_a_month_before_the_counted_years_is_forecast_with_both_years_indices() -> None:
    # 4A review 2 #16 (A5): four older months, September-December 2023, at
    # 100 x SEASON, before the same two years; 25 errors one month ahead.
    # - December 2023 is older than the counted years, so both years'
    #   indices serve: September 120 / (1.2 / 1.02) = 102, October 102,
    #   November 160 / (1.84 / 1.02) = 2040 / 23; level 13158 / 138 =
    #   95.3478, x 1.1 / 1.02 = 102.826 against 110: log(46/43).
    # - January 2024 is year 1's, so year 2's indices serve even for its
    #   older window: 130 x 1.04 / 1.3 = 104, 160 x 1.04 / 2.08 = 80, 104;
    #   level (104 + 160 + 312) / 6 = 96, x 0.8 / 1.04 = 73.846 against 80:
    #   log(13/12). February after 80, 104, 104: level 100, x 0.7 / 1.04
    #   against 70: log(1.04). March on: as in the 24 months above - the
    #   year of a month is counted from the first counted month, not the
    #   file's first.
    values = [100 * p for p in SEASON[8:]] + TWO_YEARS
    months = sorted(months_from("2023-09", values))
    cycles = season(months, values)
    assert cycles is not None
    errors, _ = horizon_errors(months, values, cycles, 1)
    expected = ([math.log(46 / 43), math.log(13 / 12), math.log(1.04)] + [0.0] * 8
                + [math.log(10 / 13), math.log(26 / 23)] + [0.0] * 10 + [math.log(1.3), math.log(20 / 23)])
    assert errors == pytest.approx(expected, abs=1e-12)
