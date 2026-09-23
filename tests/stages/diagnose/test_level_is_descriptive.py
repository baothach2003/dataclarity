"""Level-mode signals are descriptive, never verdicts (ADR-0006).

Four sessions tried to make a level chart judge a seasonal month. The last of
them shipped a gate that could not run on a 24-month file at all: the history
window holds exactly one prior occurrence of the current calendar month, and
that occurrence IS the comparator whose failure put the series in level mode.
The information the gate needed was the information that was missing.

So the policy moved instead of the code. These tests pin it from the symptom
each session produced.
"""

from datetime import date, timedelta

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


def test_a_masked_shift_on_a_short_file_still_fires_and_says_so() -> None:
    """The one exception to ADR-0006, and the reason it is an exception.

    The alert needs a step-4 row for its conjunction. Resting it on
    `gross_to_net` alone was considered and rejected: that ratio divides by
    the change in revenue, so on the flat months this alert exists for it
    fires every time. A short file has only level rows, so refusing to read
    them would disable the alert on exactly the files it was written for.

    `basis` records what it rested on, because a level basis can be right that
    composition moved and wrong that the movement was unusual.
    """
    data = run_data(_masked_shift_rows())
    signals = compute_signals(data, history_window(data))

    lever = compute_lever(data, signals)

    assert lever.gross_to_net is None, "the fixture must have flat revenue"
    assert lever.masked_shift_alert is True
    assert lever.masked_shift_basis == "level"
    # ...and the row it rested on is still not a verdict for anything else.
    customers = next(s for s in signals if s.series == "active_customers")
    assert (customers.signal, customers.rule) == ("below", 1)
    assert is_verdict(customers) is False


def test_an_alert_that_does_not_fire_claims_no_basis() -> None:
    """`masked_shift_basis` is null exactly when the alert is null or false.
    A basis on a quiet month would imply a check leaned on something.
    """
    labels, year, month = {}, 2010, 1
    for _ in range(14):
        labels[f"{year:04d}-{month:02d}"] = 50000.0
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)

    data = run_data(full_months(labels))
    lever = compute_lever(data, compute_signals(data, history_window(data)))

    assert lever.masked_shift_alert is False
    assert lever.masked_shift_basis is None


def test_an_all_year_over_year_run_needs_no_hedge() -> None:
    """The same shift on a file long enough to chart year over year: every
    component row is `yoy`, so the basis is `yoy` and 3F states the alert
    plainly instead of hedging it as seasonal.
    """
    data = run_data(_masked_shift_rows(months=26))
    signals = compute_signals(data, history_window(data))

    lever = compute_lever(data, signals)

    assert lever.masked_shift_alert is True
    assert lever.masked_shift_basis == "yoy"


def test_a_year_over_year_row_is_a_verdict() -> None:
    """The other half of the policy, and the half a negative test cannot give.

    Every other test here asserts what is NOT a verdict. Without this one the
    whole policy is satisfied by "nothing is ever a verdict", which would
    leave T3 permanently inconclusive and the engine unable to say a quiet
    month was quiet.
    """
    data = run_data(_masked_shift_rows(months=26))

    signals = compute_signals(data, history_window(data))

    revenue = next(s for s in signals if s.series == "revenue")
    assert revenue.mode == "yoy"
    assert is_verdict(revenue) is True


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


def _mixed_mode_rows(months: int = 26) -> list[dict]:
    """The masked shift, plus a refund-heavy month exactly twelve before the
    current one. That breaks REVENUE's year-ago base, so the revenue-derived
    series fall to level mode, while the customer COUNT that month stays clean
    and keeps its year-over-year chart - one run carrying both modes."""
    rows, year, month = [], 2010, 1
    for index in range(months):
        last = index == months - 1
        broken = index == months - 13
        customers, price = (4, 250.0) if last else (10, 100.0)
        first = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
        for customer in range(customers):
            on_last_day = last and customer == customers - 1
            day = end if on_last_day else first + timedelta(days=customer)
            rows.append(row(day, qty=1.0, price=price, customer=f"C{customer}"))
            if broken:
                rows.append(row(day, qty=-1.2, price=price,
                                customer=f"C{customer}"))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return rows


def test_one_level_row_among_the_contributors_keeps_the_hedge() -> None:
    """`mode` is decided per series, so one run's components can disagree.

    Here `aov` is on a level chart and `active_customers` on a year-over-year
    one, and both fire rule 1. The basis must be `level`.

    The first version of this rule said the stronger basis wins, and that was
    wrong in a way worth recording: headline rule 4 names the two largest
    OPPOSING contributions, which on this file are customers and aov - so the
    evidence that a named contributor moved unusually is the level row, and an
    unrelated year-over-year row elsewhere in the run is no reason to drop the
    hedge on it (3D5b review N9). The basis is about what the sentence rests
    on, not about the best row in the file.
    """
    data = run_data(_mixed_mode_rows())
    signals = compute_signals(data, history_window(data))
    firing = {s.series: s.mode for s in signals
              if s.signal in ("above", "below") and s.rule == 1}

    lever = compute_lever(data, signals)

    # The fixture only means something while it really does carry both modes.
    assert firing.get("aov") == "level"
    assert firing.get("active_customers") == "yoy"
    assert lever.masked_shift_alert is True
    assert lever.masked_shift_basis == "level"


def test_the_ratio_path_records_a_basis_too() -> None:
    """Every other masked-shift test here has revenue exactly flat, which
    takes the `gross_to_net is None` branch - the one where the ratio has no
    denominator. So all of them were exercising the same half of the function
    (3D5b review R3).

    This one moves revenue by 20 on contributions of about 1,050 each, so the
    ratio is real, comfortably above `MASKED_GROSS_TO_NET`, and the
    conjunction is evaluated as written.
    """
    data = run_data(_masked_shift_rows(last_price=255.0))
    signals = compute_signals(data, history_window(data))

    lever = compute_lever(data, signals)

    assert lever.gross_to_net is not None, "this must NOT be the flat branch"
    assert lever.gross_to_net >= 3.0
    assert lever.masked_shift_alert is True
    assert lever.masked_shift_basis == "level"


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


def test_a_rule_two_row_is_a_verdict_but_never_a_cause() -> None:
    """The distinction one predicate could not carry.

    A run of eight points on one side of the centre IS a judgement about the
    month, so it blocks T3 - that is 3D4's deliberate asymmetry, where the bar
    for asserting nothing happened is higher than the bar for acting. It may
    never BECOME a headline cause, because rule 2 re-fires every month until
    the anomalous point leaves the window (3D2).

    `is_verdict` answers the first question, `is_actionable` the second.
    """
    data = run_data(full_months(_rule_two_run()))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert (signal.mode, signal.rule) == ("yoy", 2)
    assert is_verdict(signal) is True       # blocks T3
    assert is_actionable(signal) is False   # cannot be a cause


def test_a_year_over_year_rule_one_row_is_actionable() -> None:
    """The positive case, for the same reason `is_verdict` needed one: without
    it `is_actionable` is satisfied by returning False for everything, and no
    hypothesis could ever be supported.
    """
    data = run_data(_masked_shift_rows(months=26))

    customers = next(s for s in compute_signals(data, history_window(data))
                     if s.series == "active_customers")

    assert (customers.mode, customers.rule) == ("yoy", 1)
    assert is_actionable(customers) is True


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
