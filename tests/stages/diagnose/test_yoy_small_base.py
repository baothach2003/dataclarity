"""A year-ago month too small to divide by (session 3D6).

3D4 refused a base that is not positive or is floating-point residue. It left
the magnitude half open: a base of 12.50 on a shop turning over 50,000 is
positive, is not residue, and divides to +399,900%. While year-over-year rows
were verdicts (ADR-0006, until ADR-0007 in 3D6b) that was an actionable rule-1
finding, and on the same file it fired the masked-shift alert with
`basis = yoy`, which headline rule 4 stated without the seasonal hedge. Since
ADR-0007 the row is descriptive, and the guard keeps the absurd figure off the
page.

Written from the symptom first, before the fix. The first three tests are the
damage; the rest pin what the fix must NOT exclude, because a threshold that
only ever hears about false alarms is how 3D3's first floor came to silence a
real 2% drop.
"""

import pandas as pd
import pytest

from contracts.diagnosis import is_actionable, is_verdict
from stages.diagnose.frame import history_window
from stages.diagnose.signals import _as_yoy, compute_signals
from stages.diagnose.thresholds import YOY_MIN_BASE_SHARE
from tests.stages.diagnose.diagnose_fixtures import full_months, run_data
from tests.stages.diagnose.test_rule_one_reliability import months

# A deterministic ripple, so the year-over-year chart has a measured spread.
# A perfectly flat shop hides the centre-drag symptom: every moving range is
# zero, the estimator falls back to the average, and one huge point widens
# the limits enough to swallow itself. Period 7 so no two months a year apart
# carry the same offset, which would make every year-over-year point zero.
RIPPLE = (300.0, -200.0, 100.0, -400.0, 250.0, -150.0, 50.0)


def rippled(level: float, count: int) -> list[float]:
    return [level + RIPPLE[index % len(RIPPLE)] * level / 50000.0
            for index in range(count)]


def run(values: list[float]):
    data = run_data(full_months(months(values)))
    return data, compute_signals(data, history_window(data))


def by_series(signals, name: str):
    return next(signal for signal in signals if signal.series == name)


# --- the damage ---------------------------------------------------------------


def test_a_year_ago_month_of_12_50_does_not_make_an_ordinary_month_a_finding() -> None:
    """The reproduction from PROJECT_PLAN 3D6, verbatim in shape: a shop at
    50,000 a month whose year-ago month took 12.50, and a current month back
    at an ordinary 50,000. Nothing happened this month.

    Before the fix, three series report +399,900% as an actionable rule-1
    verdict: revenue, and - because the fixture books one order a month -
    `aov` and `units_per_order` with it.
    """
    values = [50000.0] * 12 + [12.5] + [50000.0] * 11 + [50000.0]

    _, signals = run(values)

    fabricated = [(s.series, s.value_cur) for s in signals if is_actionable(s)]
    assert fabricated == [], f"actionable verdicts on a flat month: {fabricated}"
    revenue = by_series(signals, "revenue")
    # The month has rows, so the fallback says the base was unusable rather
    # than absent - the existing 3D4 label, whose meaning this session widens.
    assert revenue.mode == "level"
    assert revenue.mode_fallback == "unusable_year_ago_base"
    assert is_verdict(revenue) is False


# `test_the_small_base_does_not_fire_headline_rule_4` was deleted in 3D6b. It
# pinned the route from a fabricated `aov` verdict into the masked-shift alert;
# since ADR-0007 the alert reads no step-4 row, so that route no longer exists,
# and on its fixture (50,000 -> 50,000, every contribution zero) it passed with
# the base guard deleted - vacuous (3D6b doubt-review #8). A flat month not
# firing the alert is pinned in test_level_is_descriptive.py.


def test_a_tiny_base_inside_the_baseline_does_not_drag_the_centre() -> None:
    """The other route the same month takes into a verdict, named in the plan:
    "yields 406,300%, which then drags the mean centre and leaves every
    ordinary month firing".

    Here the tiny month is not the current month's comparator but the base of
    a BASELINE point (2011-06 against 2010-06). Its +399,900% sits in the
    history, the centre is its mean, and an ordinary current month lands tens
    of thousands of points below that centre - so `below`, rule 1, on a month
    where nothing happened.
    """
    values = rippled(50000.0, 25)
    values[5] = 12.5   # 2010-06

    _, signals = run(values)

    revenue = by_series(signals, "revenue")
    assert revenue.mode == "yoy"   # one baseline point lost, eleven remain
    assert abs(revenue.center) < 5.0, (
        f"centre {revenue.center:.1f} points - the tiny base is still in it")
    assert not is_actionable(revenue), (
        f"{revenue.signal} rule {revenue.rule} on an ordinary month")


