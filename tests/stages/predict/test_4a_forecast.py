"""Session 4A (ninth run): stage 4's forecast - the history it learns from,
the level and the 80% band, and the block the contract holds. The season
has its own file (test_4a_season.py). Written before the code, rewritten
with the method after each review (PROJECT_PLAN's 4A item); every expected
figure is computed by hand in the comment beside it, T(k) from
forecast_fixtures.

SPECS 7.4: a weighted moving average, with confidence bands; under 3
periods of history `insufficient_history: true` and no forecast.
"""

import math
from datetime import date

import pytest
from pydantic import ValidationError

from contracts.forecast import ForecastBlock
from contracts.lines import refused_as_too_large
from stages.predict.forecast import CONFIDENCE, HORIZON, INSUFFICIENT, forecast, history
from tests.stages.predict.forecast_fixtures import T, metrics_for, months_from

# --- the history and the insufficient path ---------------------------------------------------


def test_two_months_are_insufficient_history_and_no_forecast() -> None:
    block = forecast(metrics_for(months_from("2024-01", [100.0, 200.0]), current="2024-02"))
    assert (block.insufficient_history, block.revenue, block.horizon_periods, block.method) == (
        True, [], 0, INSUFFICIENT)
    assert (block.months_used, block.history_note) == (2, None)
    assert block.products_at_stockout_risk is None and "not supported in v1" in block.products_at_stockout_risk_reason


def test_a_month_with_no_revenue_cuts_the_months_before_it_and_the_note_says_so() -> None:
    # March 2024 holds no revenue: a closed month or missing data - never a zero.
    months = months_from("2024-01", [50.0, 50.0, 0.0, 100.0, 200.0, 300.0])
    del months["2024-03"]
    metrics = metrics_for(months, current="2024-06")
    run, note = history(metrics)
    assert [m for m, _ in run] == ["2024-04", "2024-05", "2024-06"]
    assert note == ("The history starts at 2024-04: 2024-03 holds no revenue - a closed month or missing data, "
                    "which the file cannot tell apart - so the 2 earlier month(s) with revenue are not used.")
    block = forecast(metrics)
    assert (block.months_used, block.history_note) == (3, note)
    assert block.revenue[0].point == pytest.approx(1400 / 6)


def test_the_note_counts_only_complete_months_left_out() -> None:
    # 4A review 3 #12 (R26): the file starts on 15 January - January holds
    # revenue but is not complete, so of the months before March's gap only
    # February counts as left out.
    months = months_from("2024-01", [40.0, 50.0, 0.0, 100.0, 200.0, 300.0])
    del months["2024-03"]
    note = history(metrics_for(months, current="2024-06", data_start=date(2024, 1, 15)))[1]
    assert note is not None and "so the 1 earlier month(s) with revenue are not used" in note


def test_an_empty_month_with_nothing_before_it_notes_nothing() -> None:
    # 4A review 2 #5: a month-grain file dated from 1 December whose first
    # revenue is in January - no month with revenue was left out, so no note.
    metrics = metrics_for(months_from("2024-01", [100.0, 200.0, 300.0]), current="2024-03",
                          data_start=date(2023, 12, 1), data_end=date(2024, 3, 1), month_grain=True)
    assert history(metrics) == ([("2024-01", 100.0), ("2024-02", 200.0), ("2024-03", 300.0)], None)


def test_one_missing_month_before_the_current_says_why_the_history_is_short() -> None:
    # 4A review 2 #7: 36 months, only November 2022 missing - one month runs
    # up to December, so no forecast, and the note says why.
    months = months_from("2020-01", [100.0] * 36)
    del months["2022-11"]
    block = forecast(metrics_for(months, current="2022-12"))
    assert (block.insufficient_history, block.months_used) == (True, 1)
    assert block.history_note is not None and "2022-11 holds no revenue" in block.history_note
    assert "the 34 earlier month(s) with revenue are not used" in block.history_note


def test_a_compared_month_with_no_revenue_says_why_nothing_is_used() -> None:
    # 4A review 3 #8: a file whose last line in June is not revenue (a stock
    # row on the 30th): June is complete and compared, but holds no revenue,
    # so the history is empty - and the five months before it are named.
    metrics = metrics_for(months_from("2024-01", [100.0] * 5), current="2024-06", data_end=date(2024, 6, 30))
    assert history(metrics) == ([], "The compared month 2024-06 holds no revenue - a closed month or missing data, "
                                     "which the file cannot tell apart - so the 5 earlier month(s) with revenue are "
                                     "not used.")
    block = forecast(metrics)
    assert (block.insufficient_history, block.months_used, block.history_note) == (True, 0, history(metrics)[1])


