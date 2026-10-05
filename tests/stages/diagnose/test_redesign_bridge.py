"""Report redesign step 1 (Thach, 2026-10-05): diagnosis.json 18.4's
`tree.lever.bridge` - the waterfall the report draws, its bars the lever's
own terms, cents by largest remainder so the shown bars sum exactly to the
shown change (Q2), the items/price split withheld where stage 3 refuses B2
(Q1). docs/REPORT_REDESIGN.md 1.2 and 2; method
C:/Users/Happy/redesign-step1-method.txt M2.

The Kaggle case is built from that run's month totals (orders, customers
who placed an order, units, sales) - aggregates, not its rows: uploaded
data is never committed (CLAUDE.md section 6)."""

from datetime import date

import pytest
from pydantic import ValidationError

from contracts.diagnosis import Lever
from contracts.lever_bridge import LeverBridge, floor_cents
from stages.diagnose import lever as lever_module
from stages.diagnose.frame import history_window
from stages.diagnose.lever import PeriodTotals, allocate_cents, compute_lever, lever_from_totals
from tests.stages.diagnose.diagnose_fixtures import NOW, full_months, row, run_data

KAGGLE_NOV = PeriodTotals(revenue=41_367.5, orders=308, customers=25, units=1_675.0)
KAGGLE_DEC = PeriodTotals(revenue=46_292.5, orders=343, customers=25, units=1_991.0)


def _kaggle(refund_lines: bool = False) -> Lever:
    return lever_from_totals(KAGGLE_NOV, KAGGLE_DEC, has_customers=True, typical=40_281.75,
                             refunds=refund_lines)


def test_kaggles_four_bars_are_the_lever_terms_shown_to_the_cent() -> None:
    bridge = _kaggle().bridge

    assert [bar.factor for bar in bridge.bars] == ["customers", "frequency", "units_per_order", "price_per_unit"]
    assert [bar.shown for bar in bridge.bars] == [0.0, 4_712.29, 2_858.84, -2_646.13]
    assert bridge.aov_split is True and bridge.aov_split_withheld is None


def test_kaggles_bars_sum_exactly_to_the_change() -> None:
    bridge = _kaggle().bridge

    assert (bridge.revenue_previous, bridge.revenue_current, bridge.change) == (41_367.5, 46_292.5, 4_925.0)
    assert bridge.shown_change == 4_925.0
    assert round(sum(bar.shown for bar in bridge.bars) * 100) == 492_500


def test_the_bars_carry_the_levers_exact_terms_and_values() -> None:
    lever = _kaggle()
    level1 = {f.name: f for f in lever.level1.factors}
    level2 = {f.name: f for f in lever.level2.factors}

    for bar in lever.bridge.bars:
        factor = level1.get(bar.factor) or level2[bar.factor]
        assert (bar.value_prev, bar.value_cur, bar.contribution) == (
            factor.value_prev, factor.value_cur, factor.contribution)
    assert lever.level2.factors[1].contribution == pytest.approx(-2_646.1315155101943, abs=1e-9)


def test_where_b2_is_refused_the_order_value_is_one_bar() -> None:
    bridge = _kaggle(refund_lines=True).bridge

    assert [bar.factor for bar in bridge.bars] == ["customers", "frequency", "aov"]
    assert (bridge.aov_split, bridge.aov_split_withheld) == (False, "refund_lines")
    assert bridge.bars[2].shown == 212.71
    assert round(sum(bar.shown for bar in bridge.bars) * 100) == 492_500


# --- largest remainder (Q2) -------------------------------------------------------------------------

# The unanswered Online Retail II run's four exact terms (level 1's customers and frequency, level 2's
# pair): rounded one by one to the cent they add to 139,466.57, against a change of 139,466.56.
UNANSWERED = [125_915.38884327032, 51_213.496219437366, -77_061.74278323835, 39_399.41772053071]


def test_rounding_each_bar_alone_misses_the_change_by_a_cent() -> None:
    assert round(sum(round(term, 2) for term in UNANSWERED) * 100) == 13_946_657


