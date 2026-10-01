"""Session 3E2: the planted-cause suite (AI_PIPELINE 7.11) at the seed fixed
before the engine first ran on it (store.SEED). Results are pre-3E1b.

Where the engine says what was planted, the spec's criterion is asserted.
Where it does not - F1 and F2, open for Thach (PROJECT_PLAN 3E2-F1, 3E2-F2)
- today's answer is pinned under a KNOWN LIMIT name, as 3D6's were: no xfail
(CONSTRAINTS F1, F2; 3E2 review 1 #1). Every outcome is pinned exactly, so a
fix - or any other change in what the engine says - fails here until the pin
is replaced by the spec's criterion (review 1 #4).
"""

import pytest

from tests.scenarios.scenarios import SCENARIOS
from tests.scenarios.store import SEED
from tests.stages.diagnose.scenario_runs import SEVERAL, Outcome, outcome_of, run

BY_ID = {scenario.id: scenario for scenario in SCENARIOS}
# What the engine says at the seed: (headline rule, the cause it names, every
# supported hypothesis). Measured 2026-10-01 with MASKED_MIN_CONTRIBUTION_SHARE 0.25.
SAID = {
    "S0": (6, {"B1"}, {"B1", "P2", "T1"}),
    "S1": (6, {"B1"}, {"B1", "T1"}),
    "S2": (6, {"P1"}, {"P1"}),
    "S3": (6, {"P2"}, {"P2"}),
    "S4": (6, {"C2"}, {"C2"}),
    "S5": (2, set(), {"C2", "D1"}),
    "S6": (4, set(), {"C2"}),
    "S7": (6, {"R3"}, {"C2", "R3"}),
    "S8": (6, {"R2"}, {"B1", "R2"}),
    "S9": (6, {"B1"}, {"B1", "T2"}),
    "S10": (6, {"P1"}, {"D2", "P1"}),
    "S11": (6, {"B1"}, {"B1", "P2", "T1"}),
}
MEETS_THE_SPEC = ("S2", "S3", "S4", "S5", "S6", "S7", "S8", "S10")


@pytest.fixture(scope="module")
def outcomes() -> dict[str, Outcome]:
    return {scenario.id: run(scenario, SEED) for scenario in SCENARIOS}


def test_the_engine_says_what_it_said_when_measured(outcomes: dict[str, Outcome]) -> None:
    assert {i: (o.rule, set(o.named), set(o.supported)) for i, o in outcomes.items()} == SAID


@pytest.mark.parametrize("scenario_id", MEETS_THE_SPEC)
def test_each_scenario_says_what_was_planted(scenario_id: str, outcomes: dict[str, Outcome]) -> None:
    outcome = outcomes[scenario_id]
    assert outcome.meets(BY_ID[scenario_id]), (outcome.rule, sorted(outcome.named), outcome.message)


@pytest.mark.parametrize("scenario_id", ["S0", "S11"])
def test_known_limit_f1_a_month_with_nothing_planted_names_a_cause(scenario_id: str,
                                                                    outcomes: dict[str, Outcome]) -> None:
    """KNOWN LIMIT, 3E2-F1 (awaiting Thach). The spec: headline rule 7 and no
    hypothesis supported. Today revenue moved +159.89 (+0.28%) and the
    headline names B1, "customers bought more often (+260.63 against the
    change of +159.89)", with P2 and T1 supported too: a share is measured
    against the change itself, so a term of any decomposition of noise holds
    20% of it. 30 of 30 seeds name a cause."""
    outcome = outcomes[scenario_id]
    assert not outcome.meets(BY_ID[scenario_id])
    assert (outcome.rule, outcome.named, outcome.supported) == (6, {"B1"}, {"B1", "P2", "T1"})


@pytest.mark.parametrize("scenario_id,context", [("S1", "T1"), ("S9", "T2")])
def test_known_limit_f2_the_mechanism_takes_the_context_causes_place(
        scenario_id: str, context: str, outcomes: dict[str, Outcome]) -> None:
    """KNOWN LIMIT, 3E2-F2 (awaiting Thach). The spec: rule 5 naming the
    calendar (S1) or the season (S9). Today the context cause is supported
    but B1 - fewer orders from every customer, the way a calendar or a
    season works - fits closer under the one fit of rules 5 and 6 (2E-o Q1)
    and takes the headline: true, and it hides the cause."""
    outcome = outcomes[scenario_id]
    assert not outcome.meets(BY_ID[scenario_id])
    assert context in outcome.supported and (outcome.rule, outcome.named) == (6, {"B1"})


