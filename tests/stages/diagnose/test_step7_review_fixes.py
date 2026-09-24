"""Fabrications the 3E1 doubt-review reproduced, each fixed by a decision of
Thach's (3E1), written from the reproduction before the fix.

1. Overshoot: a hypothesis whose contribution is an EXPECTATION (D1, T1, T2,
   R3) or a between-period difference (C1-C3) is supported only when it
   leaves at most 1 - SUPPORTED_MIN_SHARE of the change unexplained: share in
   [0.2, 1.8]. Headlines never print a share above 100%.
2. D1 counts a gap in the PREVIOUS month too, and the trust check cautions
   on it.
3. R3 looks only at top products (at least MEMBER_MIN_REVENUE_SHARE of
   previous revenue) that still sold this month.
4. Headline rule 6 skips D2 and D3: their finding is the caution badge, and
   caution never changes the headline.
"""

from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest

import stages.diagnose.hypothesis_evidence_customers as customers_module
from contracts.diagnosis import Hypothesis
from stages.diagnose.catalog import BY_ID, CATALOG
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses, share_verdict
from stages.diagnose.step7_inputs import Changes, changes
from stages.diagnose.stockout import detect_stockouts
from tests.stages.diagnose.diagnose_fixtures import (
    daily_months,
    daily_rows,
    full_months,
    row,
    run_data,
)
from tests.stages.diagnose.test_hypotheses import by_id, step7
from tests.stages.diagnose.test_rule_one_reliability import months


# --- 1. overshoot ---------------------------------------------------------------


def test_seasonality_that_predicted_ten_times_the_change_does_not_explain_it() -> None:
    """The reproduction: last year January -> February went +50% (1,000 ->
    1,500); this year only +5% (1,000 -> 1,050). T2 = 1,000 * (1,500 / 1,000 -
    1) = +500 against a change of +50: share 10.0. It came out supported and
    headlined "1000% of the change is consistent with seasonality" - the month
    in fact fell 450 short of its season. |1 - 10| = 9 > 0.8: ruled_out.
    Daily rows, so the year-ago months pass T2's coverage check (3E1)."""
    values = months([1000.0] * 26)
    values["2011-02"] = 1500.0
    values["2012-02"] = 1050.0
    inputs = step7(run_data(daily_months(values)))

    results = evaluate_hypotheses(inputs)
    t2 = by_id(results)["T2"]
    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert t2.share == pytest.approx(10.0)
    assert t2.verdict == "ruled_out"
    assert "1000%" not in headline.message


@pytest.mark.parametrize("contribution,verdict", [
    (360.0, "supported"),   # share 1.80, remainder -0.80: at the edge
    (361.0, "ruled_out"),   # share 1.805
    (40.0, "supported"),    # share 0.20
    (39.0, "partial"),      # share 0.195
])
def test_the_residual_band_for_an_expectation(contribution, verdict) -> None:
    """Change +200, D = 200. An expectation is supported iff the same sign and
    |1 - share| <= 1 - SUPPORTED_MIN_SHARE = 0.8, i.e. share in [0.2, 1.8]."""
    moved = Changes(1000.0, 1200.0, 200.0, 200.0, False)

    got, _, _ = share_verdict(BY_ID["T2"], contribution, NS(tree=None), moved)

    assert got == verdict


def test_a_decomposition_term_may_overshoot() -> None:
    """P1 is a term of the product split: +800 on a +200 gross change is real,
    offset by the other terms, and stays supported."""
    moved = Changes(1000.0, 1200.0, 200.0, 200.0, False)

    got, share, _ = share_verdict(BY_ID["P1"], 800.0, NS(tree=None), moved)

    assert (got, share) == ("supported", pytest.approx(4.0))


def test_a_headline_never_prints_a_share_above_one_hundred_percent() -> None:
    hypotheses = [Hypothesis(id=s.id, family=s.family, lens=s.lens, statement=s.statement,
                             verdict="supported" if s.id == "P1" else "ruled_out",
                             contribution=800.0 if s.id == "P1" else None,
                             share=4.0 if s.id == "P1" else None, evidence={}, rule="t")
                  for s in CATALOG]
    moved = Changes(1000.0, 1200.0, 200.0, 200.0, False)
    trust = NS(verdict="trusted", checks=[])
    tree = NS(lever=NS(masked_shift_alert=False))

    headline = choose_headline(trust, hypotheses, tree, moved)

    assert "400%" not in headline.message
    assert "+800.00 against the change in gross sales of +200.00" in headline.message


