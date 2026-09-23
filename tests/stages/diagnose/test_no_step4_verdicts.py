"""In v1 no step-4 row is a verdict, and the masked-shift alert rests on the
tree alone (ADR-0007, session 3D6b).

Written from the symptom first. ADR-0006 made level rows descriptive and kept
year-over-year rows as verdicts; 3D6's known limits then showed year-over-year
fabricating actionable verdicts from ONE anomalous comparator (a trickle
off-season, a year-ago month at 10% of normal) and from ONE anomalous
baseline point, through the mean centre. Telling whether a comparator was
itself normal needs three prior years - 45 complete months - and no demo
dataset has them. So the engine stops claiming unusualness at all.
"""

from datetime import date

import pytest

from contracts.diagnosis import LeverFactor, LeverLevel, Signal, is_actionable, is_verdict
from stages.diagnose.frame import history_window
from stages.diagnose.lever import _masked_shift, compute_lever
from stages.diagnose.numbers import typical_magnitude
from stages.diagnose.signals import compute_signals
from stages.diagnose.thresholds import MASKED_GROSS_TO_NET, MASKED_MIN_CONTRIBUTION_SHARE
from tests.stages.diagnose.diagnose_fixtures import full_months, row, run_data
from tests.stages.diagnose.test_rule_one_reliability import months

# --- no row is a verdict ---------------------------------------------------------


def test_a_year_over_year_rule_one_row_is_not_a_verdict() -> None:
    """Before ADR-0007 this row was actionable: year over year, rule 1, a
    chart drawn. It is exactly the shape 3D6's known limits fabricated."""
    row_ = Signal(series="revenue", mode="yoy", value_cur=400300.0, center=-4.2,
                  lower=-20.0, upper=12.0, signal="above", rule=1,
                  limits_method="median_moving_range")

    assert is_verdict(row_) is False
    assert is_actionable(row_) is False


def test_the_3d6_known_limit_still_fires_and_is_not_a_verdict() -> None:
    """The trickle off-season shop from 3D6: open June to September at
    50,000, 300 a month otherwise, a 12.50 June a year ago. The chart still
    computes +400,300% and still says `above`, rule 1 - the row is data - but
    nothing in the run is a verdict any more, so nothing can reach a headline
    as a finding."""
    values = [(50000.0 if 6 <= index % 12 + 1 <= 9 else 300.0) for index in range(42)]
    values[29] = 12.5
    data = run_data(full_months(months(values)))

    signals = compute_signals(data, history_window(data))

    revenue = next(s for s in signals if s.series == "revenue")
    assert (revenue.mode, revenue.signal, revenue.rule) == ("yoy", "above", 1)
    assert [s.series for s in signals if is_verdict(s)] == []


# --- the masked-shift alert, on the tree ---------------------------------------


def _shop(october: list[tuple[str, float]], november: list[tuple[str, float]],
          *, history_level: float = 1200.0) -> list[dict]:
    """Three complete months at `history_level` (one order each from twelve
    customers at history_level / 12), then October and November as given, as
    (customer, price) orders. Every month opens on its 1st, so each is
    complete and the history window holds July to October. The last November
    order falls on the 30th so November is complete too."""
    rows = []
    for month in (7, 8, 9):
        rows += [row(date(2011, month, 1 + index), qty=1, price=history_level / 12,
                     customer=f"H{index}") for index in range(12)]
    rows += [row(date(2011, 10, 1 + index), qty=1, price=price, customer=customer)
             for index, (customer, price) in enumerate(october)]
    rows += [row(date(2011, 11, _day(index, len(november))), qty=1, price=price,
                 customer=customer)
             for index, (customer, price) in enumerate(november)]
    return rows


def _day(index: int, count: int) -> int:
    return 30 if index == count - 1 else 1 + index


def _lever(rows: list[dict]):
    data = run_data(rows)
    return compute_lever(data, history_window(data))


