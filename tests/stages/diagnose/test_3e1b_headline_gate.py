"""Session 3E1b part C with 3E2-F1 (Thach, 2026-10-02): the headline singles a
cause out (rules 5 and 6) only when the change is at least twice this shop's
median month-over-month movement of complete months; otherwise it states the
descriptive fact and names none (rule 7). Rules 1-4, the verdicts and the
hypothesis table are unchanged. Too short a history: said so.

Every percentage below is worked by hand."""

import pytest

from contracts.diagnosis import Headline, HeadlineMovement, Hypothesis, Trust, TrustCheck
from stages.diagnose.catalog import BY_ID, CATALOG
from stages.diagnose.headline import choose_headline
from stages.diagnose.movement import MIN_MOVEMENTS, measure_movement, singled_out
from stages.diagnose.step7_inputs import Changes
from stages.diagnose.thresholds import HEADLINE_MOVEMENT_FACTOR, XMR_MIN_BASELINE_POINTS

HISTORY = ["2023-01", "2023-02", "2023-03", "2023-04", "2023-05", "2023-06", "2023-07", "2023-08", "2023-09"]
REVENUE = dict(zip(HISTORY, [100.0, 110.0, 99.0, 108.0, 102.0, 105.0, 100.0, 104.0, 98.0]))


def test_the_factor_is_thachs_and_the_minimum_is_the_engines_baseline() -> None:
    # Thach: twice the median ("by the definition of a median, about half of
    # ordinary months exceed it" - a factor of 1 is not viable). The minimum:
    # the 8 months the engine already asks of a baseline, i.e. 7 movements.
    assert HEADLINE_MOVEMENT_FACTOR == 2.0
    assert MIN_MOVEMENTS == XMR_MIN_BASELINE_POINTS - 1 == 7


def test_the_typical_movement_is_the_median_of_the_month_to_month_changes() -> None:
    """Movements: 10/100 = 10%, 11/110 = 10%, 9/99 = 9.0909%, 6/108 = 5.5556%,
    3/102 = 2.9412%, 5/105 = 4.7619%, 4/100 = 4%, 6/104 = 5.7692%. Eight;
    the median is (5.5556 + 5.7692) / 2 = 5.6624%. 98 -> 108 is +10.2041%,
    under 2 x 5.6624 = 11.3248: not singled out."""
    movement = measure_movement(HISTORY, REVENUE, revenue_prev=98.0, revenue_cur=108.0)
    assert movement.movements == 8
    assert movement.typical_pct == pytest.approx((6 / 108 + 6 / 104) / 2 * 100)
    assert movement.change_pct == pytest.approx(10 / 98 * 100)
    assert (movement.factor, movement.singled_out, movement.reason) == (2.0, False, None)
    # 98 -> 120 is +22.449%: singled out.
    assert measure_movement(HISTORY, REVENUE, revenue_prev=98.0, revenue_cur=120.0).singled_out is True


@pytest.mark.parametrize("change,typical,expected", [
    (10.0, 5.0, True),    # exactly twice
    (9.99, 5.0, False),
    (-10.0, 5.0, True),   # a fall as much as a rise
    (-9.99, 5.0, False),
    (0.5, 0.0, True),     # a shop whose months never moved: any movement is beyond it
])
def test_singled_out_at_twice_the_typical_movement(change: float, typical: float, expected: bool) -> None:
    assert singled_out(change, typical) is expected


def test_a_month_with_no_revenue_gives_no_base_for_the_movement_after_it() -> None:
    """A shut month: 100 -> 0 is a 100% movement; 0 -> 100 has no percentage
    (stage 2's rule, shared.numbers.pct_change) and is skipped. Ten months,
    so nine pairs, one skipped: eight movements."""
    history = [f"2023-{m:02d}" for m in range(1, 11)]
    revenue = dict(zip(history, [100.0, 100.0, 100.0, 100.0, 0.0, 100.0, 100.0, 100.0, 100.0, 100.0]))
    movement = measure_movement(history, revenue, revenue_prev=100.0, revenue_cur=101.0)
    # 0, 0, 0, 100, (skipped), 0, 0, 0, 0 -> median 0: any change is singled out.
    assert (movement.movements, movement.typical_pct, movement.singled_out) == (8, 0.0, True)


def test_too_short_a_history_says_so() -> None:
    """Seven months, six movements: one fewer than the engine's baseline."""
    movement = measure_movement(HISTORY[:7], REVENUE, revenue_prev=100.0, revenue_cur=101.0)
    assert (movement.movements, movement.typical_pct, movement.singled_out) == (6, None, None)
    assert movement.reason == "only 6 month-to-month changes before it can be measured, and 7 are needed"
    one = measure_movement(HISTORY[:2], REVENUE, revenue_prev=100.0, revenue_cur=101.0)
    assert one.reason == "only 1 month-to-month change before it can be measured, and 7 are needed"


def test_a_previous_month_with_no_revenue_gives_the_change_no_percentage() -> None:
    movement = measure_movement(HISTORY, REVENUE, revenue_prev=0.0, revenue_cur=50.0)
    assert (movement.change_pct, movement.singled_out) == (None, None)
    assert movement.reason == ("this month's change has no percentage: there is no previous value to "
                               "compare against, so there is no percentage")