# --- 2. a gap in the previous month ------------------------------------------------


def test_a_gap_in_the_previous_month_is_counted_and_cautioned() -> None:
    """The reproduction: three products trade daily; 10-21 February 2011 have
    no rows; the comparison is February -> March. Trust said "trusted", D1 was
    ruled_out with a gap of 0, and the +495 rise was credited to another
    cause. February's missing days make the change look bigger: D1 now
    contributes +gap_prev, and the trust check cautions."""
    rows = daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3,
                      skip=tuple(date(2011, 2, d) for d in range(10, 22)))
    inputs = step7(run_data(rows))

    d1 = by_id(evaluate_hypotheses(inputs))["D1"]
    check = next(c for c in inputs.trust.checks if c.id == "D1")

    assert check.status == "caution"
    assert check.evidence["estimated_revenue_gap_prev"] > 0
    assert d1.contribution == pytest.approx(check.evidence["estimated_revenue_gap_prev"]
                                            - check.evidence["estimated_revenue_gap"])
    assert d1.verdict in ("supported", "partial")


# --- 3. R3 scope ---------------------------------------------------------------


def _two_months(extra) -> list[dict]:
    rows = []
    day = date(2011, 10, 1)
    while day <= date(2011, 11, 30):
        rows.append(row(day, qty=10, price=100.0, product="Big"))
        rows += extra(day)
        day += timedelta(days=1)
    return rows


def test_a_tail_product_is_not_a_stockout_candidate() -> None:
    """"Tail" sells 1 unit at 10 daily in October (310 of 31,310, 0.99% of
    previous revenue - under MEMBER_MIN_REVENUE_SHARE, 2%) and stops mid
    November. A rate test alone flags it; the statement says a TOP product."""
    data = run_data(_two_months(
        lambda d: [row(d, qty=1, price=10.0, product="Tail")]
        if d.month == 10 or d.day <= 15 else []))

    assert detect_stockouts(data) == []


def test_a_discontinued_product_is_not_a_stockout() -> None:
    """"Gone" sold daily in October (a top product) and not at all in November.
    That is R2's discontinuation; R3 claimed it too, 181% of the change
    between them. R3 needs the product to have sold this month."""
    data = run_data(_two_months(
        lambda d: [row(d, qty=5, price=100.0, product="Gone")] if d.month == 10 else []))

    assert detect_stockouts(data) == []


# --- 4. rule 6 skips the data-quality flags ------------------------------------------


def test_a_data_quality_flag_never_takes_the_headline() -> None:
    """D3 is supported exactly when its trust check cautions. 7.8: caution
    never changes the headline and is shown beside it. So rule 6 skips D2 and
    D3 and, with nothing else supported, rule 7 speaks."""
    hypotheses = [Hypothesis(id=s.id, family=s.family, lens=s.lens, statement=s.statement,
                             verdict="supported" if s.id in ("D2", "D3") else "ruled_out",
                             contribution=None, share=None, evidence={}, rule="t")
                  for s in CATALOG]
    moved = Changes(1000.0, 800.0, -200.0, -200.0, False)

    headline = choose_headline(NS(verdict="caution", checks=[]), hypotheses,
                               NS(lever=NS(masked_shift_alert=False)), moved)

    assert headline.rule == 7


def test_an_overshooting_product_share_is_printed_against_gross_sales() -> None:
    """The product lens decomposes GROSS sales, so its overshoot is printed
    against the gross change (+200), not net revenue (+150 here, returns grew
    by 50) - otherwise the figure beside it is a different total. (Net was -50
    until 3E1 cycle 3, which stopped rule 6 naming a cause that moved against
    the net change - the fixture's own shape.)"""
    hypotheses = [Hypothesis(id=s.id, family=s.family, lens=s.lens, statement=s.statement,
                             verdict="supported" if s.id == "P1" else "ruled_out",
                             contribution=800.0 if s.id == "P1" else None,
                             share=4.0 if s.id == "P1" else None, evidence={}, rule="t")
                  for s in CATALOG]
    moved = Changes(1000.0, 1150.0, 150.0, 200.0, False)

    headline = choose_headline(NS(verdict="trusted", checks=[]), hypotheses,
                               NS(lever=NS(masked_shift_alert=False)), moved)

    assert "+800.00 against the change in gross sales of +200.00" in headline.message


