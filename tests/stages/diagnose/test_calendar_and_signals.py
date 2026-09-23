"""Steps 3 and 4: calendar adjustment and XmR signals, plus the stage 2 /
stage 3 consistency guarantee."""

from datetime import date

import pytest

from stages.diagnose.calendar_effect import compute_calendar
from stages.diagnose.frame import history_window
from stages.diagnose.signals import compute_signals, monthly_series
from stages.diagnose.thresholds import (
    XMR_MEDIAN_FACTOR,
    XMR_MIN_SPREAD_RATE,
    YOY_MODE_MIN_MONTHS,
)
from tests.stages.diagnose.diagnose_fixtures import (
    MAPPING,
    daily_rows,
    full_months,
    month_span,
    row,
    run_data,
)

# --- step 3: calendar ---------------------------------------------------------


def test_february_to_march_is_explained_by_day_count_alone() -> None:
    # Every day is worth exactly 10, so all seven weekday weights are 10 and
    # the expectation reduces to month length: March has 31 days, February 28.
    # calendar_effect = revenue_prev * (31/28 - 1) = 280 * 3/28 = 30.
    start, end = month_span("2010-01", 15)  # .. 2011-03, so current = 2011-03
    data = run_data(daily_rows(start, end))
    assert (data.metrics.period.current, data.metrics.period.previous) == ("2011-03", "2011-02")
    assert data.metrics.core.revenue_previous == pytest.approx(280.0)  # 28 days x 10

    calendar = compute_calendar(data, history_window(data))

    assert calendar.method == "weekday_weights"
    assert calendar.expected_cur == pytest.approx(310.0)
    assert calendar.expected_prev == pytest.approx(280.0)
    assert calendar.calendar_effect == pytest.approx(30.0)
    # Revenue went 280 -> 310, i.e. +30, all of it calendar: nothing is left.
    assert calendar.calendar_adjusted_change == pytest.approx(0.0)


def test_a_saturday_heavy_shop_gets_a_heavier_saturday_weight() -> None:
    start, end = month_span("2011-01", 11)
    rows = daily_rows(start, end)
    # Saturdays earn ten times an ordinary day.
    rows += [entry for entry in rows
             if date.fromisoformat(entry["Date"]).weekday() == 5 for _ in range(9)]
    data = run_data(rows)

    calendar = compute_calendar(data, history_window(data))

    weights = calendar.evidence["weights"]
    assert weights["sat"] == pytest.approx(10 * weights["mon"])


def test_too_little_history_falls_back_to_day_count() -> None:
    # One complete month of history (January), so under CALENDAR_MIN_WEEKS.
    data = run_data(daily_rows(date(2011, 1, 1), date(2011, 2, 28)))
    assert data.metrics.period.current == "2011-02"

    calendar = compute_calendar(data, history_window(data))

    assert calendar.method == "day_count"
    assert calendar.expected_cur == 28.0  # February
    assert calendar.expected_prev == 31.0  # January
    assert calendar.evidence["reason"].startswith("fewer than")


# --- step 4: signals ----------------------------------------------------------

# Nine baseline months with a hand-computed centre and moving range, then a
# tenth month as `current`.
#   centre  = 900 / 9 = 100
#   moving ranges = 10, 20, 15, 10, 5, 8, 16, 8
#     sorted 5, 8, 8, 10, 10, 15, 16, 20 -> MEDIAN = (10 + 10) / 2 = 10.0
#   limits  = 100 +/- 3.145 * 10.0 = 100 +/- 31.45
#
# Recomputed by hand in session 3D2, when the SPREAD estimator became the
# median moving range. The centre is untouched - still the mean, still 100 -
# and only the half-width moved, from 30.59 to 31.45: the median moving range
# (10.0) is a little smaller than the average (11.5) while its constant is
# larger (3.145 = 3/d4 against 2.66 = 3/d2). Nothing was re-fitted to what the
# code prints.
BASELINE = {
    "2011-01": 100.0, "2011-02": 110.0, "2011-03": 90.0, "2011-04": 105.0,
    "2011-05": 95.0, "2011-06": 100.0, "2011-07": 108.0, "2011-08": 92.0,
    "2011-09": 100.0,
}
CENTER = 100.0
MR_MEDIAN = 10.0
SPREAD = XMR_MEDIAN_FACTOR * MR_MEDIAN  # 31.45


