"""Year-over-year against a base that is not a usable denominator (3D4).

Both defects predate this session and both live in `_as_yoy`. They are written
here from the symptom first, before any fix, because that is the only form in
which the damage is visible: the arithmetic looks unremarkable and the numbers
it produces are finite, plausible and wrong.

The engine divides by the year-ago month. That is only a growth rate while the
year-ago month is a positive quantity. Revenue is signed in this codebase -
returns are negative-quantity rows, and ADR-0004 rejected LMDI precisely
because a period can net to zero or below - so the denominator can be
negative, and two negatives divide to a confident positive.
"""

import pandas as pd
import pytest

from contracts.diagnosis import is_verdict

from stages.diagnose.frame import history_window
from stages.diagnose.signals import _signal_for, compute_signals
from tests.stages.diagnose.diagnose_fixtures import full_months, run_data
from tests.stages.diagnose.test_rule_one_reliability import months


def signal_for(values: list[float], current: float, series: str = "revenue"):
    data = run_data(full_months(months([*values, current])))
    return next(signal for signal in compute_signals(data, history_window(data))
                if signal.series == series)


# --- the sign inversion -------------------------------------------------------


def test_a_doubling_of_losses_is_not_reported_as_growth() -> None:
    """The symptom, and the reason 3D4 is a prerequisite of 3E rather than a
    follow-up: a shop whose month went from -100 to -200 - twice the loss -
    reports `value_cur = +100.0`, `signal = "above"`, `rule = 1`.

    That is the rule step 7 acts on, so the inversion reaches T3 and the
    masked-shift alert with the direction reversed: the engine calls a
    doubling of losses an unusually good month.
    """
    values = [1000.0] * 12 + [-100.0] + [1000.0] * 11  # the comparator is index 12

    signal = signal_for(values, -200.0)

    assert signal.signal != "above", (
        f"a doubling of losses reported as {signal.signal} "
        f"(value_cur={signal.value_cur})")
    # The figure reported is the month itself, not a percentage invented by
    # dividing by a negative. Firing `below` here is correct and wanted: the
    # month really is far below this shop's normal.
    assert signal.value_cur == pytest.approx(-200.0)


def test_a_negative_year_ago_month_is_not_a_growth_base() -> None:
    """Stated as a property rather than a scenario: there is no percentage
    growth from a negative base, so the engine must not invent one."""
    values = [1000.0] * 12 + [-100.0] + [1000.0] * 11

    signal = signal_for(values, -200.0)

    # Either the series charts in level mode, or it says it cannot say - but
    # it must not report a year-over-year figure computed from -100.
    assert signal.mode == "level" or signal.signal == "insufficient_history"


def test_no_percentage_is_invented_from_a_negative_base() -> None:
    """The mirror of the inversion: -100 to +500 divides to -600%, so on the
    year-over-year chart a shop climbing out of a loss reads as a catastrophic
    fall.

    What the fix guarantees is narrower than "the verdict flips", and saying
    so precisely matters: the series charts in LEVEL mode and reports the
    month's own figure. 500 against a baseline of about 1000 is genuinely
    below normal, so `below` here is right - what would be wrong is reporting
    it as -600%.
    """
    values = [1000.0] * 12 + [-100.0] + [1000.0] * 11

    signal = signal_for(values, 500.0)

    assert signal.mode == "level"
    assert signal.value_cur == pytest.approx(500.0)


# --- the non-finite base ------------------------------------------------------


def test_a_denormal_year_ago_month_does_not_abort_the_stage() -> None:
    """`(x - tiny) / tiny` overflows to inf, which `pd.isna` does not catch.
    The `Signal` validator then refuses the non-finite figure and the whole
    stage raises, instead of this one series degrading.

    Stage 3 is supposed to degrade rather than fail: CONTRACTS section 7 says
    it still writes its file when the AI is unavailable, and the same spirit
    applies to one unusable series.

    Tested against `_as_yoy` directly, because a denormal cannot survive the
    pipeline: the fixture turns revenue into a quantity, and 5e-324 / 10
    underflows to 0.0, which the zero guard already caught. Asserting this
    end-to-end would pass whatever `_as_yoy` did, which is no assertion at
    all.
    """
    from stages.diagnose.signals import _as_yoy

    index = [f"2011-{month:02d}" for month in range(1, 13)]
    index += [f"2012-{month:02d}" for month in range(1, 13)]
    table = pd.DataFrame({"revenue": pd.Series([5e-324] + [1000.0] * 23, index=index)})

    change = _as_yoy(table, list(table.index))["revenue"]

    assert pd.isna(change["2012-01"]), "a denormal base must not yield inf"


