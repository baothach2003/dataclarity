"""Each evidence function's own decisions (stages/diagnose/hypothesis_evidence.py).

Written after the 3E1 mutation check: 21 mutants survived because these
functions were only exercised end-to-end on shapes where their requirement
and sign logic did not matter. Each test isolates one decision, with the
blocks stood in by small objects and every number derived by hand.
"""

from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest

import stages.diagnose.hypothesis_evidence_customers as customers_module
from stages.diagnose.catalog import BY_ID
from stages.diagnose.hypotheses import share_verdict
from stages.diagnose.hypothesis_evidence import EVIDENCE
from stages.diagnose.step7_inputs import Changes
from stages.diagnose.stockout import detect_stockouts
from tests.stages.diagnose.diagnose_fixtures import full_months, row, run_data
from tests.stages.diagnose.test_hypotheses import by_id, step7
from tests.stages.diagnose.test_rule_one_reliability import months
from stages.diagnose.hypotheses import evaluate_hypotheses

DOWN = Changes(1000.0, 800.0, -200.0, -200.0, False)
CUSTOMER = NS(reverse={"customer": "Cust"})


def evaluate(hypothesis_id: str, inputs, moved: Changes = DOWN):
    return EVIDENCE[hypothesis_id](inputs, moved)


# --- data quality ---------------------------------------------------------------


def _trust(check_id: str, status: str, **evidence):
    return NS(trust=NS(checks=[NS(id=check_id, status=status, evidence=evidence,
                                  message="could not run")]))


def test_d1_nets_the_two_gaps_at_their_own_pace() -> None:
    """Missing days this month worth 120 at this month's pace pull the change
    down; missing days last month worth 45 at last month's pace pushed it up:
    45 - 120 = -75."""
    outcome = evaluate("D1", _trust("D1", "caution", estimated_revenue_gap=120.0,
                                    estimated_revenue_gap_prev=45.0))

    assert outcome.contribution == -75.0


def test_d1_is_ruled_out_when_its_check_found_nothing() -> None:
    """Tied to the check (Thach, 3E1): excess zero days under the check's
    thresholds are noise, and D1 came out supported on 17-24 of 40 sparse
    shops with no missing data."""
    outcome = evaluate("D1", _trust("D1", "ok", estimated_revenue_gap=40.0,
                                    estimated_revenue_gap_prev=0.0,
                                    excess_zero_days_cur=1.0, excess_zero_days_prev=0.0))

    assert outcome.verdict == "ruled_out"


def test_d1_that_could_not_run_is_inconclusive() -> None:
    outcome = evaluate("D1", _trust("D1", "inconclusive"))

    assert outcome.verdict == "inconclusive"


@pytest.mark.parametrize("status,verdict", [
    ("caution", "supported"), ("inconclusive", "inconclusive"), ("ok", "ruled_out")])
def test_d2_follows_its_check(status, verdict) -> None:
    assert evaluate("D2", _trust("D2", status)).verdict == verdict


# --- time -----------------------------------------------------------------------


@pytest.mark.parametrize("prev,ly_cur,label", [
    (-100.0, 1500.0, "this year's previous month netted negative"),
    (1000.0, -100.0, "last year's current month netted negative"),
])
def test_t2_needs_positive_months_to_scale(prev, ly_cur, label) -> None:
    """A seasonal ratio applied to a negative month flips sign. 26 months
    ending 2012-02; the year-ago previous month (2011-01) is an ordinary 1,000,
    so only the positivity rule can refuse."""
    values = months([1000.0] * 26)
    values["2012-01"] = prev
    values["2011-02"] = ly_cur
    data = run_data(full_months(values))

    t2 = by_id(evaluate_hypotheses(step7(data)))["T2"]

    assert t2.verdict == "inconclusive", label
    assert "zero or below" in t2.rule


# --- customers ------------------------------------------------------------------


def _bridge(censored: bool, previous=True):
    before = NS(new=300.0, lapsed=-100.0, resurrected=80.0)
    return NS(data=NS(parsed=CUSTOMER), tree=NS(customers=NS(
        new=120.0, lapsed=-250.0, resurrected=30.0,
        previous_transition=before if previous else None,
        evidence={"left_censored": censored})))


@pytest.mark.parametrize("hypothesis_id,expected", [
    ("C1", 120.0 - 300.0), ("C2", -250.0 - (-100.0)), ("C3", 30.0 - 80.0)])
def test_the_c_family_compares_two_transitions(hypothesis_id, expected) -> None:
    """new 300 -> 120, lapsed -100 -> -250, resurrected 80 -> 30."""
    assert evaluate(hypothesis_id, _bridge(censored=False)).contribution == expected


@pytest.mark.parametrize("hypothesis_id,verdict", [
    ("C1", "inconclusive"), ("C2", None), ("C3", "inconclusive")])
