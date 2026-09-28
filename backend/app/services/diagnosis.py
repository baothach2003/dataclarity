"""Stage 3 orchestration: `POST /api/runs/{id}/diagnose` (docs/SPECS.md
sections 3 and 8). The logic stays in `stages/diagnose` (CLAUDE.md 3.4); this
service enforces the state machine, guards against a concurrent call for the
same run, and shapes the answer.

Session 3G-lite (Thach, 2026-09-29): the designed degraded mode - steps 1-7
only, no AI call, so `ai_findings` and `model_used` are null and the
code-written headline stands (docs/AI_PIPELINE.md sections 7.9 and 9). The
run stays `analyzed`: stages 2-4 all live in it (SPECS section 3), and which
of their files exist says how far a run went - no status, no migration.
diagnosis.json is written atomically (`stages.diagnose.assemble`), so, as
for stage 2, a concurrent second call is refused (`work.execution`) rather
than claimed, and a crash cannot strand the run.
"""

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RunStatus
from app.schemas import DiagnoseResponse
from app.services import later_outputs, run_state, stage_errors
from app.services.run_memory import RunWork
from shared.run_registry import RunNotFoundError, run_file
from shared.transactions import LineClassColumnsError
from stages.diagnose.assemble import diagnose_run
from stages.diagnose.inputs import CLEANED_FILENAME, CLEANING_REPORT_FILENAME, METRICS_FILENAME

# Only once stage 2 has run: diagnose reads metrics.json. A re-run
# overwrites diagnosis.json and removes the later stages' outputs
# (docs/CONTRACTS.md section 1).
DIAGNOSABLE_STATUSES = (RunStatus.ANALYZED,)


def diagnose(session: Session, run_id: str, *, settings: Settings, work: RunWork) -> DiagnoseResponse:
    """`analyzed` -> `analyzed`, with diagnosis.json written. A run file
    another version of the app wrote (metrics.json of another major) is
    answered by the app's handler (`stage_errors.run_file_version_handler`):
    "run the analysis again"."""
    runs_root = settings.runs_dir
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *DIAGNOSABLE_STATUSES, step="diagnose")
    _require_run_files(runs_root, run_id)

    with work.execution(run_id):
        try:
            # The forecast and the report describe the diagnosis this run
            # replaces: set aside around its rename (as stage 2's).
            diagnosis = diagnose_run(runs_root, run_id, around_write=lambda: later_outputs.set_aside(
                runs_root, run_id, after_stage=3))
        except LineClassColumnsError as error:
            # cleaned.csv's classes changed after the analysis (2E-t2): re-upload.
            raise stage_errors.analysis_failed(str(error), {"line_classes": error.problem}) from error
        except ValidationError as error:
            # Amounts stage 2 could add but stage 3's attribution multiplies
            # past a float (review 1 #1); a run file another version wrote
            # goes on to the app's handler; any other refusal is a bug.
            if not stage_errors.too_large_to_add(error):
                raise
            raise stage_errors.amounts_too_large(3) from error

    return DiagnoseResponse(run_id=run_id, status="analyzed", diagnosis=diagnosis, notices=[])


def _require_run_files(runs_root: Path, run_id: str) -> None:
    """A missing input (the retention cleanup removed the directory, or these
    files) is EXPIRED (410), not a FileNotFoundError (500)."""
    try:
        found = all(run_file(runs_root, run_id, filename).exists()
                    for filename in (CLEANED_FILENAME, CLEANING_REPORT_FILENAME, METRICS_FILENAME))
    except RunNotFoundError:
        found = False
    if not found:
        raise stage_errors.files_gone()