def test_largest_remainder_shows_bars_that_sum_to_the_change() -> None:
    shown = allocate_cents(UNANSWERED, 13_946_656)

    assert shown == [12_591_539, 5_121_349, -7_706_174, 3_939_942]
    assert sum(shown) == 13_946_656


def test_each_bar_is_its_term_floored_or_one_cent_above() -> None:
    for term, cents in zip(UNANSWERED, allocate_cents(UNANSWERED, 13_946_656), strict=True):
        assert floor_cents(term) <= cents <= floor_cents(term) + 1


def test_a_tie_goes_to_the_earlier_bar() -> None:
    assert allocate_cents([0.005, 0.005], 1) == [1, 0]


def test_a_target_a_cent_under_the_terms_takes_one_back_from_the_smallest_remainder() -> None:
    # Whole-cent terms summing to 30,975 against a printed difference of 30,974 (a month ending on half a
    # cent prints to even): one cent comes back, from the smallest remainder, a tie to the later term.
    # A term of exactly 0 - a factor that did not move - never gives a cent (doubt-review cycle 2 #3).
    assert allocate_cents([0.0, 0.0, 309.75, 0.0], 30_974) == [0, 0, 30_974, 0]
    assert allocate_cents([1.004, 2.0], 299) == [100, 199]


def test_a_factor_that_did_not_move_never_takes_a_cent() -> None:
    # Whole-cent terms summing a cent under the target: the cent goes to a term that moved.
    assert allocate_cents([0.0, 5.0, 3.0], 801) == [0, 501, 300]


def test_a_positive_term_never_gives_back_the_cent_that_would_show_it_below_zero() -> None:
    # 0.001 has the smallest remainder but rounds down to 0.00: taking its cent would show -0.01, a fall
    # that did not happen; the next smallest gives it instead.
    assert allocate_cents([0.001, 2.005], 199) == [0, 199]


def test_a_tie_in_giving_a_cent_back_goes_to_the_later_bar() -> None:
    assert allocate_cents([1.0, 2.0], 299) == [100, 199]


def test_a_residue_term_shows_no_movement() -> None:
    # -1e-13 beside 309.75 is float residue: it shows 0.00, never -0.01 (cycle 3 #5).
    assert allocate_cents([309.75 + 1e-13, -1e-13], 30_974) == [30_974, 0]


def test_no_term_that_may_move_draws_nothing() -> None:
    assert allocate_cents([0.0, 0.0], 1) is None


def test_a_target_a_cent_a_term_cannot_reach_draws_nothing() -> None:
    # Float residue past a cent (amounts around 10^12 and up, doubt-review cycle 1 #1): no bar moves
    # further, and no crash.
    assert allocate_cents([1.0, 2.0], 500) is None
    assert allocate_cents([1.0, 2.0], 297) is None


def test_a_month_ending_on_half_a_cent_still_draws_a_bridge() -> None:
    # The review's reproduction (cycle 1 #1): 310.375 prints 310.38 and 620.125 prints 620.12, so the
    # printed difference is a cent under the exact one - the first rule crashed the whole diagnosis.
    from stages.diagnose.assemble import diagnose

    found = diagnose(run_data(full_months({"2024-10": 500.0, "2024-11": 310.375, "2024-12": 620.125})), NOW)
    bridge = found.tree.lever.bridge

    assert bridge.shown_change == 309.74
    assert (bridge.shown_previous, bridge.shown_current) == (310.38, 620.12)
    assert round(sum(bar.shown for bar in bridge.bars) * 100) == 30_974
    # No factor that did not move shows a cent (doubt-review cycle 2 #3).
    assert all(bar.shown == 0.0 for bar in bridge.bars if bar.contribution == 0.0)


