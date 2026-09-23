"""Step 5: the Shapley engine itself, and the lever lens built on it.

The documented examples are asserted against `shapley_product` directly rather
than through a fixture, because they are claims about the arithmetic
(docs/adr/0004, docs/DIAGNOSE_DESIGN.md 1.1) and a fixture that happened to
produce 1,240 customers would test the fixture as much as the method.
"""

from datetime import date

import pytest

from stages.diagnose.frame import history_window
from stages.diagnose.lever import compute_lever, month_revenue, returns_levels
from stages.diagnose.shapley import shapley, shapley_product
from stages.diagnose.thresholds import MASKED_GROSS_TO_NET, RECONCILE_REL_TOLERANCE
from tests.stages.diagnose.diagnose_fixtures import MAPPING, row, run_data


def reconciles(parts: list[float], total: float) -> bool:
    """The property every lens must satisfy (docs/AI_PIPELINE.md 7.6)."""
    return sum(parts) == pytest.approx(total, rel=RECONCILE_REL_TOLERANCE, abs=1e-9)


# --- the Shapley engine -------------------------------------------------------


def test_the_figma_sample_matches_the_documented_shapley_values() -> None:
    """docs/FIGMA_DESIGN_NOTES.md section 6 / DIAGNOSE_DESIGN 1.1: revenue
    104,160 -> 96,152. Frequency and AOV are derived from the order counts
    rather than the rounded 2.10/2.14 in the notes, so the factors multiply
    back to the stated revenue exactly."""
    previous = {"customers": 1240.0, "frequency": 2604 / 1240, "aov": 104160 / 2604}
    current = {"customers": 1112.0, "frequency": 2380 / 1112, "aov": 96152 / 2380}

    effects = shapley_product(previous, current)

    assert effects["customers"] == pytest.approx(-10909.58, abs=0.01)
    assert effects["frequency"] == pytest.approx(1904.44, abs=0.01)
    assert effects["aov"] == pytest.approx(997.14, abs=0.01)
    assert reconciles(list(effects.values()), 96152 - 104160)


def test_the_large_swing_example_matches_adr_0004() -> None:
    """The case that decided the ADR: sequential substitution puts the
    customers effect anywhere from -40,000 to -67,200 depending on the order a
    developer picked. Hand-derived here from the closed form
    phi_x = dx * [y_p*z_p/3 + (y_p*z_c + y_c*z_p)/6 + y_c*z_c/3]:
    -400 * [100/3 + (140+120)/6 + 168/3] = -400 * 132.6667 = -53,066.67."""
    previous = {"customers": 1000.0, "frequency": 2.0, "aov": 50.0}
    current = {"customers": 600.0, "frequency": 2.4, "aov": 70.0}

    effects = shapley_product(previous, current)

    assert effects["customers"] == pytest.approx(-53066.67, abs=0.01)
    assert effects["frequency"] == pytest.approx(18933.33, abs=0.01)
    assert effects["aov"] == pytest.approx(34933.33, abs=0.01)
    assert reconciles(list(effects.values()), 100800 - 100000)


def test_contributions_sum_to_the_total_for_an_arbitrary_value_function() -> None:
    """Exactness is a property of the construction, not of the caller's
    arithmetic: it must hold for a value function that is not a product."""
    values = {frozenset(): 3.0, frozenset({"a"}): 11.0, frozenset({"b"}): -4.0,
              frozenset({"a", "b"}): 7.5}

    effects = shapley(("a", "b"), lambda switched: values[switched])

    assert reconciles(list(effects.values()), 7.5 - 3.0)


def test_shapley_refuses_more_players_than_the_adr_allows() -> None:
    # n! enumeration is the accepted trade-off only while n stays small.
    with pytest.raises(ValueError, match="capped at 3"):
        shapley(("a", "b", "c", "d"), lambda switched: float(len(switched)))


def test_a_factor_that_did_not_move_contributes_nothing() -> None:
    effects = shapley_product({"x": 4.0, "y": 5.0}, {"x": 6.0, "y": 5.0})

    assert effects["y"] == 0.0
    assert effects["x"] == pytest.approx(10.0)  # dx=2, y constant 5


