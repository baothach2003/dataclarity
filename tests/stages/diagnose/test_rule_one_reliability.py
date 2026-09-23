"""The four defects that make rule 1 itself unreliable (session 3D3).

Each of these predates 3D3 - they survived sessions 3B, 3C and 3D2 - and each
went unnoticed for the same reason: there was no test. They are written here
from the SYMPTOM a shop owner would see, before any fix, so the failure is on
the record rather than only the repair.

Rule 1 is now the only rule step 7 acts on (AI_PIPELINE 7.5), so a false rule-1
signal is not a cosmetic problem: it reaches the headline.
"""

import pytest

from stages.diagnose.frame import history_window
from stages.diagnose.signals import compute_signals
from stages.diagnose.thresholds import (
    XMR_MIN_SPREAD_RATE,
    XMR_MIN_SPREAD_YOY_POINTS,
)
from tests.stages.diagnose.diagnose_fixtures import full_months, run_data


def months(values: list[float], start_year: int = 2010) -> dict[str, float]:
    labels = {}
    for index, value in enumerate(values):
        year, month = divmod(index, 12)
        labels[f"{start_year + year}-{month + 1:02d}"] = value
    return labels


def signals_for(values: list[float], current: float, series: str = "revenue"):
    data = run_data(full_months(months([*values, current])))
    return next(signal for signal in compute_signals(data, history_window(data))
                if signal.series == series)


# --- C1b: a stable business that grows steadily ------------------------------


def test_a_business_growing_steadily_does_not_signal_every_month() -> None:
    """The symptom: a shop whose revenue is identical every month, then grows
    1%, is told the growth is a statistical special cause.

    In year-over-year mode the centre is 0 (no change, every month), every
    moving range is 0, so the limits are (0.0, 0.0) and the margin falls back
    to XMR_ABS_FLOOR_DEFAULT - one millionth of a percentage point. A +1%
    month clears that by a factor of a million.

    This is the most stable business imaginable and the engine cries wolf on
    it. "The engine's credibility rests on the months it says nothing
    happened" (signals.py).
    """
    signal = signals_for([100.0] * 23, 101.0)

    assert signal.mode == "yoy"
    assert signal.signal == "within", (
        f"a 1% rise reported as {signal.signal} against limits "
        f"({signal.lower}, {signal.upper})")
    assert signal.rule is None


def test_a_flat_series_gets_limits_wide_enough_to_mean_something() -> None:
    """The same defect stated as a property rather than a scenario: no chart
    should have zero width, because every conceivable move is then outside
    it."""
    signal = signals_for([100.0] * 23, 100.0)

    assert signal.upper > signal.lower


# --- R6: a business in a constant-rate decline -------------------------------


def test_a_constant_rate_decline_is_not_a_fresh_alarm_every_month() -> None:
    """The symptom: a shop losing about 1% a month, steadily, for two years.

    The decline is real and the report should say so - but it is the SAME
    decline every month, not a new special cause each time. A constant rate
    makes the year-over-year series nearly constant too, so its moving ranges
    collapse toward zero and the limits close to a hair's width around the
    centre. Every ordinary month then falls outside them.
    """
    values = [119.0 - index for index in range(23)]

    signal = signals_for(values, 95.0)

    assert signal.mode == "yoy"
    assert signal.signal == "within", (
        f"an unchanging decline reported as {signal.signal} against limits "
        f"({signal.lower}, {signal.upper})")


def test_a_real_break_in_a_declining_business_is_still_caught() -> None:
    """The other half of the same rule: quietening the steady decline must not
    silence a genuine acceleration of it."""
    values = [119.0 - index for index in range(23)]

    signal = signals_for(values, 20.0)  # a collapse, not the usual -1

    assert (signal.signal, signal.rule) == ("below", 1)


# --- R4: the margin floors are in the wrong units in YoY mode ----------------


def test_the_return_rate_floor_is_in_the_units_the_series_actually_carries() -> None:
    """`XMR_ABS_FLOOR_RATE` is documented as "one percentage point" of a
    return rate expressed as a fraction - right for level mode, meaningless in
    year-over-year mode, where the series carries a PERCENTAGE CHANGE. A
    return rate moving from 2% to 3% of orders is a +50 in YoY units; a floor
    of 0.01 does nothing there.

    The symptom: a shop whose return rate is steady gets a signal on ordinary
    wobble.
    """
    # Ten orders a month, one of them a return: a steady rate of 0.1, so the
    # year-over-year series is defined and flat at 0% change.
    data = run_data(_monthly_returns(returns=1, sales=9, months_count=25))
    signals = compute_signals(data, history_window(data))
    rate_signal = next(s for s in signals if s.series == "return_rate")

    assert rate_signal.mode == "yoy"
    assert rate_signal.signal == "within", (
        f"a steady return rate reported as {rate_signal.signal} against limits "
        f"({rate_signal.lower}, {rate_signal.upper})")