def _revenue_signal(current_revenue: float):
    data = run_data(full_months({**BASELINE, "2011-10": current_revenue}))
    signals = compute_signals(data, history_window(data))
    return next(signal for signal in signals if signal.series == "revenue")


def test_xmr_limits_are_the_hand_computed_ones() -> None:
    signal = _revenue_signal(120.0)

    assert signal.mode == "level"
    assert signal.center == pytest.approx(CENTER)
    assert signal.lower == pytest.approx(CENTER - SPREAD)
    assert signal.upper == pytest.approx(CENTER + SPREAD)
    assert (signal.lower, signal.upper) == pytest.approx((68.55, 131.45), abs=0.01)
    assert signal.limits_method == "median_moving_range"


def test_a_point_inside_the_limits_is_routine_variation() -> None:
    signal = _revenue_signal(120.0)  # inside 68.55 .. 131.45

    assert signal.signal == "within"
    assert signal.rule is None


def test_a_point_above_the_upper_limit_fires_rule_one() -> None:
    signal = _revenue_signal(140.0)

    assert (signal.signal, signal.rule) == ("above", 1)
    assert signal.value_cur == pytest.approx(140.0)


def test_a_point_below_the_lower_limit_fires_rule_one() -> None:
    signal = _revenue_signal(60.0)

    assert (signal.signal, signal.rule) == ("below", 1)


def test_a_long_run_on_one_side_fires_rule_two_without_leaving_the_limits() -> None:
    """A shop that stepped up and stayed up: no single month escapes the
    limits, but eight in a row sit above the centre line.

    Hand-computed. Baseline (12 months): 60, 100, 60, 100, 115, 125, 115, 125,
    115, 125, 118, 122, summing to 1280, so centre = 1280 / 12 = 106.67. The
    eleven moving ranges are 40, 40, 40, 15, 10, 10, 10, 10, 10, 7, 4; sorted,
    the sixth of the eleven is 10.0, so the spread is 3.145 * 10.0 = 31.45 and
    the limits are 106.67 +/- 31.45 = 75.22 .. 138.12. The current month, 120,
    is well inside them - and it is the eighth consecutive point above 106.67.

    Recomputed by hand in 3D2 for the median spread; the centre and the thing
    this test exists to prove are unchanged. An earlier attempt in that
    session replaced this fixture outright, on the argument that the mean
    centre only fired here because outliers displaced it. That was wrong -
    there are no outliers in this series, and the centre was displaced by the
    shop's genuine earlier level, which is exactly what rule 2 is for. The
    test is restored.
    """
    values = [60.0, 100.0, 60.0, 100.0, 115.0, 125.0, 115.0, 125.0, 115.0, 125.0, 118.0, 122.0]
    months = {f"2011-{index + 1:02d}": value for index, value in enumerate(values)}
    months["2012-01"] = 120.0
    data = run_data(full_months(months))
    signals = compute_signals(data, history_window(data))

    signal = next(s for s in signals if s.series == "revenue")

    assert signal.center == pytest.approx(1280 / 12)
    assert (signal.lower, signal.upper) == pytest.approx((75.22, 138.12), abs=0.01)
    assert signal.lower < signal.value_cur < signal.upper  # no single month is unusual
    assert (signal.signal, signal.rule) == ("above", 2)