def test_a_masked_shift_below_the_floor_does_not_fire() -> None:
    """Hand-checked. October: 10 customers, one order each at 120 -> 1,200.
    November: 12 customers at 100 -> 1,200. Revenue flat. Frequency 1 -> 1,
    so the three-factor Shapley split reduces to two factors:
      phi_customers = +2 * (120 + 100) / 2 = +220
      phi_aov       = -20 * (10 + 12) / 2  = -220
    The typical month and both compared months are 1,200, so the floor is
    MASKED_MIN_CONTRIBUTION_SHARE * 1,200 = 240 at 0.20 - and this does NOT
    clear it. The next test moves further and does."""
    lever = _lever(_shop([(f"C{i}", 120.0) for i in range(10)],
                         [(f"C{i}", 100.0) for i in range(12)]))

    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(220.0)
    assert effects["aov"] == pytest.approx(-220.0)
    assert MASKED_MIN_CONTRIBUTION_SHARE * 1200.0 == pytest.approx(240.0)
    assert lever.masked_shift_alert is False


def test_a_masked_shift_above_the_floor_fires() -> None:
    """October: 10 customers at 120 -> 1,200. November: 15 customers at 80
    -> 1,200. phi_customers = +5 * (120 + 80) / 2 = +500, phi_aov = -40 *
    (10 + 15) / 2 = -500. Both clear 240, revenue is flat: the alert fires.
    Before ADR-0007 it could not - no component had a step-4 signal on a file
    this short - so the one case the alert exists for went unreported."""
    lever = _lever(_shop([(f"C{i}", 120.0) for i in range(10)],
                         [(f"C{i}", 80.0) for i in range(15)]))

    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(500.0)
    assert effects["aov"] == pytest.approx(-500.0)
    assert lever.masked_shift_alert is True


def test_the_floor_is_measured_against_the_typical_month_not_last_month() -> None:
    """Why the yardstick is the typical month. October was a bad month - 2
    customers at 60, revenue 120 - and November is 3 customers at 40, also
    120. phi_customers = +1 * (60 + 40) / 2 = +50, phi_aov = -20 * 2.5 = -50.
    Against LAST month (120) each side is 42% and would fire. Against the
    typical month (median of 1,200, 1,200, 1,200, 120 = 1,200) each is 4%:
    two small moves on a quiet month, not a masked shift."""
    lever = _lever(_shop([("A", 60.0), ("B", 60.0)],
                         [("A", 40.0), ("B", 40.0), ("C", 40.0)]))

    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(50.0)
    assert lever.masked_shift_alert is False


def test_a_month_where_revenue_really_moved_is_not_masked() -> None:
    """Revenue doubled, so nothing is hidden. October 10 customers at 120
    (1,200); November 25 at 96 (2,400). phi_customers = +15 * (120 + 96) / 2
    = +1,620, phi_aov = -24 * (10 + 25) / 2 = -420. The floor is 0.20 *
    max(1,200, 1,200, 2,400) = 480: the change of 1,200 is far above it, -420
    does not clear it, and gross 2,040 over net 1,200 is 1.7, below 3 - it
    fails on every count."""
    lever = _lever(_shop([(f"C{i}", 120.0) for i in range(10)],
                         [(f"C{i}", 96.0) for i in range(25)]))

    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(1620.0)
    assert effects["aov"] == pytest.approx(-420.0)
    assert lever.gross_to_net == pytest.approx(1.7)
    assert lever.masked_shift_alert is False


def test_no_typical_month_means_no_alert_and_says_why() -> None:
    """A file whose history holds no complete trading month - here a two-month
    export that starts mid-October, which is common - has no yardstick
    for "material", so the check cannot run: the alert is null, never false,
    and carries a reason (ADR-0007 decision 3)."""
    rows = [row(date(2011, 10, 5 + index), qty=1, price=120.0, customer=f"C{index}")
            for index in range(10)]
    rows += [row(date(2011, 11, _day(index, 15)), qty=1, price=80.0, customer=f"C{index}")
             for index in range(15)]

    lever = _lever(rows)

    assert lever.level1 is not None
    assert lever.masked_shift_alert is None
    assert lever.reasons["masked_shift_alert"]


def _history_then(october: list[tuple[str, float, int]],
                   november: list[tuple[str, float, int]]) -> list[dict]:
    """Three complete months of ten customers at 100 (typical month 1,000),
    then October and November as (customer, price, orders) - so a customer
    can order more than once."""
    rows = []
    for month in (7, 8, 9):
        rows += [row(date(2011, month, 1 + index), qty=1, price=100.0,
                     customer=f"H{index}") for index in range(10)]
    day = 1
    for customer, price, count in october:
        for _ in range(count):
            rows.append(row(date(2011, 10, day), qty=1, price=price, customer=customer))
            day += 1
    orders = [(customer, price) for customer, price, count in november for _ in range(count)]
    rows += [row(date(2011, 11, _day(index, len(orders))), qty=1, price=price,
                 customer=customer)
             for index, (customer, price) in enumerate(orders)]
    return rows