# --- what the fix must NOT exclude ----------------------------------------------


def test_a_shop_that_really_was_tiny_still_fires_its_real_growth() -> None:
    """The case PROJECT_PLAN names: a REAL 4,000% jump, from a shop that
    genuinely was tiny a year ago. The threshold must separate "too small to
    divide by" from "small, and the growth is real".

    Here the base is small against the CURRENT month and ordinary against the
    shop's own history, which is what "typical" means in the guard. So the
    year-over-year chart survives and the jump is an actionable verdict.

    What this pins is the choice of YARDSTICK, not the constant: the base is
    about 100% of its typical level, so it passes for any share below 1. A
    yardstick taken from the current month - a cap on the result - would
    refuse it. The recovery test below is the one that bounds the constant.
    """
    values = rippled(1220.0, 24) + [50000.0]

    _, signals = run(values)

    revenue = by_series(signals, "revenue")
    assert revenue.mode == "yoy"
    assert (revenue.signal, revenue.rule) == ("above", 1)
    assert revenue.value_cur == pytest.approx((50000.0 / values[12] - 1) * 100)


def test_a_recovery_after_a_year_long_slump_still_fires() -> None:
    """A real recovery a median-based guard makes hard, and the shape that
    bounds the constant from above. Not the hardest: a DEEPER slump is lost
    (see the known limits at the end of this file).

    Twelve months at 1,220 - exactly half of a 24-month window - then the
    current month back at 50,000. The median of an even window averages its
    two middle values, so the shop's "typical" month comes out at about
    25,600 and the base sits at 1,220 / 25,610 = 4.76% of it. Any share above
    that throws the base away and turns a genuine 4,000% recovery into a
    descriptive row. With noise the edge moves down: the sweep's first loss
    was at 0.045 with 5% monthly noise and at 0.035 with 20%, and 0.05 lost
    26 of 80 seeds even at 5%. This fixture has no noise, so it pins only the
    ceiling of 4.76% - `thresholds.py` records the rest.
    """
    values = [50000.0] * 12 + [1220.0] * 12 + [50000.0]

    _, signals = run(values)

    revenue = by_series(signals, "revenue")
    assert revenue.mode == "yoy"
    assert (revenue.signal, revenue.rule) == ("above", 1)


def test_one_freak_month_does_not_void_every_ordinary_base() -> None:
    """Why "typical" is a MEDIAN. A mean would let one freak month set the
    bar for every base in the file: at 100,000,000 in one month, the mean of
    this file is 4,214,583, three per cent of that is 126,437, and
    every ordinary 50,000 base would be thrown away.

    That is 3D8's defect - an anchor one month can move - and a new guard must
    not reintroduce it on a different threshold.
    """
    values = rippled(50000.0, 25)
    values[20] = 1e8

    _, signals = run(values)

    assert by_series(signals, "revenue").mode == "yoy"


def test_a_shop_is_judged_against_its_recent_self_not_its_distant_past() -> None:
    """Why "typical" is taken over the HISTORY WINDOW, the months the chart
    itself judges against, and not over the whole file.

    A shop that turned over 5,000,000 a month more than two years ago and
    50,000 since. Over the whole file the median is the old figure, and a
    perfectly ordinary 50,000 base is one per cent of it. Over the history
    window the shop is what it is now.
    """
    values = [5_000_000.0] * 25 + rippled(50000.0, 24)

    _, signals = run(values)

    assert by_series(signals, "revenue").mode == "yoy"


# --- the guard itself, unit level -----------------------------------------------


def _table(values: list[float], name: str = "revenue") -> pd.DataFrame:
    index = list(months(values))
    return pd.DataFrame({name: pd.Series(values, index=index)})


def test_the_share_is_measured_against_the_typical_level() -> None:
    """A specification pin, not evidence: it states what the constant means
    and would pass for any value of it. The evidence is the sweep recorded in
    `thresholds.py` and the two recovery tests above.

    Typical 50,000, so the line sits at exactly 1,500 (0.03 * 50,000 is exact
    in binary floating point). A base on the line is kept; one below is not.
    """
    assert YOY_MIN_BASE_SHARE * 50000.0 == 1500.0
    for base, kept in ((1500.0, True), (1499.0, False)):
        values = [50000.0] * 12 + [base] + [50000.0] * 12
        table = _table(values)
        history = list(table.index[:-1])

        change = _as_yoy(table, history)["revenue"].iloc[-1]

        assert pd.notna(change) is kept, f"base {base}: {change}"