def test_the_scores_the_readme_quotes(outcomes: dict[str, Outcome], capsys: pytest.CaptureFixture[str]) -> None:
    """The README quotes these: a change here is a change there. The spec
    allows one decoy in the suite; today 8 - F1's six, and two by a planted
    cause's own consequence (3E2-F3, for Thach: whether the implied sets
    should hold them): C2 beside the stockout (S7), B1 beside the
    discontinued products (S8). S10 meets its expectation by its
    verdict (D2 supported), not by its headline, which names the price
    change the x100 error made - 7 headlines name the planted cause."""
    accuracy = sum(outcomes[s.id].meets(s) for s in SCENARIOS)
    by_headline = sum(outcomes[s.id].meets(s) for s in SCENARIOS if s.expected.supported is None)
    decoys = sorted((s.id, d) for s in SCENARIOS for d in outcomes[s.id].decoys(s))
    alarms = sorted(s.id for s in SCENARIOS if outcomes[s.id].false_alarm(s))
    with capsys.disabled():
        print(f"\n3E2 suite at seed {SEED}: expectation met {accuracy}/12 ({by_headline} by the headline), "
              f"decoys {len(decoys)} {decoys}, false alarms {len(alarms)} {alarms}")
    assert (accuracy, by_headline, alarms) == (8, 7, ["S0", "S11"])
    assert decoys == [("S0", "B1"), ("S0", "P2"), ("S0", "T1"), ("S11", "B1"), ("S11", "P2"), ("S11", "T1"),
                      ("S7", "C2"), ("S8", "B1")]


def test_the_masked_shift_fires_on_s6_only(outcomes: dict[str, Outcome]) -> None:
    # 3E2's sweep set MASKED_MIN_CONTRIBUTION_SHARE to 0.25 (thresholds.py).
    # At the seed S6's month fell 24.887% against a flat bound of 25%.
    assert sorted(i for i, outcome in outcomes.items() if outcome.alert) == ["S6"]


def test_a_tie_names_no_single_cause_and_counts_as_a_false_alarm() -> None:
    # Review 1 #13: a tie or the offsetting movements name several causes the
    # contract does not list - scored conservatively, never as "named nothing".
    from types import SimpleNamespace as NS

    tie = NS(headline=NS(rule=6, hypothesis_id=None, message="Equally well supported: ..."), tree=None,
             hypotheses=[NS(id="P1", verdict="supported"), NS(id="B1", verdict="supported")])
    outcome = outcome_of(BY_ID["S2"], tie)  # type: ignore[arg-type]  # a stub of the diagnosis
    assert outcome.named == {SEVERAL}
    assert not outcome.meets(BY_ID["S2"]) and outcome.false_alarm(BY_ID["S2"])


def test_missing_days_where_another_cause_was_planted_is_a_false_alarm() -> None:
    # Review 2 #11: rules 1-4 name a cause too - a rule-2 headline on the
    # price cut says days were lost when none was.
    from types import SimpleNamespace as NS

    lost_days = NS(headline=NS(rule=2, hypothesis_id=None, message="... days that have no sales ..."), tree=None,
                   hypotheses=[NS(id="D1", verdict="supported")])
    outcome = outcome_of(BY_ID["S2"], lost_days)  # type: ignore[arg-type]  # a stub of the diagnosis
    assert outcome.false_alarm(BY_ID["S2"]) and not outcome.false_alarm(BY_ID["S5"])


def test_a_blocked_run_is_no_false_alarm_where_a_data_problem_was_planted() -> None:
    # Review 3 #4: refusing a file whose prices were entered x100 (S10) or
    # whose week was lost (S5) names the planted cause; on the price cut it
    # does not.
    from types import SimpleNamespace as NS

    blocked = NS(headline=NS(rule=1, hypothesis_id=None, message="The data cannot be diagnosed: ..."), tree=None,
                 hypotheses=[])
    for scenario_id, alarm in (("S10", False), ("S5", False), ("S2", True)):
        outcome = outcome_of(BY_ID[scenario_id], blocked)  # type: ignore[arg-type]  # a stub of the diagnosis
        assert outcome.false_alarm(BY_ID[scenario_id]) is alarm, scenario_id
