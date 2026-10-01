"""Runs a scenario through stages 2 and 3 for real - the handover the engine
sees (diagnose_fixtures.run_data does the same) - and scores the diagnosis
against the scenario's expectation (AI_PIPELINE 7.11). The generator never
imports this module: scores flow out of the engine, never back in."""

from dataclasses import dataclass
from datetime import UTC, datetime

from contracts.diagnosis import DiagnosisContract
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.assemble import diagnose
from stages.diagnose.headline import CONTEXT
from stages.diagnose.inputs import build_run_data
from tests.scenarios.scenarios import Scenario
from tests.scenarios.store import MAPPING

NOW = datetime(2026, 10, 1, tzinfo=UTC)
SEVERAL = "several causes"
# A blocked run (rule 1) or missing days (rule 2) names a data problem: no
# false alarm where one was planted - a lost week, a x100 entry (review 3 #4).
DATA_PROBLEMS = {1: frozenset({"D1", "D2", "D3"}), 2: frozenset({"D1"})}


@dataclass(frozen=True)
class Outcome:
    scenario: str
    rule: int
    named: frozenset[str]  # the causes the headline names (rule 5's context, rule 6's id)
    supported: frozenset[str]
    alert: bool
    message: str

    def meets(self, scenario: Scenario) -> bool:
        expected = scenario.expected
        if expected.supported is not None:
            return expected.supported in self.supported
        return self.rule == expected.rule and (expected.names is None or self.named == {expected.names})

    def decoys(self, scenario: Scenario) -> frozenset[str]:
        """Supported, but neither implied nor an accepted consequence of the
        planted cause (Thach's 3E2-F3: both written in the spec)."""
        return self.supported - scenario.implied - scenario.consequences

    def false_alarm(self, scenario: Scenario) -> bool:
        """A headline naming a cause that was not planted: any rule but 7
        where nothing was planted; a blocked run, missing days, routine
        variation or a masked shift where another cause was (review 2 #11);
        a named cause outside the implied set."""
        if scenario.expected.rule == 7 and self.rule != 7:
            return True
        if self.rule in (1, 2, 3, 4) and self.rule != scenario.expected.rule and not (
                DATA_PROBLEMS.get(self.rule, frozenset()) & scenario.implied):
            return True
        return bool(self.named - scenario.implied)


def diagnosis_of(scenario: Scenario, seed: int) -> DiagnosisContract:
    frame = scenario.build(seed)
    metrics = assemble_metrics(frame, MAPPING, now=NOW)
    return diagnose(build_run_data(frame, MAPPING, metrics), NOW)


def outcome_of(scenario: Scenario, diagnosis: DiagnosisContract) -> Outcome:
    headline = diagnosis.headline
    if headline.rule == 5:
        # Rule 5 names T1 and T2 by two fixed phrases the engine owns
        # (headline.CONTEXT), not by a hypothesis id: matched as constants,
        # the way a test pins rendered words - never a statement parsed.
        named = frozenset(i for i, words in CONTEXT.items() if words in headline.message)
    elif headline.rule == 6 and headline.hypothesis_id is not None:
        named = frozenset({headline.hypothesis_id})
    elif headline.rule == 6:
        # A tie, or the movements that offset each other: several causes,
        # rendered as their statements, which the contract does not list by
        # id and a sentence is never parsed for (CLAUDE.md 3.7) - scored as
        # naming no single planted cause, and as a false alarm (3E2 review 1
        # #13: conservative).
        named = frozenset({SEVERAL})
    else:
        named = frozenset()
    lever = diagnosis.tree.lever if diagnosis.tree is not None else None
    return Outcome(scenario.id, headline.rule, named,
                   frozenset(h.id for h in diagnosis.hypotheses if h.verdict == "supported"),
                   bool(lever and lever.masked_shift_alert), headline.message)


def run(scenario: Scenario, seed: int) -> Outcome:
    return outcome_of(scenario, diagnosis_of(scenario, seed))