def test_typical_is_a_magnitude_for_a_series_that_can_go_negative() -> None:
    """Revenue, `aov`, `units_per_order` and `price_per_unit` are signed. On a
    refund-heavy shop that nets -1,000 in most months and +20 in the rest,
    the size of a typical month is 1,000 - its magnitude - and a base of 20 is
    two per cent of it. Measured on the positive months alone the base would
    be ordinary, and it divides to +4,900%: not a growth rate on a shop that
    swings by a thousand either way.

    Rewritten after the mutation check: the first version used +1,000 for the
    positive months, which made the magnitude and the positive months agree,
    so removing the `abs` passed it.
    """
    values = [-1000.0] * 14 + [20.0] * 10
    values[12] = 20.0         # an ordinary positive month, as the base
    values.append(1000.0)     # the current month, which divides by it
    table = _table(values)

    change = _as_yoy(table, list(table.index[:-1]))["revenue"].iloc[-1]

    assert pd.isna(change), f"a base of 20 on a shop of +-1,000 divided to {change}"


def test_a_base_with_no_typical_level_to_judge_it_is_refused() -> None:
    """The direction of the unknown case. With no history there is no typical
    level, so nobody knows whether the base is big enough to divide by - and
    under the asymmetry an unknown base is treated as too small: refusing it
    costs a verdict, accepting it can fabricate one.

    Reached from `compute_signals` whenever every history month is zero -
    `return_rate` on a shop with no returns - and harmless there, since every
    base is then zero. Pinned with an ORDINARY base so a later change cannot
    quietly give the permissive answer.
    """
    # An ORDINARY base, so the refusal can only come from the missing typical
    # level - a tiny base here would pass for the wrong reason.
    table = _table([50000.0] * 25)

    change = _as_yoy(table, [])["revenue"].iloc[-1]

    assert pd.isna(change), f"a base judged against nothing divided to {change}"


def test_a_shop_shut_most_of_the_year_is_still_guarded() -> None:
    """Found by the 3D6 doubt-review, after the first version shipped: a
    market stall trading June to September at 50,000 and nothing otherwise.
    Months without rows are charted as 0.0, so two thirds of the history is
    zero, the median magnitude is ZERO, three per cent of it is zero, and the
    12.50 June a year ago divided to +399,900% exactly as before the fix -
    actionable on revenue, `aov` and `units_per_order`.

    "Typical" is the size of a month the shop actually trades, so it is the
    median over the non-zero months.
    """
    labels, values = [], []
    for year in (2010, 2011, 2012, 2013):
        for month in range(1, 13 if year < 2013 else 7):   # ends June 2013
            labels.append(f"{year}-{month:02d}")
            values.append(50000.0 if 6 <= month <= 9 else 0.0)
    values[labels.index("2012-06")] = 12.5
    # `months()` numbers from January, so pass the table through directly.
    data = run_data(full_months(dict(zip(labels, values))))

    signals = compute_signals(data, history_window(data))

    # Asserted on what the GUARD does - the comparator is refused and the
    # series drops to level mode - not on "no actionable verdict", which since
    # ADR-0007 is true of every row and so would pass with the guard deleted
    # (3D6b mutation check).
    for name in ("revenue", "aov", "units_per_order"):
        row_ = next(s for s in signals if s.series == name)
        assert (row_.mode, row_.mode_fallback) == ("level", "unusable_year_ago_base"), (
            f"{name}: {row_.mode} {row_.value_cur} from a 12.50 base")


def test_a_residue_base_in_a_mostly_shut_series_is_refused() -> None:
    """An outcome pin, recorded with its history because the mechanism moved
    twice in this session.

    The first version of the share took its median over every history month,
    so a series that netted exactly zero in more than half of them had a
    typical level of 0, a floor of 0, and 3D4's residue test was the only
    thing between 1.4e-17 and a figure of 7e21 per cent. The mutation check
    found that no test pinned it. The doubt-review then found that the same
    zero median disarmed the share for every shop shut most of the year, and
    the median moved to TRADING months, so on this fixture the share now
    refuses the residue base itself. This test pins the outcome, whichever
    check produces it; the next one pins the residue check.
    """
    values = [0.0] * 14 + [1000.0] * 10
    values[12] = 1.4e-17      # a month whose sales and refunds cancelled
    values.append(1000.0)
    table = _table(values)
    history = list(table.index[:-1])

    change = _as_yoy(table, history)["revenue"].iloc[-1]

    assert pd.isna(change), f"a residue base divided to {change}"


