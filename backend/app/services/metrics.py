"""Stage 2 orchestration: `POST /api/runs/{id}/analyze` (docs/SPECS.md
section 3 "Analyzing insights"; section 8). The logic stays in
`stages/analyze` (CLAUDE.md 3.4); this service enforces the state machine,
guards against a concurrent call for the same run, and shapes the answer.

No AI call anywhere in this stage (docs/adr/0002-pandas-computes-ai-interprets.md),
so none of stage 1's AI-step machinery (retry budgets, notices beyond
NOT_INVENTORY) applies here. A concurrent second call is simply refused
(`work.execution`) rather than raced: unlike `execute`, there is no AI-driven
variance a transient claim status needs to protect against, and
metrics.json is written atomically (`stages.analyze.assemble`), so there is
no partial-write state a crash could strand - a run here is never "stuck"
the way a run could get stuck in `cleaning`.
"""

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RunStatus
from app.schemas import AnalyzeResponse
from app.services import run_state, stage_errors
from app.services.analysis import is_not_inventory, not_inventory_notice, read_schema
from app.services.run_memory import RunWork
from shared import later_outputs
from shared.run_registry import RunNotFoundError, run_file
from shared.transactions import LineClassColumnsError, RequiredColumnMissingError
from stages.analyze.assemble import analyze_run
from stages.analyze.metrics_core import CLEANED_FILENAME, CLEANING_REPORT_FILENAME

# `analyzed` is allowed too: re-running overwrites this stage's own output
# and removes the later stages' (docs/CONTRACTS.md section 1).
ANALYZABLE_STATUSES = (RunStatus.CLEANED, RunStatus.ANALYZED)


def analyze(session: Session, run_id: str, *, settings: Settings, work: RunWork) -> AnalyzeResponse:
    """`cleaned` (or an already-`analyzed` run) -> `analyzed`."""
    runs_root = settings.runs_dir
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *ANALYZABLE_STATUSES, step="analyze")

    schema = read_schema(runs_root, run_id)
    if is_not_inventory(schema):
        notice = not_inventory_notice(schema)
        raise stage_errors.analysis_failed(
            "This file was not identified as inventory or sales data; "
            "stages 2-5 are unavailable.",
            notice.details if notice else None,
        )
    _require_cleaned_files(runs_root, run_id)
    uploaded_at = run.created_at
    # No read transaction held through the wait for the slot and the work: a
    # connection kept while waiting, while a step inside the slot needs one,
    # is the slot-against-pool shape of Q68 (its review).
    session.commit()

    with work.execution(run_id), work.heavy():
        try:
            # The later stages' outputs describe the metrics this run
            # replaces: set aside around the new file's rename, deleted once
            # it succeeds (3G-lite reviews 1-3, DEMO review #2).
            # The upload is the reference for lines dated after it (2E-u6):
            # the same answer however late the run is analysed.
            metrics = analyze_run(runs_root, run_id, around_write=lambda: later_outputs.set_aside(
                runs_root, run_id, after_stage=2), uploaded_at=uploaded_at)
        except RequiredColumnMissingError as error:
            raise stage_errors.analysis_failed(
                str(error), {"canonical_field": error.canonical_field}
            ) from error
        except LineClassColumnsError as error:
            # A cleaned.csv changed after cleaning (2E-t2): the user is told
            # to re-upload, not shown a generic 500.
            raise stage_errors.analysis_failed(str(error), {"line_classes": error.problem}) from error
        except ValidationError as error:
            # A figure whose amounts do not add up: metrics.json cannot carry
            # it (2E-t3 review 3 #4; any month's, 2E-v #1). A run file another
            # version wrote goes on to the app's handler
            # (stage_errors.run_file_version_handler); any other refusal is a
            # bug: a 500.
            if not stage_errors.too_large_to_add(error):
                raise
            raise stage_errors.amounts_too_large(2) from error
        except OverflowError as error:
            # Quantities too large to add: a product's units overflowed before
            # any contract was built (2E-v review 2 #3).
            raise stage_errors.amounts_too_large(2) from error

    run_state.advance(session, run_id, RunStatus.ANALYZED, only_from=ANALYZABLE_STATUSES)
    return AnalyzeResponse(run_id=run_id, status="analyzed", metrics=metrics, notices=[])


def _require_cleaned_files(runs_root: Path, run_id: str) -> None:
    """Explicit, so a missing file (retention cleanup removed the run's
    directory, or just these two files) is EXPIRED (410), not an unhandled
    FileNotFoundError (500) - same reasoning as plan_execution._require_raw."""
    try:
        found = all(
            run_file(runs_root, run_id, filename).exists()
            for filename in (CLEANED_FILENAME, CLEANING_REPORT_FILENAME)
        )
    except RunNotFoundError:
        found = False
    if not found:
        raise stage_errors.files_gone()
