"""What the minimum spread must and must NOT suppress (session 3D3).

Every constant in the spread floor was chosen against this table, so the table
lives in the repo rather than in a scratchpad. The point is the second column:
a floor tuned only against false alarms will happily silence a real collapse,
which is what happened the first time these constants were picked. Each case
names the size of move that decides it, so a later session can see what the
numbers were bought with rather than having to trust them.
"""

import pytest

from stages.diagnose.frame import history_window
from stages.diagnose.signals import compute_signals
from tests.stages.diagnose.diagnose_fixtures import full_months, run_data
from tests.stages.diagnose.test_rule_one_reliability import months


def revenue(values: list[float], current: float):
    data = run_data(full_months(months([*values, current])))
    return next(signal for signal in compute_signals(data, history_window(data))
                if signal.series == "revenue")


def high_volume_tight() -> list[float]:
    """A shop turning over 1,000,000 a month, varying by 0.2%. Any business
    with enough volume looks like this: the law of large numbers makes its
    month-to-month variation small relative to its level."""
    return [1_000_000.0 + (2000 if index % 2 else -2000) for index in range(11)]


# --- must FIRE: the floor may not widen a chart that has a real width --------


@pytest.mark.parametrize("current,move", [(980_000.0, "-2.0%"), (985_000.0, "-1.5%")])
def test_a_real_drop_on_a_high_volume_shop_still_fires(current: float, move: str) -> None:
    """The measured half-width here is about 12,580, so a 2% drop is roughly a
    ten-sigma event and the most important line in the report.

    A floor of 2% of the centre - the first value chosen for this constant -
    computes to 19,996 and puts that drop inside the limits. Step 7 acts on
    rule 1, so suppressing it does not soften the headline, it deletes it.
    """
    signal = revenue(high_volume_tight(), current)

    assert (signal.signal, signal.rule) == ("below", 1), (
        f"a {move} drop reported as {signal.signal} against limits "
        f"({signal.lower:,.0f}, {signal.upper:,.0f})")
    assert signal.limits_method != "minimum_spread"


def test_a_decline_that_worsens_is_still_caught() -> None:
    """An unchanging -1%/month decline must stay quiet (that is
    test_rule_one_reliability), but a decline that deepens by a third must
    not. The two are about four percentage points apart in year-over-year
    terms, which is what sets the ceiling on the year-over-year floor."""
    values = [119.0 - index for index in range(23)]

    signal = revenue(values, 92.0)  # yoy about -14%, against an ordinary -11%

    assert (signal.signal, signal.rule) == ("below", 1)


def test_a_steady_grower_that_flips_negative_is_caught() -> None:
    """A business growing 2% year over year, every month, that swings to -2.5%.
    This is the single event the product exists to surface, and a
    year-over-year floor of 5 points hides it."""
    values = [1000.0 * 1.02 ** (index // 12) + (2 if index % 2 else -2)
              for index in range(24)]

    signal = revenue(values, values[-12] * 0.975)

    assert signal.mode == "yoy"
    assert (signal.signal, signal.rule) == ("below", 1)


# --- must stay QUIET: the cases the floor exists for -------------------------


def test_a_flat_shop_stays_quiet_on_a_rounding_move() -> None:
    signal = revenue([500.0] * 9 + [520.0, 500.0, 540.0], 501.0)

    assert (signal.signal, signal.rule) == ("within", None)


def test_a_steady_grower_stays_quiet_on_an_ordinary_month() -> None:
    values = [1000.0 * 1.02 ** (index // 12) + (2 if index % 2 else -2)
              for index in range(24)]

    signal = revenue(values, values[-12] * 1.02)

    assert signal.signal == "within"


def test_a_series_with_no_variation_at_all_reports_the_floor_it_used() -> None:
    """When neither estimator measures anything, the limits come from the
    floor - and the file has to say so. Reporting the estimator that returned
    zero would make a floored chart indistinguishable from a measured one,
    which is the exact thing `limits_method` was added to prevent."""
    signal = revenue([100.0] * 10, 100.0)

    assert signal.limits_method == "minimum_spread"
    assert (signal.lower, signal.upper) == (99.0, 101.0)
    assert signal.signal == "within"


def test_a_money_series_with_no_level_and_no_variation_cannot_be_charted() -> None:
    """A shop whose net revenue is exactly zero every month has neither a
    measured spread nor a level to take a share of. Inventing a currency floor
    would be picking a number out of the air, and zero-width limits call one
    cent a special cause - so the honest answer is that there is no chart
    (3D3 doubt-review R1).
    """
    signal = revenue([0.0] * 11, 0.01)

    assert signal.signal == "insufficient_history"
    assert signal.rule is None
    assert signal.center is None