def test_the_residue_check_is_still_load_bearing() -> None:
    """Found by doubt-review cycle 2, after I had documented the residue check
    as implied by the share. It is not: the floor is a MEDIAN, so when half
    the trading months are themselves residue - 4.4e-16, a month of cancelling
    sales and refunds - the floor is residue-sized too and a 1.4e-17 base
    clears it. Only 3D4's residue check then stands between it and 7.1e21 per
    cent. The input is implausible (13 of 24 months cancelling exactly); the
    claim it refutes was still false.
    """
    values = [4.4e-16] * 13 + [1000.0] * 11
    values[12] = 1.4e-17
    values.append(1000.0)
    table = _table(values)
    history = list(table.index[:-1])

    change = _as_yoy(table, history)["revenue"].iloc[-1]

    assert pd.isna(change), f"a residue base divided to {change}"


def test_a_rate_series_is_guarded_the_same_way() -> None:
    """`return_rate` is a fraction, so the guard is scale-free by necessity:
    one per cent of a typical 3% rate is excluded, half of it is kept."""
    for base, kept in ((0.0003, False), (0.015, True)):
        values = [0.03] * 12 + [base] + [0.03] * 12
        table = _table(values, "return_rate")

        change = _as_yoy(table, list(table.index[:-1]))["return_rate"].iloc[-1]

        assert pd.notna(change) is kept, f"rate base {base}: {change}"


# --- KNOWN LIMITS of the chart ----------------------------------------------
#
# The guard removes only the absurd end. Two doubt-review cycles found three
# families it cannot reach, each run to the headline and classified (Thach,
# 3D6). Two of them fabricated a verdict - until ADR-0007 (3D6b) made every
# step-4 row descriptive in v1. The CHART behaviour is unchanged and pinned
# here as it is; what changed is that none of it is a verdict. The Backlog's
# "unusualness verdicts" must fix these before it switches verdicts back on.


def test_known_limit_a_trickle_off_season_disarms_the_guard() -> None:
    """Was FABRICATE in 3D6; descriptive since ADR-0007. Open June to
    September at 50,000, trickling 300 a month the
    rest of the year. Eight of twelve months are off-season, so the median
    trading month is the trickle, three per cent of it is 9, and a 12.50
    in-season comparator clears it: +400,300%, actionable, on a June where
    nothing happened. The yardstick cannot tell the season from the trickle
    without calendar information a 24-month file does not have."""
    values = [(50000.0 if 6 <= index % 12 + 1 <= 9 else 300.0)
              * (1 + RIPPLE[index % 7] / 50000.0) for index in range(42)]
    values[29] = 12.5   # 2012-06, the comparator of 2013-06

    _, signals = run(values)

    assert sorted(s.series for s in signals if s.rule == 1 and s.mode == "yoy") == [
        "aov", "revenue", "units_per_order"]
    assert by_series(signals, "revenue").value_cur == pytest.approx(400300.0, rel=1e-3)
    assert [s.series for s in signals if is_actionable(s)] == []


def test_known_limit_a_baseline_base_above_the_share_still_drags_the_centre() -> None:
    """Was FABRICATE (predating 3D6); descriptive since ADR-0007. A
    year-ago month at 10% of normal is kept
    as a base - it is a trading month - and its +900% point sits in the
    baseline, where the mean centre is pulled far above zero. An ordinary
    month then lands below the lower limit: `below`, rule 1, actionable. The
    share only removed the cliff below 3%; 3.5%, 5% and 25% behave the same
    (scratchpad triage.py, L3). A robust yoy centre is 3D9's candidate."""
    values = rippled(50000.0, 25)
    values[5] = 5000.0            # 2010-06 at 10% of normal
    values[24] = 50000.0 * 0.995  # an ordinary month

    _, signals = run(values)

    revenue = by_series(signals, "revenue")
    assert revenue.mode == "yoy"
    assert (revenue.signal, revenue.rule) == ("below", 1)
    assert not is_actionable(revenue)


def test_known_limit_a_deep_slump_loses_its_real_recovery() -> None:
    """SUPPRESS - the safe direction, and the one the asymmetry accepts. A
    year at 700 against a normal 50,000, then the shop is back: a real
    +7,043% recovery. The median averages the two halves, the base is 2.8%
    of it, and the series goes to level mode, where it is descriptive. The
    level row still says `above`; it is not a verdict."""
    values = [50000.0] * 12 + [700.0] * 12 + [50000.0]

    _, signals = run(values)

    revenue = by_series(signals, "revenue")
    assert revenue.mode == "level"
    assert revenue.mode_fallback == "unusable_year_ago_base"
    assert not is_actionable(revenue)