# --- cycle 2 of the 3E1 doubt-review --------------------------------------------


def test_rule_2_prints_the_netted_effect_not_one_months_gap() -> None:
    """F2. February misses 12 days, March is complete, compared February ->
    March. The verdict comes from D1's netted contribution; the first version
    printed the CURRENT month's gap, "an estimated gap of 0.00".
    Hand-checked: three products at 10, 11, 12 sell daily, 33 a day. February
    trades 16 of 28 days (528), March all 31 (1,023): +495. The 12 missing
    February days at February's pace are 12 x 33 = 396 - share 0.8,
    supported, and at least HEADLINE_CONTEXT_MIN_SHARE: rule 2."""
    rows = daily_rows(date(2010, 1, 1), date(2011, 3, 31), products=3,
                      skip=tuple(date(2011, 2, d) for d in range(10, 22)))
    inputs = step7(run_data(rows))
    results = evaluate_hypotheses(inputs)
    d1 = by_id(results)["D1"]

    headline = choose_headline(inputs.trust, results, inputs.tree, changes(inputs))

    assert (d1.verdict, d1.contribution, d1.share) == ("supported", 396.0, pytest.approx(0.8))
    assert headline.rule == 2
    assert "+396.00" in headline.message


def test_an_expectation_keeps_its_change_as_d_under_the_alert() -> None:
    """F4. Under the masked-shift alert D becomes a decomposition's gross -
    for TERMS. T2 predicted +504 for a +19.20 month; against level 1's gross
    (1,180) that is 0.43 and came out supported. An expectation's overshoot is
    the signal, so its D stays |the change|: share 26.25, ruled_out."""
    tree = NS(lever=NS(level1=NS(factors=[NS(contribution=600.0), NS(contribution=-580.0)])))
    moved = Changes(1000.0, 1019.2, 19.2, 19.2, True)

    verdict, share, rule = share_verdict(BY_ID["T2"], 504.0, NS(tree=tree), moved)

    assert share == pytest.approx(504.0 / 19.2)
    assert verdict == "ruled_out"
    assert "alert" not in rule


def test_the_closest_expectation_wins_not_the_largest() -> None:
    """Ranking by fit (Thach, 3E1). T1 explains the change exactly (share
    1.00); T2 overshoots it by 75% (1.75). Ranking by |share| named T2."""
    hypotheses = [Hypothesis(id=s.id, family=s.family, lens=s.lens, statement=s.statement,
                             verdict="supported" if s.id in ("T1", "T2") else "ruled_out",
                             contribution={"T1": 100.0, "T2": 175.0}.get(s.id),
                             share={"T1": 1.0, "T2": 1.75}.get(s.id), evidence={}, rule="t")
                  for s in CATALOG]
    moved = Changes(1000.0, 1100.0, 100.0, 100.0, False)

    headline = choose_headline(NS(verdict="trusted", checks=[]), hypotheses,
                               NS(lever=NS(masked_shift_alert=False)), moved)

    assert headline.rule == 5
    assert "calendar" in headline.message


def test_c4_explains_a_rise_by_a_move_to_stronger_segments(monkeypatch) -> None:
    """Direction-neutral C4. All six segments; previous 100: strong 30, weak
    30; current 100: strong 40, weak 20. Weak -10, strong +10 points:
    unfavourable -20, i.e. 20 points towards STRONGER segments - with revenue
    rising, supported, rendered "migrated to stronger segments"."""
    # The rule behind C4's v1 switch (3E1 cycle 3): pinned so it is right
    # when stage 2 anchors segments per month and the switch goes on.
    monkeypatch.setattr(customers_module, "SEGMENTS_ANCHORED_TO_THE_PERIOD", True)
    def seg(name, now, before):
        return NS(segment=name, customers=now, customers_previous=before)

    segments = [seg("Champions", 20, 15), seg("Loyal", 20, 15), seg("At-risk", 10, 15),
                seg("Hibernating", 10, 15), seg("New", 30, 30), seg("Needs Attention", 10, 10)]
    inputs = NS(data=NS(parsed=NS(reverse={"customer": "Cust"}),
                        metrics=NS(customers=NS(segments=segments))),
                trust=NS(verdict="trusted"))
    from stages.diagnose.hypothesis_evidence import EVIDENCE

    outcome = EVIDENCE["C4"](inputs, Changes(1000.0, 1200.0, 200.0, 200.0, False))

    assert outcome.evidence["unfavourable_points"] == pytest.approx(-20.0)
    assert outcome.verdict == "supported"
    assert BY_ID["C4"].render(outcome.sign) == "Customers migrated to stronger segments"


