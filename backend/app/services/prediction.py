"""Stage 4 orchestration: `POST /api/runs/{id}/predict` (docs/SPECS.md
sections 3 and 8; session 4C). The logic stays in `stages/predict`
(CLAUDE.md 3.4); this service enforces the state machine, keeps one piece of
work at a time per run, and shapes the answer.

The run stays `analyzed` (stages 2-4 all live in it; which files exist says
how far it went - 3G-lite's rule). forecast.json is written atomically, the
report's files set aside around its rename. Stage 4 asks no AI in v1 (the
report redesign's step 4, Thach's option (d)): the forecast and the
code-written suggested actions, nothing else.
"""

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import RunStatus
from app.schemas import Notice, PredictResponse
from app.services import run_state, stage_errors
from app.services.run_memory import RunWork
from shared import later_outputs
from shared.run_registry import RunNotFoundError, run_file
from stages.predict.assemble import (
    DIAGNOSIS_FILENAME,
    METRICS_FILENAME,
    DiagnosisMismatchError,
    predict_run,
)

PREDICTABLE_STATUSES = (RunStatus.ANALYZED,)


def predict(session: Session, run_id: str, *, settings: Settings, work: RunWork) -> PredictResponse:
    """`analyzed` -> `analyzed`, with forecast.json written. A run file
    another version of the app wrote is answered by the app's handler
    (`stage_errors.run_file_version_handler`): "run that stage again"."""
    runs_root = settings.runs_dir
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *PREDICTABLE_STATUSES, step="predict")
    session.commit()  # no read transaction held through the work
    with work.execution(run_id):
        # Inside: a re-analysis that finished just before cannot remove the
        # files between the check and the read (4C review #3).
        _require_run_files(runs_root, run_id)
        try:
            prediction = predict_run(runs_root, run_id,
                                     around_write=lambda: later_outputs.set_aside(runs_root, run_id, after_stage=4))
        except DiagnosisMismatchError as error:
            raise ApiError("INVALID_STATE", f"{error}.", {"reason": "diagnosis_mismatch"}) from error
        except ValidationError as error:
            # Amounts the forecast carries past a float; a run file another
            # version wrote goes on to the app's handler.
            if not stage_errors.too_large_to_add(error):
                raise
            raise stage_errors.amounts_too_large(4) from error
    return PredictResponse(run_id=run_id, status="analyzed", forecast=prediction.contract, notices=_notices())


def _notices() -> list[Notice]:
    # No AI step, so nothing to say about one: the forecast and its actions
    # stand in forecast.json (section 4 of the report words them).
    return []


def _require_run_files(runs_root: Path, run_id: str) -> None:
    """Its files gone (the retention cleanup): EXPIRED. No diagnosis.json -
    never diagnosed, or removed by a re-analysis - is the step's order, not
    an expiry: INVALID_STATE (PROJECT_PLAN 4C)."""
    try:
        metrics = run_file(runs_root, run_id, METRICS_FILENAME).exists()
        diagnosis = run_file(runs_root, run_id, DIAGNOSIS_FILENAME).exists()
    except RunNotFoundError:
        metrics = diagnosis = False
    if not metrics:
        raise stage_errors.files_gone()
    if not diagnosis:
        raise ApiError("INVALID_STATE", "Run the diagnosis first: this run has no diagnosis.json.",
                       {"status": RunStatus.ANALYZED.value, "missing": DIAGNOSIS_FILENAME})