# --- the headline -------------------------------------------------------------------------------------


def _trust() -> Trust:
    return Trust(verdict="trusted", checks=[TrustCheck(id="D1", status="ok", evidence={}, message="ok")],
                 limitations=[])


def _h(hid: str, verdict: str, contribution: float | None, share: float | None) -> Hypothesis:
    spec = BY_ID[hid]
    return Hypothesis(id=hid, family=spec.family, lens=spec.lens, statement=spec.render(contribution),
                      verdict=verdict, contribution=contribution, share=share, evidence={}, rule="r")


def _all(*named: Hypothesis) -> list[Hypothesis]:
    """Every catalog hypothesis, the named ones as given, the rest ruled out."""
    given = {h.id: h for h in named}
    return [given.get(spec.id) or _h(spec.id, "ruled_out", None, None) for spec in CATALOG]


INSIDE = HeadlineMovement(change_pct=1.2, typical_pct=4.5, movements=23, factor=2.0, singled_out=False, reason=None)
BEYOND = HeadlineMovement(change_pct=12.0, typical_pct=4.5, movements=23, factor=2.0, singled_out=True, reason=None)
SHORT = HeadlineMovement(change_pct=1.2, typical_pct=None, movements=4, factor=2.0, singled_out=None,
                         reason="only 4 month-to-month changes before it can be measured, and 7 are needed")


def _moved(movement: HeadlineMovement | None, *, alert: bool = False) -> Changes:
    return Changes(1000.0, 1012.0, 12.0, 12.0, alert, movement=movement)


def test_inside_the_usual_range_no_cause_is_singled_out() -> None:
    """S0's shape: B1 fits the +12 (supported, its table row unchanged), but
    +1.2% is under twice the shop's median movement of 4.5%."""
    hypotheses = _all(_h("B1", "supported", 12.0, 1.0))
    headline = choose_headline(_trust(), hypotheses, None, _moved(INSIDE))
    assert headline == Headline(
        rule=7, hypothesis_id=None, lens=None, movement=INSIDE,
        message="Revenue went from 1,000.00 to 1,012.00 (+12.00). This month's change (+1.2%) is within "
                "this shop's usual month-to-month range: under twice its median movement of about 4.5% "
                "over the 23 month-to-month changes before it. No single cause is singled out.")
    assert next(h for h in hypotheses if h.id == "B1").verdict == "supported"


def test_beyond_the_usual_range_rule_6_names_the_cause_as_before() -> None:
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(BEYOND))
    assert (headline.rule, headline.hypothesis_id, headline.movement) == (6, "B1", BEYOND)
    assert headline.message.endswith("(lever lens, 100% of the change).")


def test_the_context_cause_is_gated_too() -> None:
    hypotheses = _all(_h("T2", "supported", 12.0, 1.0))
    assert choose_headline(_trust(), hypotheses, None, _moved(BEYOND)).rule == 5
    assert choose_headline(_trust(), hypotheses, None, _moved(INSIDE)).rule == 7


def test_too_short_a_history_names_no_cause() -> None:
    """Thach, 2026-10-03 (decision 5; was: the cause stood and said the size
    could not be said): without enough history the engine cannot tell a cause
    from noise, and naming one is still a guess - S11 plants nothing and
    named one in 30 of 30 seeds."""
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(SHORT))
    assert (headline.rule, headline.hypothesis_id, headline.lens, headline.movement) == (7, None, None, SHORT)
    assert headline.message == ("Revenue went from 1,000.00 to 1,012.00 (+12.00). "
                                "The history is too short to tell whether this change is larger than this shop's ordinary month-to-month movement (only 4 month-to-month changes before it can be measured, and 7 are needed); the table shows what each hypothesis measured.")


def test_rules_1_to_4_are_not_gated() -> None:
    blocked = Trust(verdict="blocked", checks=[TrustCheck(id="D1", status="blocked", evidence={}, message="gap.")],
                    limitations=[])
    headline = choose_headline(blocked, _all(), None, _moved(INSIDE))
    assert (headline.rule, headline.movement) == (1, None)
    d1 = _h("D1", "supported", 12.0, 1.0)
    assert choose_headline(_trust(), _all(d1), None, _moved(INSIDE)).rule == 2


def test_nothing_supported_keeps_its_own_rule_7_sentence() -> None:
    # Only a cause singled out is gated (3E1b review 1, F6): rule 7's "partly
    # consistent" list stays, the movement attached.
    headline = choose_headline(_trust(), _all(_h("B1", "partial", 1.0, 0.1)), None, _moved(INSIDE))
    assert (headline.rule, headline.movement) == (7, INSIDE)
    assert headline.message.endswith("No single tested cause explains most of the change. "
                                     "Partly consistent: customers bought more often (B1).")


def test_the_sentence_names_the_factor_it_tested() -> None:
    three = INSIDE.model_copy(update={"factor": 3.0})
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(three))
    assert "under 3 times its median movement" in headline.message