def test_the_previous_month_cannot_teach_its_own_gap_away() -> None:
    """M2. The D1 check learned "normal" from a history that included the
    previous month, so a 12-day February gap taught itself away. With three
    months of history the gap is now seen in full (12 excess days); with only
    the previous month as history there is nothing to learn from."""
    skip = tuple(date(2011, 2, d) for d in range(10, 22))
    three = step7(run_data(daily_rows(date(2010, 12, 1), date(2011, 3, 31), products=3, skip=skip)))
    one = step7(run_data(daily_rows(date(2011, 2, 1), date(2011, 3, 31), products=3, skip=skip)))

    d1_three = next(c for c in three.trust.checks if c.id == "D1")
    d1_one = next(c for c in one.trust.checks if c.id == "D1")

    assert d1_three.evidence["excess_zero_days_prev"] == 12.0
    assert d1_one.status == "inconclusive"


def test_d1_prices_each_months_gap_at_that_months_own_pace() -> None:
    """F1, pinned on the check's evidence. Daily history at three products
    (33 a day). February 2011 keeps three products and misses Feb 10-19 (10
    days); March has six products (10+11+...+15 = 75 a day) and misses Mar
    10-14 (5 days). Own pace: February's gap 10 x 33 = 330, March's 5 x 75 =
    375, net effect on the change 330 - 375 = -45. Check: full months would
    have gone 28 x 33 = 924 -> 31 x 75 = 2,325 (+1,401); observed 18 x 33 =
    594 -> 26 x 75 = 1,950 (+1,356); the gaps cost exactly -45."""
    rows = daily_rows(date(2010, 1, 1), date(2011, 2, 28), products=3,
                      skip=tuple(date(2011, 2, d) for d in range(10, 20)))
    rows += daily_rows(date(2011, 3, 1), date(2011, 3, 31), products=6,
                       skip=tuple(date(2011, 3, d) for d in range(10, 15)))
    inputs = step7(run_data(rows))
    check = next(c for c in inputs.trust.checks if c.id == "D1")

    d1 = by_id(evaluate_hypotheses(inputs))["D1"]

    assert (check.evidence["estimated_revenue_gap_prev"],
            check.evidence["estimated_revenue_gap"]) == (330.0, 375.0)
    assert d1.contribution == -45.0
    assert changes(inputs).net == 1356.0


def test_c4_explains_nothing_when_revenue_did_not_move(monkeypatch) -> None:
    """A strong move to weaker segments (20 points) in a month whose revenue
    is flat: there is no change for C4 to explain, whichever way it points."""
    # The rule behind C4's v1 switch (3E1 cycle 3): pinned so it is right
    # when stage 2 anchors segments per month and the switch goes on.
    monkeypatch.setattr(customers_module, "SEGMENTS_ANCHORED_TO_THE_PERIOD", True)
    def seg(name, now, before):
        return NS(segment=name, customers=now, customers_previous=before)

    segments = [seg("Champions", 10, 15), seg("Loyal", 10, 15), seg("At-risk", 20, 15),
                seg("Hibernating", 20, 15), seg("New", 30, 30), seg("Needs Attention", 10, 10)]
    inputs = NS(data=NS(parsed=NS(reverse={"customer": "Cust"}),
                        metrics=NS(customers=NS(segments=segments))),
                trust=NS(verdict="trusted"))
    from stages.diagnose.hypothesis_evidence import EVIDENCE

    outcome = EVIDENCE["C4"](inputs, Changes(1000.0, 1000.0, 0.0, 0.0, False))

    assert outcome.evidence["unfavourable_points"] == pytest.approx(20.0)
    assert outcome.verdict == "ruled_out"