# --- lever lens, level 1 ------------------------------------------------------


def _two_month_rows() -> list[dict]:
    """October: Alice twice (50 + 50), Bob once (100)  -> 3 orders, 2 customers, 200.
    November: Alice 120, Bob 60, Cara 60               -> 3 orders, 3 customers, 240."""
    return [
        row(date(2011, 10, 5), qty=1, price=50.0, customer="Alice"),
        row(date(2011, 10, 15), qty=1, price=50.0, customer="Alice"),
        row(date(2011, 10, 20), qty=1, price=100.0, customer="Bob"),
        row(date(2011, 11, 5), qty=1, price=120.0, customer="Alice"),
        row(date(2011, 11, 15), qty=1, price=60.0, customer="Bob"),
        row(date(2011, 11, 30), qty=1, price=60.0, customer="Cara"),
    ]


def test_level_1_splits_revenue_into_customers_frequency_and_aov() -> None:
    """Hand-checked. prev: customers 2, frequency 1.5, AOV 66.667 (=200/3).
    cur: customers 3, frequency 1.0, AOV 80. Revenue 200 -> 240.
    phi_customers = 1 * [100/3 + (120 + 66.667)/6 + 80/3]      = +91.111
    phi_frequency = -0.5 * [133.333/3 + (160 + 200)/6 + 240/3] = -92.222
    phi_aov       = 13.333 * [3/3 + (2 + 4.5)/6 + 3/3]         = +41.111"""
    data = run_data(_two_month_rows())

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None
    assert lever.level1.formula == "customers*frequency*aov"
    effects = {factor.name: factor.contribution for factor in lever.level1.factors}
    assert effects["customers"] == pytest.approx(91.111, abs=0.001)
    assert effects["frequency"] == pytest.approx(-92.222, abs=0.001)
    assert effects["aov"] == pytest.approx(41.111, abs=0.001)


def test_level_1_reconciles_to_the_revenue_change() -> None:
    data = run_data(_two_month_rows())

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None
    delta = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    assert reconciles([f.contribution for f in lever.level1.factors], delta)


def test_level_1_carries_the_factor_values_it_used() -> None:
    data = run_data(_two_month_rows())

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None
    values = {f.name: (f.value_prev, f.value_cur) for f in lever.level1.factors}
    assert values["customers"] == (2.0, 3.0)
    assert values["frequency"] == (1.5, 1.0)
    assert values["aov"][0] == pytest.approx(200 / 3)


def test_without_a_mapped_customer_the_lens_falls_back_to_two_factors() -> None:
    """Hand-checked: orders 2 -> 3, AOV 100 -> 80, revenue 200 -> 240.
    phi_orders = 1 * (100 + 80)/2 = +90;  phi_aov = -20 * (2 + 3)/2 = -50."""
    mapping = {key: value for key, value in MAPPING.items() if value != "customer"}
    rows = [
        row(date(2011, 10, 5), qty=1, price=100.0),
        row(date(2011, 10, 15), qty=1, price=100.0),
        row(date(2011, 11, 5), qty=1, price=100.0),
        row(date(2011, 11, 15), qty=1, price=80.0),
        row(date(2011, 11, 30), qty=1, price=60.0),
    ]
    data = run_data(rows, mapping)

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None
    assert lever.level1.formula == "orders*aov"
    effects = {factor.name: factor.contribution for factor in lever.level1.factors}
    assert effects["orders"] == pytest.approx(90.0)
    assert effects["aov"] == pytest.approx(-50.0)
    assert reconciles(list(effects.values()), 40.0)