@pytest.mark.parametrize("base,value,label", [
    (0.0, 1000.0, "a zero base divides to infinity"),
    (5e-324, 1000.0, "a denormal base overflows upward"),
    (5e-324, -1000.0, "a denormal base overflows DOWNWARD"),
])
def test_no_base_can_produce_a_non_finite_change(
    base: float, value: float, label: str,
) -> None:
    """Every way the division can leave the finite numbers, in one table.

    The downward case matters on its own: a guard that drops only positive
    infinity leaves `-inf` to reach the contract's finiteness validator and
    abort the stage. The mutation check found exactly that gap, and a zero
    base was passing only because the non-finite guard cleaned up after the
    `> 0` test rather than because the `> 0` test was pinned.
    """
    from stages.diagnose.signals import _as_yoy

    index = [f"2011-{month:02d}" for month in range(1, 13)]
    index += [f"2012-{month:02d}" for month in range(1, 13)]
    series = pd.Series([base] + [value] * 23, index=index)

    change = _as_yoy(pd.DataFrame({"revenue": series}), list(series.index))["revenue"]

    assert pd.isna(change["2012-01"]), label


def test_many_non_positive_months_send_the_series_to_level_mode() -> None:
    """The question this session was asked to answer: what happens to a file
    where MANY months are non-positive.

    Each bad base removes one usable year-over-year point, so enough of them
    drop the series below `XMR_MIN_BASELINE_POINTS` and it charts in level
    mode - which is the honest outcome, since level mode charts the months as
    they actually were, negatives included. Measured in the 3D4 sweep: a
    heavy-refund shop had 7 of 13 bases non-positive, leaving 6 usable.
    """
    values = [1000.0 if index % 2 else -200.0 for index in range(24)]

    signal = signal_for(values, -200.0)

    assert signal.mode == "level"
    assert signal.value_cur == pytest.approx(-200.0)


def test_price_per_unit_goes_negative_when_the_refunds_are_priced_differently() -> None:
    """The claim this test used to make was FALSE, and the fixture it made it
    with could not have shown otherwise.

    It asserted `price_per_unit` is immune because revenue and units flip
    together in a refund-heavy month. That holds only while every line carries
    the same price - and the fixture used a single price of 10.0, so
    `price_per_unit` was constant across all 25 months and arithmetically
    incapable of going negative. The two assertions were `x == approx(x)` and
    "the signal is one of the four values the Literal allows": neither can
    fail under any implementation.

    Hand-checked. One sale of 1 unit at 1000 and four refunds of 3 units at
    50: revenue is 1000 - 600 = +400, units are 1 - 12 = -11, so price per
    unit is 400 / -11 = -36.36. Revenue stays POSITIVE and survives the base
    guard while price per unit is negative - the two series disagree, which is
    the case the immunity argument assumed away.
    """
    from datetime import date

    from tests.stages.diagnose.diagnose_fixtures import row
    from stages.diagnose.signals import monthly_series

    rows = [row(date(2010, 1, 1), qty=1, price=1000.0)]
    rows += [row(date(2010, 1, day + 2), qty=-3, price=50.0) for day in range(4)]
    for index in range(1, 25):
        year, month = 2010 + index // 12, index % 12 + 1
        last = 28 if month == 2 else 30
        rows += [row(date(year, month, min(line + 1, last)), qty=1, price=100.0)
                 for line in range(5)]
    data = run_data(rows)

    table = monthly_series(data)
    first = table.index[0]

    assert table.loc[first, "revenue"] == pytest.approx(400.0)
    assert table.loc[first, "price_per_unit"] == pytest.approx(-400 / 11)

    # The month twelve later is the one that would divide by it. Its
    # year-over-year value must be dropped, not inverted. The series stays in
    # yoy mode, and correctly so - this is a baseline point, not the current
    # month's comparator, so only one point is lost.
    from stages.diagnose.signals import _as_yoy

    change = _as_yoy(table, list(table.index))["price_per_unit"]
    assert pd.isna(change["2011-01"]), (
        f"a base of {table.loc[first, 'price_per_unit']:.2f} produced "
        f"{change['2011-01']}")


def test_a_residue_base_does_not_become_a_percentage() -> None:
    """A month whose sales and refunds cancel nets 1.4e-17 rather than 0.0 -
    `thresholds.py` says so in as many words - and `> 0` admitted it as a
    denominator, producing a year-over-year figure of 7.2e21 per cent.

    Two files identical in every business sense were being routed down
    different charts by the sign of a rounding residue: negative residue
    dropped and safe, positive residue kept and catastrophic.
    """
    from datetime import date

    from tests.stages.diagnose.diagnose_fixtures import row

    rows = [row(date(2010, 1, 1), qty=2, price=0.01),
            row(date(2010, 1, 2), qty=7, price=0.01),
            row(date(2010, 1, 3), qty=-9, price=0.01)]
    for index in range(1, 25):
        year, month = 2010 + index // 12, index % 12 + 1
        last = 28 if month == 2 else 30
        rows += [row(date(year, month, min(line + 1, last)), qty=1, price=100.0)
                 for line in range(10)]
    data = run_data(rows)

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert signal.value_cur is None or abs(signal.value_cur) < 1e6, (
        f"value_cur={signal.value_cur!r} came from a residue denominator")


