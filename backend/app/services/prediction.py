"""Stage 4 orchestration: `POST /api/runs/{id}/predict` (docs/SPECS.md
sections 3 and 8; session 4C). The logic stays in `stages/predict`
(CLAUDE.md 3.4); this service enforces the state machine, builds the AI step
when it is switched on, keeps one piece of work at a time per run, and shapes
the answer.

The run stays `analyzed` (stages 2-4 all live in it; which files exist says
how far it went - 3G-lite's rule). forecast.json is written atomically, the
report's files set aside around its rename. The AI step is off unless
`STRATEGY_AI_ENABLED` - v1's default, as 4B stopped at its review bound
(PROJECT_PLAN 4B); on, it spends the run's one retry shared with stage 1
(SPECS 11), the AI is asked at most MAX_AI_ATTEMPTS_PER_STEP times a run -
counted only when asked, never at the forecast's expense - and an answer
already accepted is final (4C review #1, #2).
"""

from pathlib import Path

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import RunStatus
from app.schemas import Notice, PredictResponse
from app.services import run_state, stage_errors
from app.services.analysis import AiClientFactory
from app.services.run_memory import MAX_AI_ATTEMPTS_PER_STEP, RetryBudgets, RunWork
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastBlock
from contracts.metrics import MetricsContract
from shared import later_outputs
from shared.run_registry import RunNotFoundError, run_file
from stages.predict.ai_strategy import Strategy, recommend
from stages.predict.assemble import (
    DIAGNOSIS_FILENAME,
    METRICS_FILENAME,
    SWITCHED_OFF,
    DiagnosisMismatchError,
    Prediction,
    RecommendStep,
    Skip,
    predict_run,
)

PREDICTABLE_STATUSES = (RunStatus.ANALYZED,)
STEP = "recommend"  # the AI step's name for its attempt count
ATTEMPTS_USED = Skip("attempts_used",
                     f"no recommendation: the AI has already been asked {MAX_AI_ATTEMPTS_PER_STEP} times for this run")


def predict(session: Session, run_id: str, *, settings: Settings, make_client: AiClientFactory,
            budgets: RetryBudgets, work: RunWork) -> PredictResponse:
    """`analyzed` -> `analyzed`, with forecast.json written. A run file
    another version of the app wrote is answered by the app's handler
    (`stage_errors.run_file_version_handler`): "run that stage again"."""
    runs_root = settings.runs_dir
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *PREDICTABLE_STATUSES, step="predict")
    # No read transaction held through an AI call of up to a minute (as stage 1).
    session.commit()
    with work.execution(run_id):
        # Inside: a re-analysis that finished just before cannot remove the
        # files between the check and the read (4C review #3).
        _require_run_files(runs_root, run_id)
        try:
            prediction = predict_run(runs_root, run_id, recommend_step=_ai_step(settings, make_client, budgets, work,
                                                                                run_id),
                                     around_write=lambda: later_outputs.set_aside(runs_root, run_id, after_stage=4))
        except DiagnosisMismatchError as error:
            raise ApiError("INVALID_STATE", f"{error}.", {"reason": "diagnosis_mismatch"}) from error
        except ValidationError as error:
            # Amounts the forecast carries past a float; a run file another
            # version wrote goes on to the app's handler.
            if not stage_errors.too_large_to_add(error):
                raise
            raise stage_errors.amounts_too_large(4) from error
    return PredictResponse(run_id=run_id, status="analyzed", forecast=prediction.contract,
                           notices=_notices(prediction))


def _ai_step(settings: Settings, make_client: AiClientFactory, budgets: RetryBudgets, work: RunWork,
             run_id: str) -> RecommendStep | Skip:
    if not settings.strategy_ai_enabled:
        return SWITCHED_OFF
    if not work.attempts_left(run_id, STEP):
        return ATTEMPTS_USED

    def step(metrics: MetricsContract, diagnosis: DiagnosisContract, block: ForecastBlock) -> Strategy:
        work.record_attempt(run_id, STEP)  # counted only when the AI is asked
        return recommend(metrics, diagnosis, block, make_client(), settings.model_reasoning, budgets.for_run(run_id))
    return step


def _notices(prediction: Prediction) -> list[Notice]:
    if prediction.ai == "answered":
        return []
    forecast = prediction.contract.forecast
    written = ("There is too little history for a forecast." if forecast.insufficient_history
               else "The forecast is written.")
    code = "AI_UNAVAILABLE" if prediction.ai == "unavailable" else "AI_NOT_ASKED"
    return [Notice(code=code, message=f"{(prediction.sentence or '').capitalize()}. {written}",
                   details={"reason": prediction.code})]


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
