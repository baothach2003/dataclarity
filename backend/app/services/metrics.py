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

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RunStatus
from app.schemas import AnalyzeResponse
from app.services import run_state, stage_errors
from app.services.analysis import is_not_inventory, not_inventory_notice, read_schema
from app.services.run_memory import RunWork
from shared.run_registry import RunNotFoundError, run_file
from stages.analyze.assemble import analyze_run
from shared.transactions import RequiredColumnMissingError
from stages.analyze.metrics_core import CLEANED_FILENAME, CLEANING_REPORT_FILENAME

# `analyzed` is allowed too: re-running overwrites only this stage's own
# output (docs/CONTRACTS.md section 1), same as re-profiling in 1B/1G.
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

    with work.execution(run_id):
        try:
            metrics = analyze_run(runs_root, run_id)
        except RequiredColumnMissingError as error:
            raise stage_errors.analysis_failed(
                str(error), {"canonical_field": error.canonical_field}
            ) from error

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