def test_left_censoring_blocks_new_and_resurrected_only(hypothesis_id, verdict) -> None:
    """Near the file start everyone looks new or resurrected; who LAPSED is
    unaffected, so C2 is still judged (a contribution, no verdict yet)."""
    outcome = evaluate(hypothesis_id, _bridge(censored=True))

    assert outcome.verdict == verdict


@pytest.mark.parametrize("hypothesis_id", ["C1", "C2", "C3"])
def test_the_c_family_needs_the_previous_transition(hypothesis_id) -> None:
    assert evaluate(hypothesis_id, _bridge(False, previous=False)).verdict == "inconclusive"


def test_c4_partial_band(monkeypatch) -> None:
    """All six segments. Previous 102 customers: strong 40, weak 21. Current
    102: strong 38, weak 22. Weak +1/102, strong -2/102 points x 100:
    unfavourable 300/102 = 2.94 points, between C4_RULE_OUT_POINTS (1) and
    C4_SUPPORT_POINTS (5): partial."""
    # The rule behind C4's v1 switch (3E1 cycle 3): pinned so it is right
    # when stage 2 anchors segments per month and the switch goes on.
    monkeypatch.setattr(customers_module, "SEGMENTS_ANCHORED_TO_THE_PERIOD", True)
    segments = [NS(segment="Champions", customers=19, customers_previous=20),
                NS(segment="Loyal", customers=19, customers_previous=20),
                NS(segment="At-risk", customers=21, customers_previous=20),
                NS(segment="Hibernating", customers=1, customers_previous=1),
                NS(segment="New", customers=41, customers_previous=40),
                NS(segment="Needs Attention", customers=1, customers_previous=1)]
    inputs = NS(data=NS(parsed=CUSTOMER, metrics=NS(customers=NS(segments=segments))))

    outcome = evaluate("C4", inputs)

    assert outcome.evidence["unfavourable_points"] == pytest.approx(300 / 102, abs=1e-4)
    assert outcome.verdict == "partial"


# --- lever ----------------------------------------------------------------------


def test_b1_needs_the_three_factor_split() -> None:
    """A customer column is mapped, but a period had no identified customers,
    so level 1 fell back to orders x AOV: frequency cannot be read."""
    inputs = NS(data=NS(parsed=CUSTOMER), tree=NS(
        returns=NS(returns_prev=0.0, returns_cur=0.0),
        lever=NS(level1=NS(formula="orders*aov", factors=[]),
                 reasons={"level1_form": "no identified customers in one period"})),
                trust=NS(checks=[NS(id="D1", status="ok", evidence={
                    "excess_zero_days_cur": 0.0, "excess_zero_days_prev": 0.0})]))

    outcome = evaluate("B1", inputs)

    assert outcome.verdict == "inconclusive"
    assert "three-factor" in outcome.rule or "customers x frequency" in outcome.rule


def test_b2_reads_units_per_order_not_price() -> None:
    level2 = NS(factors=[NS(name="units_per_order", contribution=-70.0, value_prev=4.0, value_cur=3.5),
                         NS(name="price_per_unit", contribution=25.0, value_prev=10.0, value_cur=10.5)])
    inputs = NS(tree=NS(lever=NS(level2=level2, reasons={}),
                        returns=NS(returns_prev=0.0, returns_cur=0.0)))

    assert evaluate("B2", inputs).contribution == -70.0


@pytest.mark.parametrize("hypothesis_id", ["B1", "B2"])
@pytest.mark.parametrize("returns_prev,returns_cur", [(0.0, 50.0), (80.0, 0.0)])
def test_b1_b2_are_inconclusive_while_return_lines_count_as_orders(
    hypothesis_id, returns_prev, returns_cur,
) -> None:
    """INTERIM until 2E (Thach, 3E1): a return line is an order with negative
    units today, so refunds read as smaller baskets and rarer purchases. B2
    headlined "baskets got smaller" at 2.4x the change when only returns had
    changed. Either period with any refund makes both inconclusive."""
    inputs = NS(data=NS(parsed=CUSTOMER), tree=NS(
        returns=NS(returns_prev=returns_prev, returns_cur=returns_cur)))

    assert evaluate(hypothesis_id, inputs).verdict == "inconclusive"


# --- product and returns --------------------------------------------------------


def test_p3_is_minus_the_change_in_returns() -> None:
    """Returns grew from 100 to 150: 50 more refunded, -50 of change."""
    inputs = NS(tree=NS(returns=NS(returns_prev=100.0, returns_cur=150.0)))

    assert evaluate("P3", inputs).contribution == -50.0


def _two_products(october: dict, november: dict):
    rows = []
    for (month, day), basket in (((10, 1), october), ((11, 30), november)):
        for product, (qty, price) in basket.items():
            rows.append(row(date(2011, month, day), qty=qty, price=price, product=product))
    return run_data(rows)