def test_the_history_ends_at_the_compared_month_even_when_a_later_one_is_complete() -> None:
    # A month-grain file whose last month is month-to-date (2E-o): stage 2
    # compares March, and the history ends there (review 1 #11: M4).
    metrics = metrics_for(months_from("2024-01", [100.0, 200.0, 300.0, 10.0]), current="2024-03",
                          data_end=date(2024, 4, 1), month_grain=True)
    assert [m for m, _ in history(metrics)[0]] == ["2024-01", "2024-02", "2024-03"]


def test_a_partial_first_month_is_never_history() -> None:
    # The file starts on 15 January: January is not complete, and no note -
    # it holds revenue but is no complete month the history could have used.
    metrics = metrics_for(months_from("2024-01", [40.0, 100.0, 200.0, 300.0]), current="2024-04",
                          data_start=date(2024, 1, 15))
    assert history(metrics) == ([("2024-02", 100.0), ("2024-03", 200.0), ("2024-04", 300.0)], None)


def test_a_month_grain_file_counts_every_month_it_holds() -> None:
    metrics = metrics_for(months_from("2024-01", [100.0, 200.0, 300.0]), current="2024-03",
                          data_end=date(2024, 3, 1), month_grain=True)
    assert [m for m, _ in history(metrics)[0]] == ["2024-01", "2024-02", "2024-03"]


# --- the level and the band ------------------------------------------------------------------


def test_three_months_a_weighted_level_and_a_band_from_the_history() -> None:
    # Level (1*100 + 2*200 + 3*300) / 6 = 233.333; no error h months ahead
    # yet, so the band is the history's own spread in money: stdev 100,
    # T(2), sqrt(h).
    block = forecast(metrics_for(months_from("2024-01", [100.0, 200.0, 300.0]), current="2024-03"))
    assert block.insufficient_history is False and block.horizon_periods == HORIZON == 3
    assert block.method == "weighted moving average of the last 3 complete months (weights 1, 2, 3), " \
                           "no seasonality claimed"
    assert [p.period for p in block.revenue] == ["2024-04", "2024-05", "2024-06"]
    for h, point in enumerate(block.revenue, start=1):
        assert point.point == pytest.approx(1400 / 6)
        assert (point.low, point.high) == pytest.approx((1400 / 6 - T[2] * 100 * math.sqrt(h),
                                                         1400 / 6 + T[2] * 100 * math.sqrt(h)))
        assert point.confidence == CONFIDENCE == 0.8


def test_one_error_is_not_enough_the_history_spread_stands() -> None:
    # Four months: one error one month ahead, none further (review 1 #11:
    # M1). stdev of 100, 200, 300, 100: mean 175, squares 5625 + 625 +
    # 15625 + 5625 = 27500, sqrt(27500 / 3) = 95.7427, with T(3), x sqrt(h).
    block = forecast(metrics_for(months_from("2024-01", [100.0, 200.0, 300.0, 100.0]), current="2024-04"))
    for h, point in enumerate(block.revenue, start=1):
        assert point.point == pytest.approx(1100 / 6)
        assert point.high - point.point == pytest.approx(T[3] * math.sqrt(27500 / 3) * math.sqrt(h))


def test_the_band_comes_from_the_log_errors_h_months_ahead() -> None:
    # 100 x5 then 160, every month positive: the band is in logs. Level
    # (100 + 200 + 480) / 6 = 130.
    # h=1: months 4, 5, 6 forecast from the three before them (100 each):
    #   errors log(1), log(1), log(1.6); root mean square log(1.6) / sqrt(3), T(2).
    # h=2: months 5 and 6 from the three ending two months before: log(1),
    #   log(1.6); log(1.6) / sqrt(2) with T(1) - two errors are enough.
    # h=3: one error only - the history's spread in money: mean 110, squares
    #   5 x 100 + 2500 = 3000, sqrt(3000 / 5) with T(5), x sqrt(3).
    block = forecast(metrics_for(months_from("2024-01", [100.0] * 5 + [160.0]), current="2024-06"))
    first, second, third = block.revenue
    assert first.point == second.point == third.point == pytest.approx(130.0)
    width_1 = T[2] * math.log(1.6) / math.sqrt(3)
    width_2 = T[1] * math.log(1.6) / math.sqrt(2)
    assert (first.low, first.high) == pytest.approx((130 * math.exp(-width_1), 130 * math.exp(width_1)))
    assert (second.low, second.high) == pytest.approx((130 * math.exp(-width_2), 130 * math.exp(width_2)))
    width_3 = T[5] * math.sqrt(600) * math.sqrt(3)
    assert (third.low, third.high) == pytest.approx((130 - width_3, 130 + width_3))


