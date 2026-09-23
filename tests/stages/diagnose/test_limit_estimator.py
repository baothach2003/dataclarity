"""How wide the XmR limits are, and which estimator decided (session 3D2).

Two failures pull in opposite directions, which is why the estimator has a
fallback rather than a single rule:

- an outlier makes the AVERAGE moving range huge, so the limits swallow
  everything and the series can never signal (3B finding 3a);
- half-identical months make the MEDIAN moving range exactly zero, so the
  limits collapse to a point and a rounding move is a special cause.

The second is not a degenerate corner. Flat, rounded and small-integer series
are ordinary, and session 3D2 shipped the collapse before measuring it.
"""

import pytest

from stages.diagnose.frame import history_window
from stages.diagnose.signals import compute_signals
from tests.stages.diagnose.diagnose_fixtures import full_months, run_data


def revenue_signal(values: list[float], current: float):
    labels = {}
    for index, value in enumerate([*values, current]):
        year, month = divmod(index, 12)
        labels[f"{2011 + year}-{month + 1:02d}"] = value
    data = run_data(full_months(labels))
    return next(signal for signal in compute_signals(data, history_window(data))
                if signal.series == "revenue")


def test_one_extreme_month_no_longer_swallows_the_limits() -> None:
    """3B finding 3a, hand-computed. Fourteen months around 100 with one at
    1200. The thirteen moving ranges are 3, 4, 3, 2, 3, 1, 3, 1, 1099, 1100,
    1, 1, 2; their MEDIAN is 3, so the half-width is 3.145 * 3 = 9.4 and the
    limits are about 90 to 110. Their AVERAGE is 171, which would have given
    a half-width of 456 - limits from -350 to 550, inside which no real month
    could ever fall.
    """
    values = [102.0, 99.0, 103.0, 100.0, 98.0, 101.0, 102.0, 99.0,
              100.0, 1199.0, 99.0, 100.0, 101.0, 99.0]

    signal = revenue_signal(values, 40.0)

    assert signal.limits_method == "median_moving_range"
    assert signal.upper - signal.lower < 40.0  # not the ~900 of the average
    # And a real collapse to 40 is now seen rather than swallowed.
    assert (signal.signal, signal.rule) == ("below", 1)


def test_a_flat_shop_does_not_get_zero_width_limits() -> None:
    """The regression session 3D2 shipped and then measured: nine identical
    months make half the moving ranges zero, so the median is zero and the
    limits collapse onto the centre. A move of one unit on a centre of 500 -
    0.2% - was reported as a special cause.

    The fallback puts this series back on the average moving range, which is
    bit-for-bit what it used before, so it stays quiet.
    """
    values = [500.0] * 9 + [520.0, 500.0, 540.0]

    signal = revenue_signal(values, 501.0)

    assert signal.limits_method == "mean_moving_range"
    assert signal.upper > signal.lower  # not a point
    assert (signal.signal, signal.rule) == ("within", None)


def test_a_rounded_series_also_takes_the_fallback() -> None:
    """Four of seven moving ranges are zero, so the median is zero. Rounded
    figures are ordinary in a real file, not a contrived shape.

    The series deliberately does not trend: an earlier version of this test
    climbed 100 to 103 and then expected silence on its highest point, which
    the chart is right to call unusual. The fallback is about the WIDTH of the
    limits, not about suppressing real movement.
    """
    values = [100.0, 100.0, 101.0, 101.0, 100.0, 100.0, 101.0, 101.0]

    signal = revenue_signal(values, 101.0)

    assert signal.limits_method == "mean_moving_range"
    assert signal.upper > signal.lower
    assert signal.signal == "within"


def test_the_estimator_that_ran_is_recorded_on_every_signal() -> None:
    """Thach, 3D2: a later change of estimator must be visible in the file
    rather than silently changing what every verdict means."""
    values = [100.0, 101.0, 99.0, 100.0, 102.0, 98.0, 100.0, 101.0, 100.0]

    signals = compute_signals(*_run(values, 100.0))

    assert signals
    assert all(signal.limits_method in ("median_moving_range", "mean_moving_range")
               for signal in signals)


def _run(values: list[float], current: float):
    labels = {}
    for index, value in enumerate([*values, current]):
        year, month = divmod(index, 12)
        labels[f"{2011 + year}-{month + 1:02d}"] = value
    data = run_data(full_months(labels))
    return data, history_window(data)


def test_a_series_with_no_variation_at_all_is_still_quiet() -> None:
    # Every moving range is zero, so both estimators give zero width. The
    # margin from 3B is what keeps this quiet, and it is worth pinning: this
    # is the one shape where the fallback cannot help.
    signal = revenue_signal([100.0] * 10, 100.0)

    assert signal.upper == signal.lower
    assert signal.signal == "within"
    assert signal.rule is None


@pytest.mark.parametrize("current", [100.0, 100.0001])
def test_a_flat_series_tolerates_rounding_noise(current: float) -> None:
    signal = revenue_signal([100.0] * 10, current)

    assert signal.signal == "within"