def test_p1_and_p2_read_their_own_pvm_term() -> None:
    data = _two_products({"A": (10, 10.0)}, {"A": (10, 8.0)})
    inputs = step7(data)
    products = inputs.tree.products

    assert evaluate("P1", inputs).contribution == products.price
    assert evaluate("P2", inputs).contribution == products.mix
    assert products.price != products.mix


def test_p1_needs_a_product_sold_in_both_periods() -> None:
    """A sold only in October, B only in November: no like-for-like set."""
    data = _two_products({"A": (10, 10.0)}, {"B": (10, 10.0)})

    assert evaluate("P1", step7(data)).verdict == "inconclusive"


def test_r2_adds_launches_and_discontinuations() -> None:
    inputs = NS(tree=NS(products=NS(new_products=300.0, discontinued_products=-450.0)))

    assert evaluate("R2", inputs).contribution == -150.0


def test_r1_needs_concentration_and_the_top_product_moving_with_the_total() -> None:
    """A fell 900 while the total fell: concentrated and moving with it ->
    supported. Same data under a `mixed` breadth -> ruled_out. And with the
    total RISING, A's fall is against it -> ruled_out."""
    data = _two_products({"A": (100, 10.0), "B": (10, 10.0)}, {"A": (10, 10.0), "B": (10, 10.0)})

    def r1(classification: str, moved: Changes):
        inputs = NS(data=data, localization=NS(breadth=NS(classification=classification,
                                                           top_member_share=0.9)))
        return evaluate("R1", inputs, moved).verdict

    fell = Changes(1100.0, 200.0, -900.0, -900.0, False)
    rose = Changes(1100.0, 1300.0, 200.0, 200.0, False)
    assert r1("concentrated", fell) == "supported"
    assert r1("mixed", fell) == "ruled_out"
    assert r1("concentrated", rose) == "ruled_out"


# --- the share rule on the product lens -----------------------------------------


def test_the_product_lens_is_judged_against_gross_sales() -> None:
    """Revenue fell 200 but GROSS sales rose 50 (returns grew by 250). A price
    effect of -30 is against the gross change the product lens decomposes:
    ruled_out, share -30 / 50 = -0.6. Judged against revenue it would have
    been a partial -0.15."""
    moved = Changes(1000.0, 800.0, -200.0, 50.0, False)

    verdict, share, _ = share_verdict(BY_ID["P1"], -30.0, NS(tree=None), moved)

    assert (verdict, share) == ("ruled_out", pytest.approx(-0.6))


# --- stockout rate boundary ------------------------------------------------------


def test_a_rate_of_exactly_one_half_qualifies() -> None:
    """Sundays closed: October 2011 has 26 trading days. A sells on the first
    13 of them (rate 0.50 = R3_MIN_ACTIVE_DAY_RATE, which qualifies), every
    trading day of November up to the 16th, then stops: from Thursday 17 to
    Wednesday 30 is 12 trading days."""
    rows, trading = [], []
    day = date(2011, 10, 1)
    while day <= date(2011, 11, 30):
        if day.weekday() != 6:
            rows.append(row(day, qty=1, price=10.0, product="B"))
            trading.append(day)
        day += timedelta(days=1)
    october = [d for d in trading if d.month == 10]
    assert len(october) == 26
    for d in october[:13] + [d for d in trading if d.month == 11 and d.day <= 16]:
        rows.append(row(d, qty=1, price=100.0, product="A"))

    found = detect_stockouts(run_data(rows))

    assert [(item.product, item.active_day_rate_prev) for item in found] == [("A", 0.5)]


def test_c4_refuses_when_a_segment_has_emptied() -> None:
    """3E1 doubt-review #7. Stage 2 lists only the segments present NOW, so a
    segment that emptied vanishes from BOTH totals. True previous: Champions
    30, Loyal 20, Hibernating 20, Needs Attention 30; true current: Champions
    30, Loyal 20, At-risk 5, Needs Attention 45 - a 15-point FAVOURABLE move.
    Without Hibernating in the list the previous total is 80, not 100, and C4
    came out supported at 17.5 unfavourable points. When any of stage 2's six
    segments is missing, the previous total cannot be trusted: inconclusive."""
    segments = [NS(segment="Champions", customers=30, customers_previous=30),
                NS(segment="Loyal", customers=20, customers_previous=20),
                NS(segment="At-risk", customers=5, customers_previous=0),
                NS(segment="Needs Attention", customers=45, customers_previous=30)]
    inputs = NS(data=NS(parsed=CUSTOMER, metrics=NS(customers=NS(segments=segments))))

    assert evaluate("C4", inputs).verdict == "inconclusive"