def test_a_six_month_file_gets_weekday_weights_but_no_xmr_baseline() -> None:
    """The two history requirements are different sizes, and a six-month file
    is the common case that falls between them (Thach, after 3B).

    Steps 3 and 4 are easy to conflate: both "need history". But step 3 needs
    `CALENDAR_MIN_WEEKS * 7` = 56 calendar days, which five months of history
    clears many times over, while step 4 needs `XMR_MIN_BASELINE_POINTS` = 8
    whole months and gets five. So the same file legitimately reports real
    weekday weights AND `insufficient_history` on every series. Asserting both
    on one file is what stops a future change from quietly coupling them.
    """
    data = run_data(daily_rows(*month_span("2011-01", 6)))
    history = history_window(data)
    assert len(history) == 5  # five baseline points, under XMR_MIN_BASELINE_POINTS

    calendar = compute_calendar(data, history)
    signals = compute_signals(data, history)

    assert calendar.method == "weekday_weights"
    assert {signal.signal for signal in signals} == {"insufficient_history"}
    assert all(signal.center is None and signal.value_cur is None for signal in signals)
    assert all(signal.rule is None for signal in signals)


def test_year_over_year_mode_switches_on_with_enough_months() -> None:
    start, end = month_span("2009-01", YOY_MODE_MIN_MONTHS)
    data = run_data(daily_rows(start, end))
    assert len(data.complete_months) == YOY_MODE_MIN_MONTHS

    signals = {signal.series: signal for signal in compute_signals(data, history_window(data))}

    assert signals["revenue"].mode == "yoy"
    # return_rate is 0.0 every month here, so its year-ago denominator is zero
    # and YoY yields no usable baseline: the series honestly reports the mode
    # it actually used rather than claiming yoy alongside the others.
    assert signals["return_rate"].mode == "level"


def test_a_series_whose_yoy_baseline_is_too_thin_falls_back_to_level() -> None:
    """3B doubt-review finding 1: mode used to be chosen from the month count
    alone, so one zero month in the file's first year left seven usable YoY
    points instead of eight - and a correctly detected collapse became
    "we cannot say" purely because the file got longer."""
    # Exactly YOY_MODE_MIN_MONTHS months, which yields exactly
    # XMR_MIN_BASELINE_POINTS YoY points - so losing one to a shut month is
    # the difference between eight and seven.
    months = {f"2009-{month:02d}": 300.0 for month in range(1, 13)}
    months |= {f"2010-{month:02d}": 300.0 for month in range(1, 10)}
    months["2009-03"] = 0.0  # kills the YoY point at 2010-03
    months["2010-09"] = 120.0  # the collapse, in the current month
    data = run_data(full_months(months))
    assert len(data.complete_months) == YOY_MODE_MIN_MONTHS

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert signal.mode == "level"
    assert signal.signal == "below"  # the collapse is still reported


def test_a_file_with_no_complete_month_still_reports_every_series() -> None:
    """3B doubt-review finding 6: `signals` came back as an empty list, which
    is not the documented way to say "no baseline"."""
    data = run_data(daily_rows(date(2011, 11, 5), date(2011, 12, 9)))
    assert data.complete_months == []

    signals = compute_signals(data, history_window(data))

    assert [signal.series for signal in signals]
    assert {signal.signal for signal in signals} == {"insufficient_history"}
    assert any(signal.series == "revenue" for signal in signals)


def test_one_month_short_of_the_threshold_stays_in_level_mode() -> None:
    start, end = month_span("2009-01", YOY_MODE_MIN_MONTHS - 1)
    data = run_data(daily_rows(start, end))

    signals = compute_signals(data, history_window(data))

    assert {signal.mode for signal in signals} == {"level"}


# --- the margin around the limits (Thach, 3B doubt-review) --------------------


def _flat_then(series_values: dict[str, float]):
    data = run_data(full_months(series_values))
    return {s.series: s for s in compute_signals(data, history_window(data))}


def test_a_rounding_cent_on_a_flat_series_is_not_a_signal() -> None:
    months = {f"2011-{month:02d}": 100.0 for month in range(1, 10)}
    months["2011-10"] = 100.01

    signal = _flat_then(months)["revenue"]

    # Limits collapse to 100.0/100.0 with no variation in the baseline; without
    # a margin a hundredth of a percent reads as "outside the control limits".
    assert signal.signal == "within"


