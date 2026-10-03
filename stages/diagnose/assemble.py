"""Stage 3 Diagnose - assembles diagnosis.json (docs/CONTRACTS.md section 7)
from the deterministic engine's steps 1-7 (docs/AI_PIPELINE.md section 7)
and writes it to runs/<run_id>/ atomically.

Session 3G-lite (Thach, 2026-09-29): the designed degraded mode - no AI
narration yet, so `ai_findings` and `model_used` are null and every computed
block, the code-written headline included, stands (AI_PIPELINE section 9).
Step 8 (3F) adds only the narration. If the trust gate blocks, steps 3-6 are
skipped, their blocks are null, and the headline states the data problem.
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from contracts.diagnosis import DiagnosisContract, NotTestable
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
# 18.1 (Thach, 2026-10-03): hypotheses_note; 18.2 (2026-10-04): headline.movement.season - both additive.
SCHEMA_VERSION = "18.2"
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
    return DiagnosisContract(
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
        ai_findings=None,
        notes=stage_3_notes(data),
        suggested_classes=named_suggestions(data, localization, hypotheses),
    )


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