def test_an_identity_is_not_a_masked_shift() -> None:
    """Thach, 3D6b: customers x frequency = orders BY DEFINITION, so when
    orders hold steady and the customer count moves, those two factors cancel
    exactly and a three-factor rule reads an identity as a masked shift - on
    that noise structure it fired on 19-39% of months with nothing planted.

    Here 10 customers ordering once each at 100 become 5 customers ordering
    twice each at 100. Orders 10 -> 10, AOV 100 -> 100, revenue 1,000 -> 1,000.
    The three-factor split shows customers -750 against frequency +750; the
    orders x AOV pair shows nothing, and
    the alert does not fire. The customers/frequency story stays in level 1,
    descriptive, and in B1/C1."""
    lever = _lever(_history_then([(f"C{i}", 100.0, 1) for i in range(10)],
                                 [(f"C{i}", 100.0, 2) for i in range(5)]))

    # Hand-checked Shapley with AOV constant at 100 (a null player): customers
    # -5 * (1 + 2) / 2 * 100 = -750, frequency +1 * (10 + 5) / 2 * 100 = +750.
    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(-750.0)
    assert effects["frequency"] == pytest.approx(750.0)
    pair = {f.name: f.contribution for f in lever.masked_shift_pair.factors}
    assert pair == {"orders": 0.0, "aov": 0.0}
    assert lever.masked_shift_alert is False


def test_the_s6_shape_still_fires_on_the_pair() -> None:
    """Scenario S6's shape: customers -40%, AOV +40%, frequency flat. October
    10 customers at 100 (1,000); November 6 at 140 (840). Orders 10 -> 6.
    Floor 0.20 * max(1,000, 1,000, 840) = 200, change -160, under it.
      phi_orders = -4 * (100 + 140) / 2 = -480
      phi_aov    = +40 * (10 + 6) / 2   = +320
    Both clear 200: the alert fires, and the pair it rested on is in the file
    for headline rule 4 to name."""
    lever = _lever(_history_then([(f"C{i}", 100.0, 1) for i in range(10)],
                                 [(f"C{i}", 140.0, 1) for i in range(6)]))

    pair = {f.name: f.contribution for f in lever.masked_shift_pair.factors}
    assert pair["orders"] == pytest.approx(-480.0)
    assert pair["aov"] == pytest.approx(320.0)
    assert lever.masked_shift_alert is True


def _history_at(level: float) -> list[dict]:
    """Three complete months of ten orders at level / 10 (typical = level)."""
    return [row(date(2011, month, 1 + index), qty=1, price=level / 10, customer=f"H{index}")
            for month in (7, 8, 9) for index in range(10)]


def _months(october: list[tuple[str, float]], november: list[tuple[str, float]],
            level: float) -> list[dict]:
    rows = _history_at(level)
    # Several orders may share a day; the last November order is on the 30th
    # so November is complete.
    rows += [row(date(2011, 10, 1 + index % 30), qty=1, price=price, customer=customer)
             for index, (customer, price) in enumerate(october)]
    rows += [row(date(2011, 11, 30 if index == len(november) - 1 else 1 + index % 28),
                 qty=1, price=price, customer=customer)
             for index, (customer, price) in enumerate(november)]
    return rows


def test_a_trough_month_that_fell_75_percent_is_not_flat() -> None:
    """3D6b doubt-review of the pair, case B2 - a FABRICATION in floor C as
    first built. Typical month 1,000; October 20 orders at 10 (200), November
    one order at 50 (50): -75%. The change of 150 was measured against 20% of
    the TYPICAL month (200) and passed as "flat", so headline rule 4 would
    have called a three-quarters collapse stable. The change is now measured
    against 20% of the larger COMPARED month: 0.20 * 200 = 40, and 150 is not
    under it."""
    lever = _lever(_months([(f"C{i}", 10.0) for i in range(20)], [("C0", 50.0)], 1000.0))

    assert lever.masked_shift_alert is False