def test_the_guard_still_lets_a_real_alarm_ring() -> None:
    """Every other test here has the shape "the wrong number is gone". This
    one has the shape "the right alarm still fires", which is the shape that
    was missing when 3D3 shipped a floor that silenced a real 2% drop.

    A steady shop, one non-positive month a year ago, and a current month that
    genuinely halves. Whatever mode the series ends up in, the collapse must
    be reported.
    """
    values = [1000.0] * 12 + [-50.0] + [1000.0] * 11

    signal = signal_for(values, 500.0)

    assert (signal.signal, signal.rule) == ("below", 1), (
        f"a halving reported as {signal.signal} in {signal.mode} mode "
        f"against ({signal.lower}, {signal.upper})")


# --- the fallback this guard can cause (3D4 doubt-review C3) ------------------


def _seasonal(january_year_ago: float, current: float) -> dict[str, float]:
    """A shop whose December is three times an ordinary month, 24 complete
    months ending in January. The reviewer's C3 fixture, kept verbatim in
    shape: the non-positive month is exactly the current month's year-ago
    comparator, so the current-month test fails with NO baseline erosion -
    11 usable points remain, three more than the eight required."""
    labels, year, month = {}, 2010, 2
    for _ in range(24):
        labels[f"{year:04d}-{month:02d}"] = 150000.0 if month == 12 else 50000.0
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    keys = list(labels)
    labels[keys[11]] = january_year_ago   # 2011-01
    labels[keys[-1]] = current            # 2012-01, the month being diagnosed
    return labels


def _flat(january_year_ago: float, current: float) -> dict[str, float]:
    """A shop with no seasonality, so its level chart is tight enough to see a
    halving and the fallback is the right answer. The seasonal fixture cannot
    be used for fallback tests any more: since 3D5 that series refuses the
    fallback, which is the point of the session."""
    labels, year, month = {}, 2010, 2
    for _ in range(24):
        labels[f"{year:04d}-{month:02d}"] = 50000.0
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    keys = list(labels)
    labels[keys[11]] = january_year_ago
    labels[keys[-1]] = current
    return labels


def test_a_series_records_why_it_fell_back_from_year_over_year() -> None:
    """The fallback is NOT always an improvement, and the output has to say it
    happened so step 7 can weigh it.

    Hand-checked against two files differing only in one month twelve months
    before the current one. With an ordinary January the series charts year
    over year and fires `below` rule 1 on a 50% collapse; with a January that
    netted -2000 it falls back to level, where the seasonal limits span
    7,587 to 105,282 and the same collapse reads `within`.

    Updated in 3D5: the fixture is now FLAT rather than seasonal. On the
    seasonal shop this series no longer falls back at all - it refuses,
    because that chart cannot see a halving - so the seasonal file can no
    longer demonstrate a fallback. The flag itself is unchanged.
    """
    data = run_data(full_months(_flat(-2000.0, 50000.0)))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert signal.mode == "level"
    assert signal.mode_fallback == "unusable_year_ago_base"
    assert signal.insufficient_reason is None  # it IS charted


def test_an_absent_year_ago_month_is_recorded_differently() -> None:
    """"We were shut that month" is a gap; "that month netted zero or below"
    is a business event. Step 7 should be able to tell them apart."""
    labels = _flat(50000.0, 50000.0)
    del labels["2011-01"]  # the shop was shut
    data = run_data(full_months(labels))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert signal.mode_fallback == "no_year_ago_value"


def test_a_healthy_series_records_no_fallback() -> None:
    data = run_data(full_months(_seasonal(50000.0, 50000.0)))

    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert signal.mode == "yoy"
    assert signal.mode_fallback is None


def test_the_fallback_does_not_restore_the_series_alarm() -> None:
    """Stated as a test so nobody reads the flag as a fix.

    The collapse is real - 25,000 against a normal January of 50,000 - and
    NO series fires rule 1 anywhere in the run, before 3D5 or after it.

    What changed is the CLAIM, not the alarm. The series reports `within` on
    a level chart - and since ADR-0006 that row is descriptive, so step 7 may
    not read it as "the month sat inside what this business normally does".
    No session can turn this file into a detection, because the information a
    detection needs is the comparator that failed.
    """
    data = run_data(full_months(_seasonal(-2000.0, 25000.0)))

    signals = compute_signals(data, history_window(data))
    revenue = next(s for s in signals if s.series == "revenue")

    assert [s.series for s in signals if s.rule == 1] == []
    assert revenue.mode == "level"
    assert is_verdict(revenue) is False


