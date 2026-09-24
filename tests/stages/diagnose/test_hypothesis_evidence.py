"""Each evidence function's own decisions (stages/diagnose/hypothesis_evidence.py).

Written after the 3E1 mutation check: 21 mutants survived because these
functions were only exercised end-to-end on shapes where their requirement
and sign logic did not matter. Each test isolates one decision, with the
blocks stood in by small objects and every number derived by hand.
"""

from datetime import date
from types import SimpleNamespace as NS

import pytest

import stages.diagnose.hypothesis_evidence_customers as customers_module
from stages.diagnose.hypothesis_evidence import EVIDENCE
from stages.diagnose.step7_inputs import Changes
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
    values["2012-01"] = prev - 1000.0 if prev < 0 else prev
    values["2011-02"] = ly_cur
    rows = full_months(values)
    if prev < 0:
        # A month that TRADED and still netted negative: a 1,000 sale beside
        # a 1,100 refund. Built from a refund alone, the previous month holds
        # no sale and blocks the run (2E doubt-review F3) before T2 runs.
        rows.append(row(date(2012, 1, 1), qty=100.0, price=10.0))
    data = run_data(rows)

    t2 = by_id(evaluate_hypotheses(step7(data)))["T2"]

    assert data.metrics.core.revenue_previous == prev
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