def test_the_minimum_spread_is_in_the_units_the_series_carries() -> None:
    """R4 pinned at the mechanism, because the symptom does not expose it.

    A perfectly steady return rate gives a year-over-year series of exactly 0
    and a current value of exactly 0, so it stays within limits however wrong
    their units are - which is why this defect survived three sessions with a
    passing suite. R4 is the mechanism behind C1b and R6 rather than a symptom
    of its own, so it is tested where it lives.

    In year-over-year mode every series carries a PERCENTAGE CHANGE, so the
    floor must be in percentage points. A floor written for money (one
    millionth) or for a rate expressed as a fraction (0.01) protects nothing
    there: a +1% month clears one millionth of a point by a factor of a
    million.
    """
    from stages.diagnose.signals import _minimum_spread

    # Same series, same centre, different mode: the floor must differ.
    assert _minimum_spread("revenue", "yoy", 0.0) == XMR_MIN_SPREAD_YOY_POINTS
    assert _minimum_spread("return_rate", "yoy", 0.0) == XMR_MIN_SPREAD_YOY_POINTS
    # ...and in level mode it is in that series' own units, not a percentage.
    assert _minimum_spread("return_rate", "level", 0.02) == XMR_MIN_SPREAD_RATE
    assert _minimum_spread("revenue", "level", 1000.0) == pytest.approx(10.0)
    # A yoy floor that scaled with the centre would be zero exactly where it
    # is needed, since an unchanged business has a yoy centre of 0.
    assert _minimum_spread("revenue", "yoy", 0.0) > 0


def _monthly_returns(returns: int, sales: int, months_count: int) -> list[dict]:
    """`sales` ordinary orders and `returns` refunds in every month, so the
    return rate is identical month to month."""
    from datetime import date

    from tests.stages.diagnose.diagnose_fixtures import row

    rows = []
    for index in range(months_count):
        year, month = 2010 + index // 12, index % 12 + 1
        last = 28 if month == 2 else 30
        for order in range(sales):
            rows.append(row(date(year, month, min(order + 1, last)), qty=2, price=10.0))
        for refund in range(returns):
            rows.append(row(date(year, month, last), qty=-1, price=10.0))
    return rows


# --- the margin, now that it does one job ------------------------------------


def _column(values: list[float]) -> "pd.Series":
    import pandas as pd

    return pd.Series(values, index=list(months(values)))


def test_float_noise_does_not_decide_which_side_of_the_line_a_point_is_on() -> None:
    """Rule 2 asks whether eight points sit on one side of the centre. On a
    series that is constant in business terms, they differ from the centre
    only in the last bits of the float - and a bare `point > center` then lets
    that noise decide, firing a run rule on a business where nothing moved.

    Tested at `_classify` because the noise has to be exact: through the
    pipeline it would be whatever the arithmetic happened to leave.

    The offset is 1e-13, not something smaller: at a centre of 100 the float
    spacing is about 1.4e-14, so `100.0 + 1e-15` IS `100.0` and a test using
    it proves nothing. A first version of this test made exactly that mistake
    and the mutation check caught it.
    """
    from stages.diagnose.signals import _classify

    centre = 100.0
    values = [centre + 1e-13] * 9
    assert values[0] != centre  # the noise survives the addition
    column = _column(values)
    history = list(months(values))[:-1]

    signal, rule = _classify("revenue", centre + 1e-13, centre, 98.0, 102.0,
                             column, history[-1], history)

    assert (signal, rule) == ("within", None)


def test_a_series_centred_on_zero_is_still_protected_from_residue() -> None:
    """The one case the minimum spread cannot cover: a non-rate series whose
    baseline nets to exactly zero, where a share of the centre is also zero.

    A shop whose sales and returns cancel every month has a revenue centre of
    0.0, so the spread floor contributes nothing and the limits really are a
    point. The residue floor in the margin is what keeps the 4.4e-16 such a
    month leaves behind from being a special cause.
    """
    from stages.diagnose.signals import _classify

    values = [0.0] * 9
    column = _column(values)
    history = list(months(values))[:-1]

    signal, rule = _classify("revenue", 4.4e-16, 0.0, 0.0, 0.0,
                             column, history[-1], history)

    assert (signal, rule) == ("within", None)


# --- R3: the current month has no year-ago comparator ------------------------


def test_a_collapse_is_not_hidden_by_a_missing_year_ago_month() -> None:
    """The symptom: the shop was shut in February last year, so this February
    has nothing to compare against year-over-year - and an 80% collapse is
    reported as "we cannot say" instead of falling back to the level chart,
    which would catch it instantly.

    This is 3B doubt-review finding 1 in its mirror image: that fix made the
    mode depend on whether the HISTORY yields usable year-over-year points,
    and never asked whether the CURRENT month has one.
    """
    values = [1000.0] * 13 + [0.0] + [1000.0] * 11  # February 2011 shut
    assert len(values) == 25

    signal = signals_for(values, 200.0)  # February 2013: an 80% collapse

    assert signal.signal != "insufficient_history", (
        f"an 80% collapse reported as {signal.signal}; mode={signal.mode}")
    assert (signal.signal, signal.rule) == ("below", 1)
    assert signal.mode == "level", "no year-ago comparator, so the level chart"


@pytest.mark.parametrize("current", [1000.0, 980.0])
def test_the_fallback_does_not_invent_a_rule_one_signal(current: float) -> None:
    """The fallback must not manufacture the kind of signal step 7 acts on.

    Rule 2 DOES fire on this series, and that is the known re-firing
    limitation rather than a new defect: the shut month drags the mean centre
    down to 958, so every ordinary month at 1000 sits above it. Step 7 acts on
    rule 1 only (AI_PIPELINE 7.5) precisely because of this, and re-baselining
    - which would fix it properly - is in the Backlog after 3D2.

    So this asserts what actually matters: no rule-1 signal on an ordinary
    month. Asserting `within` here would be asserting that a defect recorded
    as open is closed.
    """
    values = [1000.0] * 13 + [0.0] + [1000.0] * 11

    signal = signals_for(values, current)

    assert signal.rule != 1, f"{signal.signal} on an ordinary month"