def test_a_steady_lag_behind_a_trend_widens_the_band_with_the_horizon() -> None:
    # 10% growth a month, 6 months: the level (1 + 2.2 + 3.63) / 6 of the
    # window's first month trails the month h after the window by 1.1^(h+2):
    # h=1 every error is log(1.331 x 6 / 6.83) = 0.156365 (T(2), 3 of them),
    # h=2 log(1.4641 x 6 / 6.83) = 0.251676 (T(1), 2) - the lag grows with h
    # as it does in the data (4A review 2 #3).
    values = [100 * 1.1 ** i for i in range(6)]
    block = forecast(metrics_for(months_from("2024-01", values), current="2024-06"))
    level = (values[3] + 2 * values[4] + 3 * values[5]) / 6
    for point, width in zip(block.revenue, (T[2] * math.log(1.331 * 6 / 6.83), T[1] * math.log(1.4641 * 6 / 6.83))):
        assert point.point == pytest.approx(level)
        assert point.high == pytest.approx(level * math.exp(width))


def test_a_month_at_or_under_zero_in_the_last_twelve_puts_the_errors_in_money() -> None:
    # 100 x5 then 0: level (100 + 200 + 0) / 6 = 50; one month ahead the
    # errors are 0, 0, -100 in money: root mean square 100 / sqrt(3), T(2).
    block = forecast(metrics_for(months_from("2024-01", [100.0] * 5 + [0.0]), current="2024-06"))
    width = T[2] * 100 / math.sqrt(3)
    assert (block.revenue[0].low, block.revenue[0].point, block.revenue[0].high) == pytest.approx(
        (50 - width, 50, 50 + width))


def test_one_old_month_under_zero_changes_nothing_after_it() -> None:
    # 4A review 2 #2: one old month at -20 switched the whole band to money
    # and halved it. Now only the last twelve months decide - thirteen
    # months back is old (4A review 3 #12) - and in logs a window holding it
    # is left out, so the forecast is the one of the twelve months after
    # it, to the last digit.
    wiggle = [1.0, 1.04, 0.97, 1.02, 0.95, 1.03]
    later = [1000 * 1.06 ** i * wiggle[i % 6] for i in range(12)]
    with_it = forecast(metrics_for(months_from("2023-01", [-20.0, *later]), current="2024-01"))
    without = forecast(metrics_for(months_from("2023-02", later), current="2024-01"))
    assert (with_it.months_used, without.months_used) == (13, 12)
    assert with_it.revenue == without.revenue
    first = with_it.revenue[0]
    assert first.high / first.point == pytest.approx(first.point / first.low)  # a band in logs


def test_twelve_months_back_is_still_recent() -> None:
    # -20 then eleven months at 100: the month under zero is one of the last
    # twelve, so the errors are in money. One month ahead: from -20, 100,
    # 100 the level (-20 + 200 + 300) / 6 = 80 against 100, an error of 20;
    # the eight later windows 0. Root mean square 20 / 3 with T(8).
    block = forecast(metrics_for(months_from("2024-01", [-20.0] + [100.0] * 11), current="2024-12"))
    width = T[8] * 20 / 3
    assert (block.revenue[0].low, block.revenue[0].point, block.revenue[0].high) == pytest.approx(
        (100 - width, 100, 100 + width))


def test_negative_revenue_is_forecast_as_it_is_with_a_band_in_money() -> None:
    # Returns can exceed sales: level (-10 - 40 - 90) / 6; the history's stdev
    # 10 with T(2).
    block = forecast(metrics_for(months_from("2024-01", [-10.0, -20.0, -30.0]), current="2024-03"))
    assert block.revenue[0].point == pytest.approx(-140 / 6)
    assert block.revenue[0].low == pytest.approx(-140 / 6 - T[2] * 10)


def test_amounts_near_the_largest_float_are_forecast_not_crashed() -> None:
    # The 4A fuzz: 5e307 a month summed past the largest float, then the log
    # of 0. The weights are divided first, so the level is 5e307 and every
    # error log(1).
    block = forecast(metrics_for(months_from("2024-01", [5e307] * 6), current="2024-06"))
    assert [(p.low, p.point, p.high) for p in block.revenue] == pytest.approx([(5e307, 5e307, 5e307)] * 3)


