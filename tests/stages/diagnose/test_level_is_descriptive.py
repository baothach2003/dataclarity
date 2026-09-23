"""Level-mode signals are descriptive, never verdicts (ADR-0006) - and
since ADR-0007 year-over-year rows are too, in v1.

Four sessions tried to make a level chart judge a seasonal month. The last of
them shipped a gate that could not run on a 24-month file at all: the history
window holds exactly one prior occurrence of the current calendar month, and
that occurrence IS the comparator whose failure put the series in level mode.
The information the gate needed was the information that was missing.

So the policy moved instead of the code. These tests pin it from the symptom
each session produced.
"""

from datetime import date, timedelta

import pytest

from contracts.diagnosis import Signal, is_actionable, is_verdict
from stages.diagnose.frame import history_window
from stages.diagnose.lever import compute_lever
from stages.diagnose.signals import compute_signals
from stages.diagnose.tree import compute_tree
from tests.stages.diagnose.diagnose_fixtures import full_months, row, run_data


def _seasonal_24(december_multiple: float, broken_comparator: float,
                 current: float) -> dict[str, float]:
    """24 complete months ending in December, so the month being diagnosed is
    the peak AND the file is the project's reference length - the length at
    which 3D5's gate is structurally inert."""
    labels = {f"{year}-{month:02d}":
              (50000.0 * december_multiple if month == 12 else 50000.0)
              for year in (2010, 2011) for month in range(1, 13)}
    labels["2010-12"] = broken_comparator
    labels["2011-12"] = current
    return labels


def test_a_halved_peak_month_on_a_24_month_file_is_not_a_verdict() -> None:
    """The symptom 3D5 could not fix. This shop's December is 150,000; this
    December is 75,000. On the level chart that lands ABOVE a centre built
    from eleven ordinary months, so the chart reports something confident and
    wrong - and no width or seasonality test can catch it here, because the
    only prior December in the window is the broken comparator.

    The signal is still computed and still written to the file. What changes
    is that T3 may not read it.
    """
    halved = run_data(full_months(_seasonal_24(3.0, -2000.0, 75000.0)))
    ordinary = run_data(full_months(_seasonal_24(3.0, -2000.0, 150000.0)))

    def revenue(data):
        return next(s for s in compute_signals(data, history_window(data))
                    if s.series == "revenue")

    collapse, normal = revenue(halved), revenue(ordinary)

    # The symptom itself, asserted rather than described: the chart says
    # something confident, and it says the SAME confident thing about a
    # December that lost half its revenue and one that did not.
    assert (collapse.signal, collapse.rule) == ("above", 1)
    assert (collapse.signal, collapse.rule) == (normal.signal, normal.rule)
    assert (collapse.lower, collapse.upper) == (normal.lower, normal.upper)
    # That indistinguishability is why the row cannot be a verdict, and no
    # width or seasonality test can rescue it: the only prior December in the
    # window is the broken comparator, so the file does not contain what a
    # gate would need to tell these two apart.
    assert collapse.mode == "level"
    assert is_verdict(collapse) is False


def test_an_ordinary_december_on_a_level_chart_is_not_a_verdict() -> None:
    """The mirror, and the reason this is a policy rather than a filter on
    `within`: an ORDINARY December on a seasonal shop fires `above` against an
    off-season centre. Suppressing only `within` would leave the engine
    confidently reporting a normal month as unusual.
    """
    data = run_data(full_months(_seasonal_24(3.0, -2000.0, 150000.0)))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert (signal.mode, signal.signal) == ("level", "above")
    assert is_verdict(signal) is False


def test_a_flat_short_file_leaves_t3_with_nothing_to_stand_on() -> None:
    """T3 lands in 3E; what this pins is the input 3E must read.

    A 14-month file has no year-over-year chart at all, so every series is
    level mode and none is a verdict. "No verdict fired" must not be read as
    "nothing happened" - that is the S11 failure in a new shape - so T3 is
    `inconclusive`, and its evidence lists the series that were not judged.
    """
    labels, year, month = {}, 2010, 1
    for _ in range(14):
        labels[f"{year:04d}-{month:02d}"] = 50000.0
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    data = run_data(full_months(labels))
    signals = compute_signals(data, history_window(data))

    assert [s.series for s in signals if is_verdict(s)] == []
    assert all(s.mode == "level" for s in signals)


def _masked_shift_rows(months: int = 14, *, last_price: float = 250.0) -> list[dict]:
    """Revenue at 1,000 a month, reached with ten customers at 100 each -
    except the last month, which reaches 4 x `last_price` with four customers.
    At the default the total does not move at all while the composition moves
    hard, which is the case DIAGNOSE_DESIGN 1.2 says a "did revenue move?"
    report misses entirely.

    `last_price` is what selects the branch under test. At 250 revenue is
    exactly flat and `gross_to_net` has no denominator; above it the ratio is
    real and the conjunction is evaluated as written. On a 14-month file every
    row is level mode.
    """
    rows, year, month = [], 2010, 1
    for index in range(months):
        last = index == months - 1
        customers, price = (4, last_price) if last else (10, 100.0)
        first = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
        for customer in range(customers):
            on_last_day = last and customer == customers - 1
            day = end if on_last_day else first + timedelta(days=customer)
            rows.append(row(day, qty=1.0, price=price, customer=f"C{customer}"))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return rows


