"""Session 3E2: the planted-cause suite (AI_PIPELINE 7.11) at the seed fixed
before the engine first ran on it (store.SEED). Pinned again after 3E1b (D1's
pattern, the headline's size test - Thach's 3E2-F1); the 3E2 re-run decides
the rest.

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
# supported hypothesis). Measured 2026-10-01 with MASKED_MIN_CONTRIBUTION_SHARE 0.25;
# again 2026-10-02 after 3E1b (S0 and S7 changed: the size test); again
# 2026-10-03 after Thach's decisions on the eleventh run (S11: too short names
# no cause); S12 and S13 added 2026-10-04 (decision 1: a claimed season, a
# stated fact).
SAID = {
    "S0": (7, set(), {"B1", "P2", "T1"}),
    "S1": (6, {"B1"}, {"B1", "T1"}),
    "S2": (6, {"P1"}, {"P1"}),
    "S3": (6, {"P2"}, {"P2"}),
    "S4": (6, {"C2"}, {"C2"}),
    "S5": (2, set(), {"C2", "D1"}),
    "S6": (4, set(), {"C2"}),
    "S7": (7, set(), {"C2", "R3"}),
    "S8": (6, {"R2"}, {"B1", "R2"}),
    "S9": (6, {"B1"}, {"B1", "T2"}),
    "S10": (6, {"P1"}, {"D2", "P1"}),
    "S11": (7, set(), {"B1", "P2", "T1"}),
    "S12": (7, set(), {"B1", "P2", "T1"}),
    "S13": (7, set(), {"B1", "C1", "P2"}),
}
MEETS_THE_SPEC = ("S0", "S2", "S3", "S4", "S5", "S6", "S8", "S10", "S11", "S12", "S13")


@pytest.fixture(scope="module")
def outcomes() -> dict[str, Outcome]:
    return {scenario.id: run(scenario, SEED) for scenario in SCENARIOS}


def test_the_engine_says_what_it_said_when_measured(outcomes: dict[str, Outcome]) -> None:
    assert {i: (o.rule, set(o.named), set(o.supported)) for i, o in outcomes.items()} == SAID


@pytest.mark.parametrize("scenario_id", MEETS_THE_SPEC)
def test_each_scenario_says_what_was_planted(scenario_id: str, outcomes: dict[str, Outcome]) -> None:
    outcome = outcomes[scenario_id]
    assert outcome.meets(BY_ID[scenario_id]), (outcome.rule, sorted(outcome.named), outcome.message)


def test_f1_a_month_with_nothing_planted_names_no_cause(outcomes: dict[str, Outcome]) -> None:
    """3E2-F1, decided by Thach (2026-10-02): revenue moved +159.89 (+0.3%),
    under twice the shop's median movement of 4.5%, so the headline names no
    cause (rule 7). The table is unchanged by his decision - B1, P2 and T1 stay
    supported, the spec's "zero supported" for S0 is not met (the 3E2 re-run
    reports it)."""
    outcome = outcomes["S0"]
    assert (outcome.rule, outcome.named, outcome.supported) == (7, set(), {"B1", "P2", "T1"})
    assert "within this shop's usual month-to-month range" in outcome.message
    assert outcome.noted  # decision 4: the table's note says what those verdicts describe


def test_six_months_are_too_short_to_size_and_name_no_cause(outcomes: dict[str, Outcome]) -> None:
    """Thach, 2026-10-03 (decision 5; was a known limit naming B1): S11's six
    complete months give 4 month-to-month changes before the current one, 7
    needed - too short to tell a cause from noise, so none is named, and the
    table carries its note."""
    outcome = outcomes["S11"]
    assert outcome.meets(BY_ID["S11"]) and outcome.noted
    assert (outcome.rule, outcome.named, outcome.supported) == (7, set(), {"B1", "P2", "T1"})
    assert "the history is too short to tell whether this change is larger" in outcome.message.lower()


def test_known_limit_a_stockout_inside_ordinary_noise_names_no_cause(outcomes: dict[str, Outcome]) -> None:
    """KNOWN LIMIT, recorded by Thach with his 3E2-F1 decision: the stockout's
    -6.7% sits under twice the shop's median movement (4.5%), so the headline
    names no cause; R3 stays supported in the table."""
    outcome = outcomes["S7"]
    assert (outcome.rule, outcome.named) == (7, set()) and "R3" in outcome.supported


def test_a_seasonal_store_with_nothing_planted_states_the_season(outcomes: dict[str, Outcome]) -> None:
    """Decision 1 (Thach, 2026-10-03/04): S12's August and September have
    equal indices - its month moved +0.28% against a median of -0.06% in the
    two earlier Septembers, a gap of +0.34 points (printed as +0.3 - (-0.1) =
    +0.4) within twice the usual 3.87: consistent with the season, no cause
    named, the table's note."""
    outcome = outcomes["S12"]
    assert (outcome.rule, outcome.named, outcome.season, outcome.noted) == (7, set(), "consistent", True)
    assert "The change is consistent with the season; no other cause is singled out." in outcome.message