def test_a_trough_month_that_rose_143_percent_is_not_flat() -> None:
    """Case A of the same review, the mirror. Typical 2,040; October 14
    orders at 20 (280), November 68 orders at 10 (680): +143%. Under the first
    floor C only the three-factor ratio (2.975) happened to stop it. Now the
    change of 400 is measured against 0.20 * 680 = 136 and is not flat -
    stopped by the rule, not by luck."""
    october = [(f"C{i}", 20.0) for i in range(14)]
    november = [(f"C{i % 17}", 10.0) for i in range(68)]
    lever = _lever(_months(october, november, 2040.0))

    assert lever.masked_shift_alert is False
    # ...and by the flatness rule itself: with no ratio at all it still does
    # not fire.
    assert _masked_shift(lever.masked_shift_pair, None, 2040.0, 280.0, 680.0, {}) is False


def test_the_pair_carries_the_integer_order_counts() -> None:
    """Doubt-review of the pair, #8: rebuilding orders as customers x
    frequency gave 29.000000000000004 for 7 customers placing 29 orders, and
    residue in a flat-orders month's contribution. The pair is built from the
    period's own order count."""
    october = [(f"C{i % 7}", 100.0) for i in range(29)]
    november = [(f"C{i % 7}", 100.0) for i in range(29)]
    lever = _lever(_months(october, november, 2900.0))

    orders = next(f for f in lever.masked_shift_pair.factors if f.name == "orders")
    assert (orders.value_prev, orders.value_cur, orders.contribution) == (29.0, 29.0, 0.0)


# --- the decision itself, on hand-built contributions ---------------------------
#
# Every flat two-factor month splits into +x and -x, so no fixture built from
# rows can show ONE side material and the other not. The mutation check found
# that dropping either side, or turning `and` into `or`, left the suite green.
# Since the alert is decided on the orders x AOV pair (Thach, 3D6b), the unit
# tests hand it a pair; the values are placeholders, only the contributions
# are read.


def _level(orders: float, aov: float) -> LeverLevel:
    return LeverLevel(formula="orders*aov", factors=[
        LeverFactor(name="orders", value_prev=1.0, value_cur=1.0, contribution=orders),
        LeverFactor(name="aov", value_prev=1.0, value_cur=1.0, contribution=aov)])


@pytest.mark.parametrize("contributions,expected,label", [
    ((400.0, -200.0), False, "a big rise against a fall under the floor"),
    ((-400.0, 200.0), False, "a big fall against a rise under the floor"),
    ((240.0, -240.0), True, "both sides exactly on the floor (0.2 * 1,200 = 240.0)"),
    ((239.0, -241.0), False, "the positive side just under the floor"),
])
def test_both_sides_must_be_material(contributions, expected, label) -> None:
    """Typical month 1,200, both compared months at 1,200, floor 240, revenue
    flat (gross_to_net None)."""
    reasons: dict[str, str] = {}

    alert = _masked_shift(_level(*contributions), None, 1200.0, 1200.0, 1200.0, reasons)

    assert alert is expected, label


def test_the_floor_scales_up_with_a_peak_month() -> None:
    """Doubt-review 3D6b #3/#4, and Thach's choice of floor C. A shop whose
    typical month is 300 (a trickle off-season) and whose compared months are
    in season at 500,000. Against the typical month alone the floor was 60,
    so a 1% composition wiggle of +-4,975 fired the alert - measured at 15-25%
    false alarms on peak months with nothing planted. The floor is now 20% of
    the LARGEST of the typical month and the two compared months: 100,000."""
    alert = _masked_shift(_level(4975.2, -4975.2), None, 300.0,
                          500000.0, 500000.0, {})

    assert alert is False


def test_a_month_that_doubled_is_not_flat() -> None:
    """Doubt-review 3D6b #5. October 1,000 (10 customers at 100), November
    2,000 (40 at 50): orders +2,250, aov -1,250, gross_to_net 3.5. By the
    ratio alone that is "flat", and rule 4 would call a +100% month stable.
    The floor is 0.20 * max(1,000, 1,000, 2,000) = 400 and the change is
    1,000, so it is not."""
    alert = _masked_shift(_level(2250.0, -1250.0), 3.5, 1000.0,
                          1000.0, 2000.0, {})

    assert alert is False


