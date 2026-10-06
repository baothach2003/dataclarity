"""Stage 3 Diagnose - assembles diagnosis.json (docs/CONTRACTS.md section 7)
from the deterministic engine's steps 1-7 (docs/AI_PIPELINE.md section 7)
and writes it to runs/<run_id>/ atomically.

Session 3G-lite (Thach, 2026-09-29): the designed degraded mode - no AI
narration yet, so `ai_findings` and `model_used` are null and every computed
block, the code-written headline included, stands (AI_PIPELINE section 9).
Step 8 (3F) adds only the narration. If the trust gate blocks, steps 3-6 are
skipped, their blocks are null, and the headline states the data problem.
"""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from contracts.diagnosis import (
    NO_YEAR_AGO_PAIR,
    DiagnosisContract,
    Frame,
    Headline,
    Hypothesis,
    Lever,
    NotTestable,
    Trust,
    YearAgo,
)
from pydantic import ValidationError

from shared.contract_files import write_atomically
from shared.run_registry import run_file
from stages.diagnose.calendar_effect import compute_calendar
from stages.diagnose.catalog import NOT_TESTABLE
from stages.diagnose.frame import build_frame, history_window
from stages.diagnose.headline import choose_headline, hypotheses_note
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.inputs import RunData, load_run
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_localization
from stages.diagnose.signals import compute_signals
from stages.diagnose.step7_inputs import Step7Inputs, changes
from stages.diagnose.suggestions import named_suggestions, stage_3_notes
from stages.diagnose.tree import compute_tree
from stages.diagnose.trust import evaluate_trust

# The major the engine writes (contracts/diagnosis.py's supported_major; its
# comment says what each major changed).
# 18.1 (Thach, 2026-10-03): hypotheses_note; 18.2 (2026-10-04): headline.movement.season; 18.3
# (2026-10-04, (vi)-(vii)): hypotheses[].against_the_change and rule 2's note; 18.4 (the report
# redesign, step 1, 2026-10-05): tree.lever.bridge, year_ago, headline.hedge - all additive; 18.5
# (Thach, item 1): bridge_withheld "failed_checks" - a vocabulary grown, additive by his ruling; 18.6
# (Thach, Q33): headline.named, the hypotheses behind rules 5 and 6; 18.7 (Q39, Q40): trust.checks[].month and
# headline.offsetting; 18.8 (Q62): hypotheses[].member, R1's top member.
SCHEMA_VERSION = "18.8"
logger = logging.getLogger(__name__)
DIAGNOSIS_FILENAME = "diagnosis.json"


def diagnose(data: RunData, now: datetime | None = None) -> DiagnosisContract:
    """Steps 1-7 on one run's data, validated against contracts/diagnosis.py.
    Pure: writes nothing."""
    history = history_window(data)
    frame = build_frame(data)
    trust = evaluate_trust(data, history)
    if trust.verdict == "blocked":
        # The engine refuses to diagnose data it does not believe.
        calendar = signals = tree = localization = None
    else:
        period = data.metrics.period
        calendar = compute_calendar(data, history)
        signals = compute_signals(data, history)
        tree = compute_tree(data, history)
        localization = compute_localization(
            data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    inputs = Step7Inputs(data, history, frame, trust, calendar, signals, tree, localization)
    hypotheses = evaluate_hypotheses(inputs)
    headline = choose_headline(trust, hypotheses, tree, changes(inputs))
    # 18.7: every headline says whether it is rule 6's offsetting case (only
    # that case sets it true). Validated, not copied: a copy runs no validator.
    headline = Headline.model_validate(headline.model_dump() | {"offsetting": bool(headline.offsetting)})
    fields = dict(
        schema_version=SCHEMA_VERSION,
        generated_at=now or datetime.now(UTC),
        model_used=None,
        frame=frame,
        trust=trust,
        calendar=calendar,
        signals=signals,
        tree=tree,
        localization=localization,
        hypotheses=hypotheses,
        not_testable=[NotTestable(**asdict(spec)) for spec in NOT_TESTABLE],
        headline=headline,
        hypotheses_note=hypotheses_note(headline),
        **_year_ago(frame, trust, hypotheses),
        ai_findings=None,
        notes=stage_3_notes(data),
        suggested_classes=named_suggestions(data, localization, hypotheses),
    )
    try:
        return DiagnosisContract(**fields)
    except ValidationError as refused:
        if tree is None or tree.lever.bridge is None:
            raise
        # The bridge is a display (Thach, item 1): a file the contract refuses
        # only for its bridge is written without it - the bridge withheld, every
        # other field as computed. Refused without the bridge too, it was not
        # the bridge's fault, and the first refusal stands.
        # Validated, not copied: a copy runs no validator, and a lever its own
        # rules refuse would be written for every reader to refuse (review of
        # item 1c, #4).
        lever = Lever.model_validate(tree.lever.model_dump() | {"bridge": None, "bridge_withheld": "failed_checks"})
        fields["tree"] = tree.model_copy(update={"lever": lever})
        try:
            withheld = DiagnosisContract(**fields)
        except ValidationError as remaining:
            # What still fails without the bridge is the real cause (review
            # of item 1c, #2): raised, the bridge's refusal chained to it.
            raise remaining from refused
        logger.error("the diagnosis refused its bridge; it is withheld and the file written without it: %s", refused)
        return withheld


def _year_ago(frame: Frame, trust: Trust, hypotheses: list[Hypothesis]) -> dict[str, YearAgo | str | None]:
    """T2's pair as a fact (the report redesign, step 1): the same two months
    a year earlier, T2's own revenue for them (its evidence), or why there
    is none. A blocked run carries no analysis. The frame names a pair only
    among the months the file covers whole (`months_with_rows`); days with no
    sales INSIDE such a month are T2's to judge, and its verdict stands beside
    these figures (doubt-review cycle 2 #6)."""
    if trust.verdict == "blocked":
        return {"year_ago": None, "year_ago_reason": "the diagnosis is blocked"}
    if frame.year_ago_previous is None or frame.year_ago_current is None:
        return {"year_ago": None, "year_ago_reason": NO_YEAR_AGO_PAIR}
    # T2's own pair, read from its evidence - equal by construction, however
    # T2 reads the months (review of item 1c, #3): T2 writes ly_prev / ly_cur
    # whenever the frame has the pair.
    evidence = next(h.evidence for h in hypotheses if h.id == "T2")
    return {"year_ago": YearAgo(previous=frame.year_ago_previous, current=frame.year_ago_current,
                                revenue_previous=evidence["ly_prev"], revenue_current=evidence["ly_cur"]),
            "year_ago_reason": None}


def diagnose_run(runs_root: Path, run_id: str, now: datetime | None = None,
                 around_write: Callable[[], AbstractContextManager[object]] | None = None) -> DiagnosisContract:
    """Read runs/<run_id>/ (metrics.json, cleaned.csv, cleaning_report.json),
    diagnose it and write diagnosis.json atomically: a failed step leaves the
    previous file whole. Re-running overwrites only this stage's own output
    (docs/CONTRACTS.md section 1). `around_write` wraps the rename of the
    new file, once it is computed and staged (as stage 2's)."""
    diagnosis = diagnose(load_run(runs_root, run_id), now)
    write_atomically(run_file(runs_root, run_id, DIAGNOSIS_FILENAME),
                     diagnosis.model_dump_json(indent=2).encode("utf-8"), around_replace=around_write)
    return diagnosis