def test_a_hand_built_changes_without_a_movement_keeps_the_old_headline() -> None:
    # Unit tests that build Changes by hand pass no movement: the gate is not
    # applied (the pipeline's changes() always measures it - test below).
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(None))
    assert (headline.rule, headline.movement) == (6, None)


def test_the_pipeline_measures_the_movement() -> None:
    from stages.diagnose.step7_inputs import changes
    from tests.stages.diagnose.diagnose_fixtures import daily_months, run_data
    from tests.stages.diagnose.test_hypotheses import step7

    months = [f"2022-{m:02d}" for m in range(1, 13)] + ["2023-01"]
    moved = changes(step7(run_data(daily_months(dict(zip(months, [3100.0] * 12 + [3131.0]))))))
    # The history is 2022-01..12 (December the previous month): eleven pairs,
    # each 0% (to float residue: a month's 3,100 is split over its days);
    # +31 on 3,100 is +1%, beyond twice 0: singled out.
    assert moved.movement is not None
    assert (moved.movement.movements, moved.movement.singled_out) == (11, True)
    assert moved.movement.typical_pct == pytest.approx(0.0, abs=1e-9)
    assert moved.movement.change_pct == pytest.approx(1.0)


# --- mutation check (3E1b) --------------------------------------------------------------------------------


def test_seven_movements_are_enough() -> None:
    """HISTORY[:8]: the first seven movements above - 10, 10, 9.0909,
    5.5556, 2.9412, 4.7619, 4 - median 5.5556%."""
    movement = measure_movement(HISTORY[:8], REVENUE, revenue_prev=104.0, revenue_cur=105.0)
    assert movement.movements == 7 and movement.typical_pct == pytest.approx(6 / 108 * 100)


def test_the_changes_base_is_judged_against_the_money_moved() -> None:
    # 0.01 -> 0.02 is +100% between the two nets, but 0.01 is residue next to
    # a billion moved: no percentage (shared.numbers.pct_change).
    movement = measure_movement(HISTORY, REVENUE, revenue_prev=0.01, revenue_cur=0.02, scale=1e12)
    assert movement.change_pct is None and movement.singled_out is None


def test_nothing_supported_with_too_short_a_history_adds_no_size_sentence() -> None:
    # Rule 7 singles nothing out, so whether the size is known does not matter.
    headline = choose_headline(_trust(), _all(), None, _moved(SHORT))
    assert headline.rule == 7 and "cannot be said" not in headline.message and headline.movement == SHORT


def test_a_context_cause_with_too_short_a_history_is_not_named_either() -> None:
    headline = choose_headline(_trust(), _all(_h("T2", "supported", 12.0, 1.0)), None, _moved(SHORT))
    assert (headline.rule, headline.hypothesis_id) == (7, None)
    assert "too short to tell" in headline.message


def test_a_change_with_no_percentage_keeps_its_cause_and_says_the_size_is_unknown() -> None:
    # Outside decision 5 (too short only): the test cannot run for another
    # reason, the cause stands and says so, as before.
    nopct = HeadlineMovement(change_pct=None, typical_pct=None, movements=23, factor=2.0, singled_out=None,
                             reason="this month's change has no percentage: the previous month had no revenue")
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(nopct))
    assert (headline.rule, headline.hypothesis_id) == (6, "B1")
    assert headline.message.endswith("cannot be said: this month's change has no percentage: the previous "
                                     "month had no revenue.")


@pytest.mark.parametrize("fields", [
    {"singled_out": None, "reason": None},             # untested, but no reason
    {"singled_out": True, "reason": "a reason"},       # tested, yet a reason
    {"singled_out": True, "typical_pct": None},        # tested, without the typical movement
    {"singled_out": False, "change_pct": None},        # tested, without the change
])
def test_the_contract_refuses_an_inconsistent_movement(fields: dict) -> None:
    from pydantic import ValidationError

    base = {"change_pct": 1.2, "typical_pct": 4.5, "movements": 23, "factor": 2.0, "singled_out": False,
            "reason": None}
    with pytest.raises(ValidationError):
        HeadlineMovement(**(base | fields))


def test_the_sentence_never_prints_a_change_that_is_not_under_the_bound() -> None:
    # 3E1b review 2, N5: 36.96 against 18.49 is under twice (36.98), but at
    # one decimal it printed "+37.0% ... about 18.5%". Two decimals then.
    near = INSIDE.model_copy(update={"change_pct": 36.96, "typical_pct": 18.49})
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(near))
    assert "(+36.96%)" in headline.message and "about 18.49%" in headline.message
    assert "(+1.2%)" in choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None,
                                        _moved(INSIDE)).message


def test_a_tiny_change_is_not_printed_as_zero() -> None:
    # 3E1b review 3, R5: -0.04% printed "(-0.0%)".
    tiny = INSIDE.model_copy(update={"change_pct": -0.04, "typical_pct": 4.5})
    headline = choose_headline(_trust(), _all(_h("B1", "supported", 12.0, 1.0)), None, _moved(tiny))
    assert "(-0.04%)" in headline.message