@pytest.mark.parametrize("revenue_prev,revenue_cur,contributions,label", [
    (1000.0, 1200.0, (440.0, -240.0), "a month rising into a peak"),
    (1200.0, 1000.0, (240.0, -440.0), "a month falling out of one"),
])
def test_the_floor_counts_whichever_compared_month_is_larger(
    revenue_prev: float, revenue_cur: float, contributions: tuple, label: str,
) -> None:
    """The mutation check found the max was pinned only by its typical-month
    term: dropping either compared month left the suite green. Typical 1,000,
    the larger compared month 1,200, so the floor is 0.20 * 1,200 = 240. The
    change of 200 is under it and both sides clear it: the alert fires. With
    the larger month left out the floor would be 200, the change would not be
    under it, and the alert would not fire."""
    # The ratio the lens would compute: gross 680 over a change of 200.
    alert = _masked_shift(_level(*contributions), 680.0 / 200.0, 1000.0,
                          revenue_prev, revenue_cur, {})

    assert alert is True, label


def test_the_net_change_must_stay_under_the_floor() -> None:
    """The flatness bound's own boundary. Since the pair review the change is
    measured against 20% of the larger COMPARED month, not of the typical
    month. Typical 1,000; previous 2,000; current 2,499 (change 499, bound
    499.8, flat) or 2,500 (change 500, bound 500.0, not flat). Contributions
    sum to the change and clear the materiality floor (0.20 * max(1,000,
    2,000, current)) on both sides, so only flatness decides."""
    flat = _masked_shift(_level(1000.0, -501.0), 1501.0 / 499.0, 1000.0,
                         2000.0, 2499.0, {})
    moved = _masked_shift(_level(1000.0, -500.0), 1500.0 / 500.0, 1000.0,
                          2000.0, 2500.0, {})

    assert flat is True
    assert moved is False


def test_the_reported_ratio_can_still_block_and_only_blocks() -> None:
    """The three-factor `gross_to_net` is NOT implied by the pair's
    conditions - the pair review built a case where it differed from the
    pair's own ratio (2.975 against 3.05). So the check is live and pinned:
    pair conditions met, reported ratio under 3, no alert. It can only ever
    REMOVE an alert, which is the safe direction."""
    alert = _masked_shift(_level(500.0, -500.0), 2.9, 1200.0, 1200.0, 1200.0, {})

    assert alert is False


@pytest.mark.parametrize("revenue_prev,revenue_cur,label", [
    (-500.0, 300.0, "last month netted negative (the review's case R2)"),
    (300.0, -500.0, "this month netted negative"),
    (0.0, 300.0, "last month's sales and refunds cancelled exactly"),
])
def test_a_month_that_netted_zero_or_below_has_no_alert(
    revenue_prev: float, revenue_cur: float, label: str,
) -> None:
    """3D6b doubt-review cycle 2, case R2: October netted -500 (returns only),
    November +300. Revenue crossing zero flips the sign of the Shapley terms -
    customers went 10 -> 100 and contributed -2,115 - so rule 4 would narrate
    the opposite of what happened. The check cannot run: null, with a reason.
    Both months are guarded, and zero is guarded as well as below: a month
    whose sales and refunds cancel has an AOV of zero (mutation check)."""
    reasons: dict[str, str] = {}

    alert = _masked_shift(_level(-2115.0, 2915.0), 6.29, 5000.0,
                          revenue_prev, revenue_cur, reasons)

    assert alert is None
    assert "netted zero or below" in reasons["masked_shift_alert"]


def test_the_ratio_test_stays_implied() -> None:
    """`_masked_shift` proves the ratio test is implied by the floor and the
    change bound: gross > 3 * |change|. That proof needs MASKED_GROSS_TO_NET
    <= 3. Raise it and the ratio binds again, and none of the flat-month tests
    would notice - so the relationship is pinned here, where a reader of the
    failure finds the reason (3D6b doubt-review cycle 2)."""
    assert MASKED_GROSS_TO_NET <= 3.0


def test_residue_months_are_not_trading_months() -> None:
    """Three months that cancelled to floating-point residue and two trading
    months: the typical month is the median of 1,000 and 1,200, not 5.6e-17."""
    residue = 0.1 + 0.2 - 0.3

    assert typical_magnitude([residue, residue, residue, 1000.0, 1200.0]) == 1100.0


def test_the_typical_month_ignores_shut_months() -> None:
    """`typical_magnitude` over [0, 0, 0, 1,000, 1,200]: the three zeros are
    months without rows, charted as 0.0, so the typical month is the median
    of the two trading months, 1,100 - not 0, which would put the floor at
    zero and let any opposing pair fire."""
    assert typical_magnitude([0.0, 0.0, 0.0, 1000.0, 1200.0]) == 1100.0