def test_amounts_past_what_a_float_prints_back_withhold_the_bridge() -> None:
    # The review's reproduction (cycle 2 #1): a level-2 term far larger than the months - a swing in
    # units - past ~15 significant digits of cents; it crashed the diagnosis before.
    lever = lever_from_totals(PeriodTotals(537_081_396_151.06, 41, 3, 139.0),
                              PeriodTotals(723_104_697_966.88, 33, 18, 1.0),
                              has_customers=True, typical=6e11, refunds=False)

    assert (lever.bridge, lever.bridge_withheld) == (None, "not_to_the_cent")


@pytest.mark.parametrize("revenue", [0.005, 0.004999999999999999, 0.0050000000000000001, 0.015])
def test_a_month_near_half_a_cent_never_crashes_the_lever(revenue: float) -> None:
    # Stage 3 decides on the revenue as printed; the contract, which has only level 1's factors beside a
    # withheld bridge, must not read the same month the other way (cycle 3 #1: 39 crashes in 30,000).
    previous = PeriodTotals(revenue=revenue, orders=15, customers=11, units=15.0)
    current = PeriodTotals(revenue=100.0, orders=12, customers=10, units=20.0)

    lever = lever_from_totals(previous, current, has_customers=True, typical=50.0, refunds=False)

    assert (lever.bridge is None) == (lever.bridge_withheld == "month_not_positive")


def test_a_month_netting_half_a_cent_diagnoses_end_to_end() -> None:
    # The review's reproduction: 23 sale lines at 0.001 from 21 customers and one return of 0.018.
    from stages.diagnose.assemble import diagnose

    rows = [row(date(2024, 10, day), qty=1.0, price=10.0, customer=f"C{day % 5}") for day in range(1, 32)]
    rows += [row(date(2024, 11, 1 + index), qty=1.0, price=0.001, customer=f"C{index % 21}") for index in range(23)]
    rows += [row(date(2024, 11, 30), qty=-1.0, price=0.018, customer="C0")]

    found = diagnose(run_data(rows), NOW)

    assert found.tree is None or (found.tree.lever.bridge is None) != (found.tree.lever.bridge_withheld is None)


def test_a_month_that_nets_to_float_residue_is_not_positive_whatever_its_sign() -> None:
    # Sales and refunds that cancel sum to +5.55e-17 or -2.78e-17 by row order (cycle 2 #5).
    for residue in (5.55e-17, -2.78e-17):
        previous = PeriodTotals(revenue=residue, orders=10, customers=5, units=20.0)
        current = PeriodTotals(revenue=1_000.0, orders=12, customers=6, units=30.0)
        lever = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=True)
        assert (lever.bridge, lever.bridge_withheld) == (None, "month_not_positive")


def test_terms_that_cannot_be_shown_to_the_cent_withhold_the_bridge(monkeypatch) -> None:
    monkeypatch.setattr(lever_module, "allocate_cents", lambda terms, total: None)
    lever = _kaggle()

    assert (lever.bridge, lever.bridge_withheld) == (None, "not_to_the_cent")


def test_the_ends_are_the_months_as_printed_not_their_cents_rounded() -> None:
    # 100.025 prints 100.03, while round(100.025 * 100) is 10,002: the chart's start is what stage 5 prints.
    previous = PeriodTotals(revenue=100.025, orders=2, customers=1, units=2.0)
    current = PeriodTotals(revenue=150.0, orders=3, customers=1, units=4.0)
    bridge = lever_from_totals(previous, current, has_customers=True, typical=100.0, refunds=False).bridge

    assert (bridge.shown_previous, bridge.shown_change) == (100.03, 49.97)


def test_the_shown_change_is_the_printed_months_difference_not_the_rounded_change() -> None:
    # 10.006 prints 10.01 and 20.004 prints 20.00: the chart's ends differ by 9.99, while the exact
    # change, 9.998, rounds to 10.00.
    previous = PeriodTotals(revenue=10.006, orders=1, customers=1, units=1.0)
    current = PeriodTotals(revenue=20.004, orders=2, customers=1, units=2.0)
    bridge = lever_from_totals(previous, current, has_customers=True, typical=10.0, refunds=False).bridge

    assert bridge.shown_change == 9.99
    assert round(sum(bar.shown for bar in bridge.bars) * 100) == 999