def test_amounts_hundreds_of_orders_apart_are_too_large_not_a_crash() -> None:
    # 4A review 2 #11: a year at 1 then a year at 1e215 raised OverflowError.
    months = months_from("2024-01", [1.0] * 12 + [1e215] * 12)
    with pytest.raises(ValidationError) as caught:
        forecast(metrics_for(months, current="2025-12"))
    assert refused_as_too_large(caught.value)


def test_a_spread_past_the_largest_float_is_too_large_not_a_crash() -> None:
    # 4A review 3 #6: three months of both signs near the largest float -
    # their standard deviation overflowed (OverflowError, a 500).
    months = months_from("2024-01", [1.7e308, -1.7e308, 1.7e308])
    with pytest.raises(ValidationError) as caught:
        forecast(metrics_for(months, current="2024-03"))
    assert refused_as_too_large(caught.value)


def test_amounts_at_the_smallest_float_are_forecast_not_crashed() -> None:
    # 4A review 3 #12: 5e-324 a month - its weighted level rounds to 0, so no
    # error has a log to take (the log of 0 raised); nothing measured, no
    # spread: a forecast of 0 with no width.
    block = forecast(metrics_for(months_from("2024-01", [5e-324] * 6), current="2024-06"))
    assert [(p.low, p.point, p.high) for p in block.revenue] == [(0.0, 0.0, 0.0)] * 3


def test_errors_past_e_to_the_709_are_too_large_not_a_crash() -> None:
    # The 4A fuzz: 1e-300 and 1e300 by turns. One month ahead the second
    # error's ratio 1e-300 / 6.7e299 rounds to 0 (a log of 0 raised), and
    # the band's width, T(2) x about 1381, is past what exp carries
    # (OverflowError): the high is no float, refused as too large.
    with pytest.raises(ValidationError) as caught:
        forecast(metrics_for(months_from("2024-01", [1e-300, 1e300] * 3), current="2024-06"))
    assert refused_as_too_large(caught.value)


# --- the block the contract holds -------------------------------------------------------------


def _block(**changes: object) -> dict:
    point = {"period": "2024-04", "point": 10.0, "low": 9.0, "high": 11.0, "confidence": 0.8}
    return {"method": "m", "horizon_periods": 1, "revenue": [point], "insufficient_history": False,
            "months_used": 3, "history_note": None, "season_note": None, "products_at_stockout_risk": None,
            "products_at_stockout_risk_reason": "stock figures are not supported in v1"} | changes


def test_the_block_is_a_forecast_or_none() -> None:
    assert ForecastBlock.model_validate(_block()).horizon_periods == 1
    empty = {"revenue": [], "horizon_periods": 0}
    assert ForecastBlock.model_validate(_block(insufficient_history=True, months_used=2, **empty)).months_used == 2
    with pytest.raises(ValidationError, match="no forecast"):
        ForecastBlock.model_validate(_block(insufficient_history=True, months_used=2))
    with pytest.raises(ValidationError, match="no forecast, horizon 0"):
        ForecastBlock.model_validate(_block(insufficient_history=True, months_used=2, revenue=[]))
    with pytest.raises(ValidationError, match="no season note"):
        ForecastBlock.model_validate(_block(insufficient_history=True, months_used=2, season_note="n", **empty))
    with pytest.raises(ValidationError, match="one forecast point per month"):
        ForecastBlock.model_validate(_block(horizon_periods=3))
    twice = [_block()["revenue"][0], _block()["revenue"][0]]
    with pytest.raises(ValidationError, match="follow each other"):
        ForecastBlock.model_validate(_block(horizon_periods=2, revenue=twice))


@pytest.mark.parametrize(("insufficient", "months_used"), [(True, 3), (True, 24), (False, 2), (False, 0)])
def test_insufficient_history_means_fewer_than_three_months(insufficient: bool, months_used: int) -> None:
    # 4A review 2 #8: both of these were accepted.
    changes = {"revenue": [], "horizon_periods": 0} if insufficient else {}
    with pytest.raises(ValidationError, match="fewer than 3 months used"):
        ForecastBlock.model_validate(_block(insufficient_history=insufficient, months_used=months_used, **changes))


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_a_forecast_figure_json_cannot_carry_is_too_large(value: float) -> None:
    # Review 1 #6: 5e307 a month forecast past a float.
    point = {"period": "2024-04", "point": value, "low": value, "high": value, "confidence": 0.8}
    with pytest.raises(ValidationError) as caught:
        ForecastBlock.model_validate(_block(revenue=[point]))
    assert refused_as_too_large(caught.value)