def test_a_season_masking_lapsed_customers_is_stated_as_a_shortfall(outcomes: dict[str, Outcome]) -> None:
    """KNOWN LIMIT, recorded by Thach (2026-10-04): the season predicts about
    +46% and 30% of the customers lapse, so the month still rose (+5.3%) - 40.5
    points short of the two earlier Septembers. The headline states the
    shortfall and names no cause: every hypothesis measures the change from
    last month (T2 the change the season predicts) and none the gap from the
    season, and C2 moved against the change (its verdict ruled out - 8D)."""
    outcome = outcomes["S13"]
    assert (outcome.rule, outcome.named, outcome.season, outcome.noted) == (7, set(), "shortfall", True)
    assert outcome.message.endswith("None of the tested causes measures this gap from the season, so none is "
                                    "named for the shortfall.")


@pytest.mark.parametrize("scenario_id,context", [("S1", "T1"), ("S9", "T2")])
def test_known_limit_f2_the_mechanism_takes_the_context_causes_place(
        scenario_id: str, context: str, outcomes: dict[str, Outcome]) -> None:
    """KNOWN LIMIT, 3E2-F2 (decided by Thach, 2026-10-03: no context
    precedence - the re-run proved there is no safe gap). The spec: rule 5
    naming the calendar (S1) or the season (S9). The context cause is
    supported but B1 - fewer orders from every customer, the way a calendar
    or a season works - fits closer under the one fit of rules 5 and 6 (2E-o
    Q1) and takes the headline: true, and it hides the cause; the table still
    shows the context cause."""
    outcome = outcomes[scenario_id]
    assert not outcome.meets(BY_ID[scenario_id])
    assert context in outcome.supported and (outcome.rule, outcome.named) == (6, {"B1"})


def test_the_scores_the_readme_quotes(outcomes: dict[str, Outcome], capsys: pytest.CaptureFixture[str]) -> None:
    """The README quotes these: a change here is a change there. S0, S11, S12
    and S13 leave the decoy count (Thach, 2026-10-03, decision 4: their
    criterion is no cause and the table's note); every other scenario's criterion is at
    most one decoy in 25 of 30 seeds (the 30-seed re-run). C2 beside the
    stockout (S7) and B1 beside the discontinued products (S8) are accepted
    consequences (3E2-F3); R3 beside S3 is not (decision 6: it follows by
    chance, not by definition). S10 meets its expectation by its verdict
    (D2 supported), not by its headline, which names the price change the
    x100 error made - 10 headlines meet their expectation: 9 say what was
    planted (S0's, S11's and S12's "nothing" included) and S13's states the
    shortfall against the season without the cause (a known limit)."""
    accuracy = sum(outcomes[s.id].meets(s) for s in SCENARIOS)
    by_headline = sum(outcomes[s.id].meets(s) for s in SCENARIOS if s.expected.supported is None)
    decoys = sorted((s.id, d) for s in SCENARIOS for d in outcomes[s.id].decoys(s))
    alarms = sorted(s.id for s in SCENARIOS if outcomes[s.id].false_alarm(s))
    with capsys.disabled():
        print(f"\n3E2 suite at seed {SEED}: expectation met {accuracy}/{len(SCENARIOS)} "
              f"({by_headline} by the headline), decoys {len(decoys)} {decoys}, false alarms {len(alarms)} {alarms}")
    assert (accuracy, by_headline, alarms) == (11, 10, [])
    assert decoys == []


def test_the_masked_shift_fires_on_s6_only(outcomes: dict[str, Outcome]) -> None:
    # 3E2's sweep set MASKED_MIN_CONTRIBUTION_SHARE to 0.25 (thresholds.py).
    # At the seed S6's month fell 24.887% against a flat bound of 25%.
    assert sorted(i for i, outcome in outcomes.items() if outcome.alert) == ["S6"]