# --- when there is no waterfall, or no split -------------------------------------------------------


def test_level_2_null_because_aov_did_not_move_withholds_the_split() -> None:
    previous = PeriodTotals(revenue=1_000.0, orders=10, customers=5, units=20.0)
    current = PeriodTotals(revenue=1_200.0, orders=12, customers=6, units=30.0)
    bridge = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=False).bridge

    assert (bridge.aov_split, bridge.aov_split_withheld) == (False, "aov_unchanged")
    assert [bar.factor for bar in bridge.bars] == ["customers", "frequency", "aov"]


def test_level_2_null_for_net_units_withholds_the_split_with_that_code() -> None:
    previous = PeriodTotals(revenue=1_000.0, orders=10, customers=5, units=-2.0)
    current = PeriodTotals(revenue=1_200.0, orders=12, customers=6, units=30.0)
    bridge = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=False).bridge

    assert bridge.aov_split_withheld == "net_units_not_positive"


def test_refund_lines_come_first_as_b2_reads_them() -> None:
    previous = PeriodTotals(revenue=1_000.0, orders=10, customers=5, units=-2.0)
    current = PeriodTotals(revenue=1_200.0, orders=12, customers=6, units=30.0)
    bridge = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=True).bridge

    assert bridge.aov_split_withheld == "refund_lines"


def test_a_month_with_no_orders_has_no_waterfall() -> None:
    previous = PeriodTotals(revenue=0.0, orders=0, customers=0, units=0.0)
    current = PeriodTotals(revenue=1_200.0, orders=12, customers=6, units=30.0)
    lever = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=False)

    assert (lever.bridge, lever.bridge_withheld) == (None, "zero_orders")


@pytest.mark.parametrize("revenue_prev,revenue_cur", [(0.0, 1_200.0), (-50.0, 1_200.0), (1_200.0, 0.0),
                                                     (1_200.0, -50.0)])
def test_a_month_netting_zero_or_below_has_no_waterfall(revenue_prev: float, revenue_cur: float) -> None:
    # The multiplicative split's terms change sign there: more customers would read as pulling sales
    # down (the masked-shift alert refuses the same months, lever._masked_shift).
    previous = PeriodTotals(revenue=revenue_prev, orders=10, customers=5, units=20.0)
    current = PeriodTotals(revenue=revenue_cur, orders=12, customers=6, units=30.0)
    lever = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=True)

    assert (lever.bridge, lever.bridge_withheld) == (None, "month_not_positive")


def test_without_a_customer_column_the_bars_are_orders_and_order_value() -> None:
    bridge = lever_from_totals(KAGGLE_NOV, KAGGLE_DEC, has_customers=False, typical=40_281.75,
                               refunds=False).bridge

    assert [bar.factor for bar in bridge.bars] == ["orders", "units_per_order", "price_per_unit"]
    assert round(sum(bar.shown for bar in bridge.bars) * 100) == 492_500


# --- on a real run: B2's own refusal decides -------------------------------------------------------


def _with_a_refund() -> list[dict]:
    rows = [row(date(2024, 10, day), qty=1.0, price=10.0, customer=f"C{day % 3}") for day in range(1, 32)]
    rows += [row(date(2024, 11, day), qty=2.0, price=10.0, customer=f"C{day % 4}") for day in range(1, 31)]
    rows += [row(date(2024, 11, 5), qty=-1.0, price=10.0, customer="C1")]
    rows += [row(date(2024, 12, day), qty=1.0, price=10.0) for day in range(1, 32)]
    return rows