def test_a_real_collapse_on_a_flat_series_is_still_a_signal() -> None:
    months = {f"2011-{month:02d}": 100.0 for month in range(1, 10)}
    months["2011-10"] = 40.0

    signal = _flat_then(months)["revenue"]

    assert (signal.signal, signal.rule) == ("below", 1)


def test_the_first_small_return_does_not_fire_a_signal() -> None:
    """return_rate is 0.0 every month for most shops, so its centre is 0.0 and
    its observed variation is nil. The shop's first ever return must stay
    quiet.

    Updated in 3D3: this used to assert `upper == 0.0`, which pinned the
    zero-width limits rather than the behaviour - and zero-width limits are
    the defect 3D3 removes, because they make every conceivable move a special
    cause. The minimum spread for a rate series is one percentage point, so
    the limits are now (-0.01, 0.01) and a 0.5% return rate sits inside them.
    The thing this test exists to prove is unchanged.
    """
    rows = [row(date(2011, 1, 1), qty=1.0)]
    for month in range(1, 10):
        rows += [row(date(2011, month, day), qty=1.0) for day in (5, 15, 25)]
    # October: 200 clean orders and the shop's first ever return, so
    # return_rate is about 0.5% against a baseline that has always been 0.0.
    rows += [row(date(2011, 10, index % 30 + 1), qty=1.0) for index in range(200)]
    rows.append(row(date(2011, 10, 31), qty=-1.0))
    data = run_data(rows)

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "return_rate")

    assert signal.center == 0.0
    assert (signal.lower, signal.upper) == (-XMR_MIN_SPREAD_RATE,
                                            XMR_MIN_SPREAD_RATE)
    assert signal.value_cur == pytest.approx(0.005, abs=1e-4)
    assert signal.signal == "within"


def test_the_customer_series_are_dropped_when_no_customer_column_is_mapped() -> None:
    mapping = {key: value for key, value in MAPPING.items() if value != "customer"}
    data = run_data(daily_rows(*month_span("2011-01", 11)), mapping)

    reported = {signal.series for signal in compute_signals(data, history_window(data))}

    assert "active_customers" not in reported and "frequency" not in reported
    assert "revenue" in reported and "aov" in reported


# --- stage 2 / stage 3 consistency -------------------------------------------


def test_stage_3_recomputes_exactly_what_stage_2_reported() -> None:
    """The contract between the stages (docs/AI_PIPELINE.md section 7.1).

    If these ever diverge the report contradicts itself: the headline would
    explain a change the KPI cards do not show.
    """
    rows = []
    for month in range(1, 12):
        for day in (3, 11, 19, 27):
            rows.append(row(date(2011, month, day), qty=2.0, price=10.0, customer="Alice"))
            rows.append(row(date(2011, month, day), qty=1.0, price=25.0, customer="Bob"))
        rows.append(row(date(2011, month, 28), qty=-1.0, price=10.0, customer="Alice"))
    rows.append(row(date(2011, 11, 30), qty=3.0, price=10.0, customer="Carol"))
    data = run_data(rows)

    table = monthly_series(data)
    core = data.metrics.core
    period = data.metrics.period

    for label, month in (("current", period.current), ("previous", period.previous)):
        assert table.loc[month, "revenue"] == pytest.approx(
            getattr(core, f"revenue_{label}")), f"revenue disagrees for {label}"
        assert table.loc[month, "orders"] == getattr(core, f"orders_{label}"), (
            f"orders disagree for {label}")
        assert table.loc[month, "active_customers"] == getattr(
            core, f"active_customers_{label}"), f"active customers disagree for {label}"


def test_the_monthly_series_matches_stage_2s_own_revenue_by_month() -> None:
    data = run_data(daily_rows(*month_span("2011-01", 11)))

    table = monthly_series(data)

    for entry in data.metrics.core.revenue_by_month:
        if entry.period in table.index:
            assert table.loc[entry.period, "revenue"] == pytest.approx(entry.revenue)