def test_a_masked_shift_on_a_short_file_fires_on_the_tree_alone() -> None:
    """Rewritten by ADR-0007. Under ADR-0006 this alert was the one consumer
    allowed to read a level row, and recorded a `basis`. Since no step-4 row
    is a verdict in v1, the alert reads none: it is decided on the tree, and
    the basis field is gone with the signals it described.

    Hand-checked. Thirteen months of ten customers at 100 (typical month
    1,000, floor 200), then four customers at 250 - revenue flat at 1,000:
      phi_customers = -6 * (100 + 250) / 2    = -1,050
      phi_aov       = +150 * (10 + 4) / 2     = +1,050
    Both clear 200 and revenue did not move, so the alert fires - on a
    14-month file where every step-4 row is level mode and none is a verdict.
    """
    data = run_data(_masked_shift_rows())
    signals = compute_signals(data, history_window(data))

    lever = compute_lever(data, history_window(data))

    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(-1050.0)
    assert effects["aov"] == pytest.approx(1050.0)
    assert lever.gross_to_net is None, "the fixture must have flat revenue"
    assert lever.masked_shift_alert is True
    assert [s.series for s in signals if is_verdict(s)] == []


def test_a_quiet_month_does_not_fire_the_alert() -> None:
    """Fourteen identical months. Revenue did not move, so `gross_to_net` is
    null and the month counts as flat - flatness alone would fire here. Every
    contribution is zero, so nothing clears the floor and it does not."""
    labels, year, month = {}, 2010, 1
    for _ in range(14):
        labels[f"{year:04d}-{month:02d}"] = 50000.0
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    data = run_data(full_months(labels))
    lever = compute_lever(data, history_window(data))

    assert lever.masked_shift_alert is False


def test_a_year_over_year_row_is_not_a_verdict_in_v1() -> None:
    """FLIPPED by ADR-0007. This was the positive case - "a year-over-year
    row is a verdict" - written because without it the ADR-0006 policy was
    satisfied by "nothing is ever a verdict". That is now the policy: a
    year-over-year point compares with one year-ago month, which cannot vouch
    for itself on a 24-month file. The Backlog's "unusualness verdicts" (a
    comparator of three prior years AND a robust centre) is what would turn
    this assertion back."""
    data = run_data(_masked_shift_rows(months=26))

    signals = compute_signals(data, history_window(data))

    revenue = next(s for s in signals if s.series == "revenue")
    assert revenue.mode == "yoy"
    assert is_verdict(revenue) is False


def test_a_year_over_year_row_with_no_chart_is_still_not_a_verdict() -> None:
    """`is_verdict` is a contract helper, so its domain is any `Signal` - one
    built by hand, or one read back from a `diagnosis.json` written by a later
    version of the stage. `mode` alone is not enough: a row with no limits has
    nothing to judge against whatever mode it claims.

    The pipeline cannot currently produce this combination (entry to yoy mode
    requires the baseline and the current value that `insufficient_history`
    denies, and the yoy floor of 2.0 points keeps the spread positive), so it
    is asserted on the contract directly rather than through a fixture that
    would only be testing the entry conditions.
    """
    signal = Signal(
        series="revenue", mode="yoy", value_cur=None, center=None, lower=None,
        upper=None, signal="insufficient_history", rule=None,
        limits_method="mean_moving_range", insufficient_reason="too_few_points")

    assert is_verdict(signal) is False


def test_the_ratio_path_fires_too() -> None:
    """The other branch. Every flat-revenue test takes `gross_to_net is None`;
    here revenue moves by 20 (four customers at 255), so the ratio is real -
    about 105 - taking the non-null branch of the flatness test (3D5b review
    R3). It does not pin MASKED_GROSS_TO_NET: since floor C the ratio is
    implied (test_no_step4_verdicts.py)."""
    data = run_data(_masked_shift_rows(last_price=255.0))

    lever = compute_lever(data, history_window(data))

    assert lever.gross_to_net is not None, "this must NOT be the flat branch"
    assert lever.gross_to_net >= 3.0
    assert lever.masked_shift_alert is True


def _rule_two_run() -> dict[str, float]:
    """26 months whose last seven alternate high, so the current month sits on
    a run long enough for rule 2 while staying inside the limits."""
    values = [1000.0] * 18 + [1600.0, 2500.0, 1600.0, 2500.0, 1600.0, 2500.0,
                              1600.0, 2000.0]
    labels, year, month = {}, 2010, 1
    for value in values:
        labels[f"{year:04d}-{month:02d}"] = value
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return labels


def test_a_rule_two_row_is_neither_a_verdict_nor_a_cause() -> None:
    """FLIPPED by ADR-0007. Under ADR-0006 a rule-2 row was a verdict that
    blocked T3 (3D4's asymmetry) while never becoming a cause. T3 can no
    longer be supported at all, so there is nothing left for it to block;
    the rule-1-only contract still holds for whatever reads rows later."""
    data = run_data(full_months(_rule_two_run()))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert (signal.mode, signal.rule) == ("yoy", 2)
    assert is_verdict(signal) is False
    assert is_actionable(signal) is False


def test_a_year_over_year_rule_one_row_is_not_actionable_in_v1() -> None:
    """FLIPPED by ADR-0007: this was the positive case for `is_actionable`."""
    data = run_data(_masked_shift_rows(months=26))

    customers = next(s for s in compute_signals(data, history_window(data))
                     if s.series == "active_customers")

    assert (customers.mode, customers.rule) == ("yoy", 1)
    assert is_actionable(customers) is False


def test_a_level_rule_one_row_is_not_actionable() -> None:
    """A level row fires rule 1 readily on a seasonal shop - an ordinary
    December does it - so the mode test has to survive into `is_actionable`
    rather than being replaced by the rule test.
    """
    data = run_data(full_months(_seasonal_24(3.0, -2000.0, 150000.0)))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert (signal.mode, signal.rule) == ("level", 1)
    assert is_actionable(signal) is False