def test_lapsed_customers_in_a_flat_season_are_still_named() -> None:
    """Method amendment 2, B7/B8 (decided alone under CLAUDE.md 3.3a): S4's
    plant in S12's store, whose season leaves September flat - the change
    from last month IS the gap from the season, so C2 explains it and the
    size test names it, as at HEAD 6e9b224 (29 of 30 seeds). Its headline
    stands word for word; the gap is stated after it, never "the tested
    causes do not explain the shortfall". Not a spec scenario: a check."""
    from tests.scenarios.scenarios import CURRENT, FIRST, FLAT_AUGUST_SEASON, LAST, Expected, Scenario, _active_on, \
        _sep, _some
    from tests.scenarios.store import MonthPlan, generate

    def flat_lapse(seed: int):
        gone = _some(_active_on(_sep(1), seed), 0.30, seed, 4)
        return generate(FIRST, LAST, seed=seed, plans={CURRENT: MonthPlan(dropped_customers=gone)},
                        season=lambda month: FLAT_AUGUST_SEASON[month])

    outcome = run(Scenario("S4F", "lapsed customers, a flat season", Expected(rule=6, names="C2"),
                           frozenset({"C2"}), flat_lapse), SEED)
    assert (outcome.rule, outcome.named, outcome.season) == (6, {"C2"}, "shortfall")
    assert outcome.message == (
        "Revenue went from 57,282.05 to 40,073.50 (-17,208.55). The best-supported explanation: lapsed customers "
        "took more revenue away (customers lens, 89% of the change). This month's change (-30.0%) compares with "
        "the same month in the 2 earlier years (median -0.1%): the gap (-29.9 points) is 7.7 times this shop's "
        "median year-on-year difference of about 3.9 points.")


def test_rule_5_naming_t2_is_read_by_its_one_wording() -> None:
    # Thach, 2026-10-04 (ii): rule 5 names T2 in one wording, claim or none -
    # matched as an engine-owned constant.
    from types import SimpleNamespace as NS

    from stages.diagnose.headline import CONTEXT

    assert CONTEXT["T2"] == "the same months a year earlier, which moved the same way"
    stub = NS(headline=NS(rule=5, hypothesis_id=None, message=f"... consistent with {CONTEXT['T2']}: 90% ...",
                          movement=None), tree=None, hypotheses_note=None, hypotheses=[])
    assert outcome_of(BY_ID["S9"], stub).named == {"T2"}  # type: ignore[arg-type]  # a stub


def test_s13_is_met_only_by_the_shortfall() -> None:
    # Decision 1 (Thach, 2026-10-04): naming nothing with the table's note is
    # not enough - the headline must report the season's shortfall (its band,
    # a code; never the sentence).
    from types import SimpleNamespace as NS

    def outcome(band: str | None) -> Outcome:
        season = NS(band=band) if band else None
        stub = NS(headline=NS(rule=7, hypothesis_id=None, message="...", movement=NS(season=season)), tree=None,
                  hypotheses_note="a note", hypotheses=[])
        return outcome_of(BY_ID["S13"], stub)  # type: ignore[arg-type]  # a stub of the diagnosis

    assert outcome("shortfall").meets(BY_ID["S13"])
    assert not any(outcome(band).meets(BY_ID["S13"]) for band in ("consistent", "inconclusive", "excess", None))


def test_a_tie_names_no_single_cause_and_counts_as_a_false_alarm() -> None:
    # Review 1 #13: a tie or the offsetting movements name several causes the
    # contract does not list - scored conservatively, never as "named nothing".
    from types import SimpleNamespace as NS

    tie = NS(headline=NS(rule=6, hypothesis_id=None, message="Equally well supported: ...", movement=None), tree=None,
             hypotheses_note=None,
             hypotheses=[NS(id="P1", verdict="supported"), NS(id="B1", verdict="supported")])
    outcome = outcome_of(BY_ID["S2"], tie)  # type: ignore[arg-type]  # a stub of the diagnosis
    assert outcome.named == {SEVERAL}
    assert not outcome.meets(BY_ID["S2"]) and outcome.false_alarm(BY_ID["S2"])


def test_missing_days_where_another_cause_was_planted_is_a_false_alarm() -> None:
    # Review 2 #11: rules 1-4 name a cause too - a rule-2 headline on the
    # price cut says days were lost when none was.
    from types import SimpleNamespace as NS

    lost_days = NS(headline=NS(rule=2, hypothesis_id=None, message="... days that have no sales ...", movement=None),
                   tree=None, hypotheses_note=None,
                   hypotheses=[NS(id="D1", verdict="supported")])
    outcome = outcome_of(BY_ID["S2"], lost_days)  # type: ignore[arg-type]  # a stub of the diagnosis
    assert outcome.false_alarm(BY_ID["S2"]) and not outcome.false_alarm(BY_ID["S5"])


def test_a_blocked_run_is_no_false_alarm_where_a_data_problem_was_planted() -> None:
    # Review 3 #4: refusing a file whose prices were entered x100 (S10) or
    # whose week was lost (S5) names the planted cause; on the price cut it
    # does not.
    from types import SimpleNamespace as NS

    blocked = NS(headline=NS(rule=1, hypothesis_id=None, message="The data cannot be diagnosed: ...", movement=None),
                 tree=None, hypotheses_note=None,
                 hypotheses=[])
    for scenario_id, alarm in (("S10", False), ("S5", False), ("S2", True)):
        outcome = outcome_of(BY_ID[scenario_id], blocked)  # type: ignore[arg-type]  # a stub of the diagnosis
        assert outcome.false_alarm(BY_ID[scenario_id]) is alarm, scenario_id