# --- 3D5: is the level chart informative enough to fall back to? -------------


def test_the_flat_shop_still_falls_back_and_still_catches_its_collapse() -> None:
    """The other side, which is what stops this becoming option (d).

    3D3's R3: a shop shut last February must still catch this February's 80%
    collapse. Its level chart is tight, so falling back is right and the
    collapse is caught. Refusing the fallback here would revert the fix R3
    was written for.
    """
    values = [1000.0] * 13 + [0.0] + [1000.0] * 11

    signal = signal_for(values, 200.0)

    assert signal.mode == "level"
    assert (signal.signal, signal.rule) == ("below", 1)


def _december(multiple: float, january_year_ago: float,
              current: float) -> dict[str, float]:
    """A shop whose December is `multiple` times an ordinary month."""
    labels, year, month = {}, 2010, 2
    for _ in range(24):
        labels[f"{year:04d}-{month:02d}"] = (
            50000.0 * (multiple if month == 12 else 1.0))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    keys = list(labels)
    labels[keys[11]] = january_year_ago
    labels[keys[-1]] = current
    return labels


def test_a_missing_current_value_is_not_reported_as_too_few_points() -> None:
    """`insufficient_reason` exists to say WHY a series has no chart. On the
    branch where the baseline is complete but the current month has no value,
    it says `too_few_points` - which is the one thing that is not true there.

    A field that reports a plausible wrong reason is worse than no field: a
    reader of the contract, or step 7, cannot tell "this shop is too new" from
    "this shop had no orders last month", and the second is a fact about the
    current month that belongs in the report.
    """
    history = [f"2011-{month:02d}" for month in range(1, 13)]
    # Twelve solid baseline points - four more than the eight required - and
    # nothing at all for the month under diagnosis.
    column = pd.Series([50000.0] * 12, index=history)

    signal = _signal_for("revenue", column, "2012-01", history, "level")

    assert signal.signal == "insufficient_history"
    assert signal.insufficient_reason == "no_current_value", (
        f"a complete baseline reported as {signal.insufficient_reason!r}")


# --- what the width test alone does NOT catch (3D5 doubt-review) --------------


def _three_years(december_multiple: float, broken_december: float,
                 current: float) -> dict[str, float]:
    """36 complete months ending in December, so the month being diagnosed is
    the shop's PEAK month and the file still holds one good December."""
    labels = {f"{year}-{month:02d}":
              (50000.0 * december_multiple if month == 12 else 50000.0)
              for year in (2010, 2011, 2012) for month in range(1, 13)}
    labels["2011-12"] = broken_december   # the comparator, unusable
    labels["2012-12"] = current
    return labels


def test_a_rule_two_run_survives_the_refusal() -> None:
    """Refusing the chart must not delete what the chart observed.

    AI_PIPELINE 7.5 keeps rule-2 signals in the output, unacted on, and T3
    reads them to decide it cannot call a month routine. A blind level chart
    can still hold a legitimate eight-month run, and discarding the whole row
    loses that row twice over: the observation and the T3 block.
    """
    labels, year, month = {}, 2010, 2
    for _ in range(24):
        labels[f"{year:04d}-{month:02d}"] = 150000.0 if month == 12 else 50000.0
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    for label in list(labels)[-8:]:
        labels[label] = 30000.0          # a sustained decline
    labels["2011-01"] = 1e-4
    labels["2012-01"] = 30000.0

    data = run_data(full_months(labels))
    signal = next(s for s in compute_signals(data, history_window(data))
                  if s.series == "revenue")

    assert signal.rule == 2, (
        f"the rule-2 run was discarded: {signal.signal} / "
        f"{signal.insufficient_reason}")


def test_a_flat_baseline_does_not_report_too_few_points() -> None:
    """The third branch that sets `insufficient_reason` and the second that
    lied. Twelve baseline months that all netted exactly zero leave no measured
    spread and no scale to borrow a floor from, so no chart is drawn - but the
    points are there, and saying `too_few_points` sends a reader looking for
    more history that would not help.
    """
    history = [f"2011-{month:02d}" for month in range(1, 13)]
    column = pd.Series([0.0] * 12 + [500.0], index=[*history, "2012-01"])

    signal = _signal_for("revenue", column, "2012-01", history, "level")

    assert signal.signal == "insufficient_history"
    assert signal.insufficient_reason == "no_measurable_spread"