def test_a_run_with_a_return_line_withholds_the_split_as_b2_refuses_it() -> None:
    from stages.diagnose.assemble import diagnose
    from tests.stages.diagnose.diagnose_fixtures import NOW

    data = run_data(_with_a_refund())
    found = diagnose(data, NOW)
    b2 = next(h for h in found.hypotheses if h.id == "B2")

    assert found.tree.lever.level2 is not None  # stage 3 writes the pair...
    assert b2.verdict == "inconclusive" and "refund_lines_prev" in b2.evidence  # ...and refuses B2
    assert found.tree.lever.bridge.aov_split_withheld == "refund_lines"


def test_compute_lever_on_a_clean_run_draws_the_split() -> None:
    rows = [row(date(2024, 10, day), qty=1.0, price=10.0, customer=f"C{day % 3}") for day in range(1, 32)]
    rows += [row(date(2024, 11, day), qty=2.0, price=12.0, customer=f"C{day % 4}") for day in range(1, 31)]
    data = run_data(rows)

    lever = compute_lever(data, history_window(data))

    assert lever.bridge.aov_split is True
    # October: 31 lines of 10.00; November: 30 lines of 2 x 12.00.
    assert (lever.bridge.shown_previous, lever.bridge.shown_current, lever.bridge.shown_change) == (
        310.0, 720.0, 410.0)
    total = round(sum(bar.shown for bar in lever.bridge.bars) * 100)
    assert total == round(lever.bridge.shown_change * 100)


# --- the contract ------------------------------------------------------------------------------------


def _bridge_dump() -> dict:
    return _kaggle().bridge.model_dump()


def test_shown_bars_that_do_not_sum_to_the_shown_change_are_refused() -> None:
    data = _bridge_dump()
    data["bars"][0]["shown"] = 0.01  # each bar still within a cent of its term; the total one cent over

    with pytest.raises(ValidationError, match="sum"):
        LeverBridge.model_validate(data)


def test_a_shown_bar_more_than_a_cent_off_its_term_is_refused() -> None:
    data = _bridge_dump()
    data["bars"][1]["shown"] = 4_712.30  # two cents above its floor...
    data["bars"][3]["shown"] = -2_646.14  # ...and one cent taken back here, so the total still holds

    with pytest.raises(ValidationError, match="cent"):
        LeverBridge.model_validate(data)


def test_a_shown_change_that_is_not_the_printed_months_difference_is_refused() -> None:
    # The bars still sum to shown_change; only the months moved.
    data = _bridge_dump()
    data["revenue_previous"] = data["shown_previous"] = 41_367.49
    data["change"] = 46_292.5 - 41_367.49

    with pytest.raises(ValidationError, match="printed months' difference"):
        LeverBridge.model_validate(data)


def test_a_change_other_than_the_months_difference_is_refused() -> None:
    data = _bridge_dump()
    data["change"] = 4_925.5

    with pytest.raises(ValidationError, match="bridge.change"):
        LeverBridge.model_validate(data)


def test_a_bar_shown_off_the_cent_is_refused() -> None:
    from contracts.lever_bridge import BridgeBar

    bar = _bridge_dump()["bars"][1] | {"shown": 4_712.291}

    with pytest.raises(ValidationError, match="to the cent"):
        BridgeBar.model_validate(bar)


def test_a_shown_change_off_the_cent_is_refused() -> None:
    data = _bridge_dump()
    data["shown_change"] = 4_925.004

    with pytest.raises(ValidationError, match="whole cents"):
        LeverBridge.model_validate(data)


def test_a_bridge_beside_a_month_netting_zero_is_refused() -> None:
    data = _bridge_dump()
    data["revenue_previous"], data["shown_previous"], data["change"] = -50.0, -50.0, 46_292.5 + 50.0

    with pytest.raises(ValidationError, match="month_not_positive"):
        LeverBridge.model_validate(data)


@pytest.mark.parametrize("split,withheld", [(True, "refund_lines"), (False, None)])
def test_the_split_and_its_withholding_agree(split: bool, withheld: str | None) -> None:
    data = _bridge_dump()
    data.update(aov_split=split, aov_split_withheld=withheld)

    with pytest.raises(ValidationError):
        LeverBridge.model_validate(data)