def test_a_month_where_every_customer_cell_is_blank_uses_the_same_fallback() -> None:
    """Thach's call, 3C: zero identified customers with orders present is the
    same practical situation as an unmapped column, so it takes the two-factor
    form rather than losing the lens."""
    rows = [
        row(date(2011, 10, 5), qty=1, price=100.0, customer="Alice"),
        row(date(2011, 10, 15), qty=1, price=100.0, customer="Bob"),
        row(date(2011, 11, 5), qty=1, price=100.0, customer=""),
        row(date(2011, 11, 15), qty=1, price=80.0, customer="   "),
        row(date(2011, 11, 30), qty=1, price=60.0, customer=""),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None
    assert lever.level1.formula == "orders*aov"
    assert "level1_form" in lever.reasons
    assert reconciles([f.contribution for f in lever.level1.factors], 40.0)


def test_a_period_with_zero_orders_makes_the_lens_inconclusive() -> None:
    """Thach's call, 3C: AOV is 0/0 for a month with no sales, and substituting
    a zero would report 'AOV contributed +50' as a cause."""
    rows = [
        row(date(2011, 9, 1), qty=1, price=100.0),
        row(date(2011, 11, 5), qty=1, price=100.0),
        row(date(2011, 11, 30), qty=1, price=60.0),
    ]
    data = run_data(rows)  # October is empty, and October is `previous`

    lever = compute_lever(data, history_window(data))

    assert data.metrics.period.previous == "2011-10"
    assert lever.level1 is None
    assert lever.level2 is None
    assert "zero orders in the previous period" in lever.reasons["level1"]


def test_an_inconclusive_lens_reports_null_not_false_for_the_alert() -> None:
    """Thach's call, 3C: `false` states that the check ran and found nothing.
    A tree that could not be built must not be read downstream as 'no masked
    shift'."""
    rows = [
        row(date(2011, 9, 1), qty=1, price=100.0),
        row(date(2011, 11, 5), qty=1, price=100.0),
        row(date(2011, 11, 30), qty=1, price=60.0),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.masked_shift_alert is None
    assert lever.gross_to_net is None
    assert lever.reasons["gross_to_net"]


# --- lever lens, level 2 ------------------------------------------------------


def test_level_2_splits_aov_and_converts_into_revenue_units() -> None:
    """Hand-checked. Two customers, one order each, both months, so the whole
    revenue move (200 -> 260) lands on AOV: phi_aov = +60.

    Inside AOV (100 -> 130): units per order 2 -> 2.5, price per unit 50 -> 52.
    phi_upo = 0.5 * (50 + 52)/2 = 25.5;  phi_ppu = 2 * (2 + 2.5)/2 = 4.5;
    together 30, which is the AOV change. Converted into revenue units by
    phi_aov * phi_k / delta_aov: 60 * 25.5/30 = 51 and 60 * 4.5/30 = 9.
    """
    rows = [
        row(date(2011, 10, 5), qty=2, price=50.0, customer="Alice"),
        row(date(2011, 10, 15), qty=2, price=50.0, customer="Bob"),
        row(date(2011, 11, 5), qty=2, price=70.0, customer="Alice"),
        row(date(2011, 11, 30), qty=3, price=40.0, customer="Bob"),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None and lever.level2 is not None
    assert lever.level2.formula == "units_per_order*price_per_unit"
    effects = {factor.name: factor.contribution for factor in lever.level2.factors}
    assert effects["units_per_order"] == pytest.approx(51.0)
    assert effects["price_per_unit"] == pytest.approx(9.0)

    phi_aov = next(f.contribution for f in lever.level1.factors if f.name == "aov")
    assert phi_aov == pytest.approx(60.0)
    assert reconciles(list(effects.values()), phi_aov)


def test_level_2_is_inconclusive_when_returns_swamp_a_period() -> None:
    # November nets to -1 units, so units per order is negative and the
    # price/basket split says nothing.
    rows = [
        row(date(2011, 10, 5), qty=4, price=50.0, customer="Alice"),
        row(date(2011, 11, 5), qty=2, price=50.0, customer="Alice"),
        row(date(2011, 11, 30), qty=-3, price=50.0, customer="Alice"),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.level2 is None
    assert "net units are not positive" in lever.reasons["level2"]


def test_level_2_is_inconclusive_when_net_units_are_exactly_zero() -> None:
    """The zero-denominator boundary CLAUDE.md section 5 requires. Written
    `< 0` instead of `<= 0` this is a ZeroDivisionError, and nothing covered
    it (3C doubt-review R4): November buys 5 and returns 5."""
    rows = [
        row(date(2011, 10, 5), qty=4, price=50.0, customer="Alice"),
        row(date(2011, 11, 5), qty=5, price=50.0, customer="Alice"),
        row(date(2011, 11, 30), qty=-5, price=50.0, customer="Alice"),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.level2 is None
    assert "net units are not positive" in lever.reasons["level2"]


def test_a_negligible_aov_move_is_treated_as_no_move() -> None:
    """3C doubt-review R1a: the guard was `delta_aov == 0`, so float residue
    walked through it and the lens reported basket and price effects around
    10^15 times larger than the AOV change they decompose. Three rows priced
    0.1/0.2/0.3 are enough to produce that residue."""
    rows = [
        row(date(2011, 10, 5), qty=1, price=0.1, customer="Alice"),
        row(date(2011, 10, 6), qty=1, price=0.2, customer="Bob"),
        row(date(2011, 10, 7), qty=1, price=0.3, customer="Cara"),
        row(date(2011, 11, 5), qty=1, price=0.3, customer="Alice"),
        row(date(2011, 11, 6), qty=1, price=0.2, customer="Bob"),
        row(date(2011, 11, 30), qty=1, price=0.1, customer="Cara"),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.level2 is None
    assert "AOV did not move" in lever.reasons["level2"]
    # And the same residue must not become a vast gross-to-net ratio (R1b).
    assert lever.gross_to_net is None
    assert "revenue did not move" in lever.reasons["gross_to_net"]


def test_level_2_is_inconclusive_when_aov_did_not_move() -> None:
    # The conversion into revenue units divides by the AOV change.
    rows = [
        row(date(2011, 10, 5), qty=2, price=50.0, customer="Alice"),
        row(date(2011, 11, 5), qty=2, price=50.0, customer="Alice"),
        row(date(2011, 11, 30), qty=2, price=50.0, customer="Bob"),
    ]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.level2 is None
    assert "AOV did not move" in lever.reasons["level2"]


# --- masked shift -------------------------------------------------------------


def _masked_rows() -> list[dict]:
    """October: 4 customers, one order each at 100  -> 400.
    November: 1 customer, four orders at 105        -> 420.
    Revenue barely moves (+20) while the composition turns over completely."""
    return [
        *[row(date(2011, 10, 5), qty=1, price=100.0, customer=f"C{i}") for i in range(4)],
        *[row(date(2011, 11, day), qty=1, price=105.0, customer="C0")
          for day in (5, 10, 20, 30)],
    ]


def test_gross_to_net_is_computed_by_the_lens_and_not_by_the_test() -> None:
    """Hand-checked against the real `compute_lever`. The previous version of
    this test re-implemented the formula in its own body and asserted its own
    arithmetic, so `_gross_to_net` itself was pinned nowhere and dropping the
    per-factor abs() left the suite green (3C doubt-review R4).

    customers 4 -> 1, frequency 1 -> 4, AOV 100 -> 105, revenue 400 -> 420.
    phi_customers = -3 * [100/3 + (105 + 400)/6 + 420/3] = -772.5
    phi_frequency = +3 * [400/3 + (420 + 100)/6 + 105/3] = +765.0
    phi_aov       = +5 * [4/3 + (16 + 1)/6 + 4/3]        =  +27.5
    sum |phi| = 1565.0, delta_revenue = 20  ->  78.25
    """
    data = run_data(_masked_rows())

    lever = compute_lever(data, history_window(data))

    assert lever.level1 is not None
    effects = {f.name: f.contribution for f in lever.level1.factors}
    assert effects["customers"] == pytest.approx(-772.5)
    assert effects["frequency"] == pytest.approx(765.0)
    assert effects["aov"] == pytest.approx(27.5)
    assert reconciles(list(effects.values()), 20.0)
    assert lever.gross_to_net == pytest.approx(78.25)


def _with_history(rows: list[dict], level: float = 400.0) -> list[dict]:
    """Three complete months at `level` before October, so the history
    window has a typical month to measure "material" against (ADR-0007)."""
    history = [row(date(2011, month, 1 + index), qty=1, price=level / 4,
                   customer=f"H{index}")
               for month in (7, 8, 9) for index in range(4)]
    return [*history, *rows]


def test_the_alert_reads_orders_against_aov_not_an_identity() -> None:
    """Three months, typical month 400 (four orders at 100 each).

    identity: `_masked_rows` - four customers once each becomes ONE customer
        four times, AOV 100 -> 105. The three-factor split shows customers
        -772.5 against frequency +765.0 (ratio 78.25), but customers x
        frequency = orders by definition and orders did not move: 4 -> 4.
        On the orders x AOV pair: orders 0, AOV +5 * (4 + 4) / 2 = +20. No
        alert (Thach, 3D6b). Before, this was this file's flagship "loud" case.
    shift: four orders at 100 (400) become two at 210 (420).
        phi_orders = -2 * (100 + 210) / 2 = -310
        phi_aov    = +110 * (4 + 2) / 2   = +330
        Floor 0.20 * max(400, 400, 420) = 84, change 20: flat, both sides
        clear it. Alert.
    plain: two customers become four, nothing else moves - ratio 1.0, change
        200 over its floor of 80. No alert.

    The ratio test itself is not pinned here: over the pair it is implied
    (test_no_step4_verdicts.py pins MASKED_GROSS_TO_NET <= 3)."""
    identity = run_data(_with_history(_masked_rows()))
    shift = run_data(_with_history([
        *[row(date(2011, 10, 5), qty=1, price=100.0, customer=f"C{i}") for i in range(4)],
        *[row(date(2011, 11, 20 + 10 * i), qty=1, price=210.0, customer=f"C{i}")
          for i in range(2)],
    ]))
    plain = run_data(_with_history([
        *[row(date(2011, 10, 5), qty=1, price=100.0, customer=f"C{i}") for i in range(2)],
        *[row(date(2011, 11, 30), qty=1, price=100.0, customer=f"C{i}") for i in range(4)],
    ]))

    same = compute_lever(identity, history_window(identity))
    loud = compute_lever(shift, history_window(shift))
    quiet = compute_lever(plain, history_window(plain))

    assert same.gross_to_net == pytest.approx(78.25)
    assert {f.name: f.contribution for f in same.masked_shift_pair.factors} == \
        pytest.approx({"orders": 0.0, "aov": 20.0})
    assert same.masked_shift_alert is False
    assert {f.name: f.contribution for f in loud.masked_shift_pair.factors} == \
        pytest.approx({"orders": -310.0, "aov": 330.0})
    assert loud.masked_shift_alert is True
    assert quiet.gross_to_net == pytest.approx(1.0)
    assert quiet.masked_shift_alert is False


# --- returns lens -------------------------------------------------------------


def test_the_returns_lens_separates_gross_sales_from_refunds() -> None:
    """Hand-checked: gross 200 -> 180, returns 50 -> 20.
    delta_net = delta_gross - delta_returns = -20 - (-30) = +10."""
    rows = [
        row(date(2011, 10, 5), qty=4, price=50.0),
        row(date(2011, 10, 20), qty=-1, price=50.0),
        row(date(2011, 11, 5), qty=4, price=45.0),
        row(date(2011, 11, 30), qty=-1, price=20.0),
    ]
    data = run_data(rows)

    levels = returns_levels(data)

    assert levels == {"gross_prev": 200.0, "returns_prev": 50.0,
                      "gross_cur": 180.0, "returns_cur": 20.0}
    # A zero-quantity row is neither a sale nor a refund. Note that mutating
    # the returns filter from `< 0` to `<= 0` is an EQUIVALENT mutant, not a
    # gap in this test: such a row contributes `0 * price == 0.0` to the sum
    # either way. That equivalence only holds because non-finite prices are
    # now excluded at the boundary - before that fix, `0 * inf` was NaN.
    assert levels["returns_cur"] == 20.0
    delta_net = month_revenue(data, "2011-11") - month_revenue(data, "2011-10")
    delta_gross = levels["gross_cur"] - levels["gross_prev"]
    delta_returns = levels["returns_cur"] - levels["returns_prev"]
    assert delta_gross - delta_returns == pytest.approx(delta_net)
    assert delta_net == pytest.approx(10.0)