def test_a_lever_with_both_a_bridge_and_a_withholding_is_refused() -> None:
    data = _kaggle().model_dump()
    data["bridge_withheld"] = "month_not_positive"

    with pytest.raises(ValidationError, match="not both"):
        Lever.model_validate(data)


def test_ends_other_than_the_printed_months_are_refused() -> None:
    data = _bridge_dump()
    data["shown_current"] = 46_292.51

    with pytest.raises(ValidationError, match="as stage 5 prints them"):
        LeverBridge.model_validate(data)


def test_cents_moved_against_the_largest_remainder_rule_are_refused() -> None:
    # Each bar still within a cent of its term and the total still holds (cycle 2 #4).
    data = _bridge_dump()
    data["bars"][1]["shown"], data["bars"][2]["shown"] = 4_712.28, 2_858.85

    with pytest.raises(ValidationError, match="largest-remainder"):
        LeverBridge.model_validate(data)


def test_a_level_2_cause_other_than_its_reason_is_refused() -> None:
    previous = PeriodTotals(revenue=1_000.0, orders=10, customers=5, units=-2.0)
    current = PeriodTotals(revenue=1_200.0, orders=12, customers=6, units=30.0)
    data = lever_from_totals(previous, current, has_customers=True, typical=1_000.0, refunds=False).model_dump()
    data["bridge"]["aov_split_withheld"] = "aov_unchanged"  # the reason says net units

    with pytest.raises(ValidationError, match="for that reason"):
        Lever.model_validate(data)


def test_a_level_1_of_another_formula_is_refused_not_a_crash() -> None:
    data = _kaggle().model_dump()
    data["level1"], data["masked_shift_pair"] = data["level2"], None
    data["bridge"], data["bridge_withheld"] = None, "not_to_the_cent"

    with pytest.raises(ValidationError, match="level 1 is"):
        Lever.model_validate(data)


def test_months_that_are_not_level_1s_revenue_are_refused() -> None:
    data = _kaggle().model_dump()
    for end in ("revenue_previous", "revenue_current", "shown_previous", "shown_current"):
        data["bridge"][end] += 1_000.0

    with pytest.raises(ValidationError, match="multiplies back"):
        Lever.model_validate(data)


def test_a_zero_orders_withholding_beside_level_1_is_refused() -> None:
    data = _kaggle().model_dump()
    data["bridge"], data["bridge_withheld"] = None, "zero_orders"

    with pytest.raises(ValidationError, match="zero orders"):
        Lever.model_validate(data)


def test_a_month_not_positive_withholding_on_two_positive_months_is_refused() -> None:
    data = _kaggle().model_dump()
    data["bridge"], data["bridge_withheld"] = None, "month_not_positive"

    with pytest.raises(ValidationError, match="month_not_positive"):
        Lever.model_validate(data)


def test_a_bridge_beside_a_null_level_1_is_refused() -> None:
    previous = PeriodTotals(revenue=0.0, orders=0, customers=0, units=0.0)
    data = lever_from_totals(previous, KAGGLE_DEC, has_customers=True, typical=1.0, refunds=False).model_dump()
    data["bridge"], data["bridge_withheld"] = _kaggle().bridge.model_dump(), None

    with pytest.raises(ValidationError, match="zero orders"):
        Lever.model_validate(data)


def test_a_level_2_cause_beside_a_level_2_is_refused() -> None:
    data = _kaggle(refund_lines=True).model_dump()
    data["bridge"]["aov_split_withheld"] = "aov_unchanged"

    with pytest.raises(ValidationError, match="only where level 2 is null"):
        Lever.model_validate(data)


def test_bars_that_are_not_the_levers_terms_are_refused() -> None:
    data = _kaggle().model_dump()
    data["bridge"]["bars"][1]["value_prev"] = 12.0  # the bridge is whole; level 1 says 12.32

    with pytest.raises(ValidationError, match="lever's terms"):
        Lever.model_validate(data)
