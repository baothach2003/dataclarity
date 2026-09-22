"""The two AI steps of stage 1: schema inference and the cleaning plan (SPECS
section 3, "Analyzing"). Services orchestrate: they call the stage, keep the run's
status and its shared retry budget, and shape the answer; the logic stays in
`stages/ingest` (CLAUDE.md 3.4).
"""

import threading
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.models import Run, RunStatus
from app.schemas import AnalyzeSchemaResponse, Notice, PlanResponse
from app.services import run_state, stage_errors
from app.services.run_memory import RetryBudgets, RunWork
from contracts import ProfileContract, SchemaInferenceContract
from shared.ai_client import AIClient, AIUnavailable
from shared.run_registry import RunNotFoundError, run_file
from stages.ingest.ai_plan import propose_plan_run
from stages.ingest.ai_schema import OUTPUT_FILENAME as SCHEMA_FILENAME
from stages.ingest.ai_schema import infer_schema_run
from stages.ingest.contract_files import StaleInputError
from stages.ingest.profiling import (
    PROFILE_FILENAME,
    RAW_FILENAME,
    ProfilingError,
    profile_run,
)

# SPECS section 10 / AI_PIPELINE section 9.4: below this the file is not treated as
# inventory data. 0.5 itself is still inventory.
NOT_INVENTORY_BELOW = 0.5

AiClientFactory = Callable[[], AIClient]


def default_ai_client_factory(settings: Settings) -> AiClientFactory:
    """The real client, built on first use (so the app starts, and its tests run, with
    no network) and then shared: the SDK client holds a connection pool and is safe
    to use from every request thread. Tests inject a factory over a fake instead."""
    key = settings.anthropic_api_key.get_secret_value()
    lock = threading.Lock()
    built: list[AIClient] = []

    def make() -> AIClient:
        with lock:
            if not built:
                built.append(AIClient.from_api_key(key))
            return built[0]

    return make


def analyze_schema(
    session: Session,
    run_id: str,
    *,
    settings: Settings,
    make_client: AiClientFactory,
    budgets: RetryBudgets,
    work: RunWork,
) -> AnalyzeSchemaResponse:
    """`uploaded` -> `profiled` (profiling happens here: SPECS section 3 shows
    "Analyzing" as one step), then schema inference, once. The run stays `profiled`
    whatever the AI does, so a call that got no answer can simply be repeated (a few
    times: `MAX_AI_ATTEMPTS_PER_STEP`), and an answer already given is final."""
    runs_root = settings.runs_dir
    run = run_state.load_live_run(session, run_id, runs_root=runs_root, work=work)
    run_state.require_status(
        run, RunStatus.UPLOADED, RunStatus.PROFILED, step="analyze the schema")
    try:
        _require_raw(runs_root, run_id)
        with work.ai_step(run_id, "analyze the schema"):
            if run_file(runs_root, run_id, SCHEMA_FILENAME).exists():
                raise ApiError(
                    "INVALID_STATE",
                    "The schema has already been analyzed for this run. Go on to the plan.",
                    {"status": run.status.value, "existing": SCHEMA_FILENAME},
                )
            # A read transaction stays open until the session commits, and a parse of a
            # 50 MB file or a call of up to a minute must not hold a connection.
            session.commit()
            if run.status is RunStatus.UPLOADED or not _profile_exists(runs_root, run_id):
                _profile(session, run, runs_root)
            session.commit()
            try:
                schema: SchemaInferenceContract | None = infer_schema_run(
                    runs_root, run_id, make_client(), settings.model_reasoning,
                    budgets.for_run(run_id))
                notices = _notices(None, schema)
            except AIUnavailable as unavailable:
                schema = None
                notices = [_ai_unavailable(unavailable, "analyze this file")]
            _still_in_the_ai_phase(session, run, RunStatus.PROFILED, budgets, "analyze the schema")
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except StaleInputError as error:
        raise ApiError("INVALID_STATE", str(error)) from error
    return AnalyzeSchemaResponse(
        run_id=run_id, status="profiled", schema_inference=schema, notices=notices)


def propose_plan(
    session: Session,
    run_id: str,
    *,
    settings: Settings,
    make_client: AiClientFactory,
    budgets: RetryBudgets,
    work: RunWork,
) -> PlanResponse:
    """`profiled` -> `planned`, when the AI proposes a plan. Without one (the AI is
    unavailable) the run stays `profiled` and the user builds the plan by hand."""
    runs_root = settings.runs_dir
    run = run_state.load_live_run(session, run_id, runs_root=runs_root, work=work)
    run_state.require_status(run, RunStatus.PROFILED, step="propose a plan")
    try:
        for missing in (PROFILE_FILENAME, SCHEMA_FILENAME):
            if not run_file(runs_root, run_id, missing).exists():
                raise ApiError(
                    "INVALID_STATE",
                    f"Cannot propose a plan: {missing} does not exist yet. "
                    "Analyze the schema first.",
                    {"status": run.status.value, "missing": missing},
                )
        with work.ai_step(run_id, "propose a plan"):
            schema = read_schema(runs_root, run_id)
            session.commit()  # see analyze_schema
            try:
                plan = propose_plan_run(
                    runs_root, run_id, make_client(), settings.model_reasoning,
                    budgets.for_run(run_id))
            except AIUnavailable as unavailable:
                _still_in_the_ai_phase(session, run, RunStatus.PROFILED, budgets, "propose a plan")
                return PlanResponse(
                    run_id=run_id, status="profiled", plan=None,
                    notices=_notices(_ai_unavailable(unavailable, "propose a plan"), schema))
            if not run_state.advance(
                session, run_id, RunStatus.PLANNED, only_from=(RunStatus.PROFILED,)
            ):
                # Not moved: the run left `profiled` while the AI was working.
                _still_in_the_ai_phase(session, run, RunStatus.PROFILED, budgets, "propose a plan")
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except StaleInputError as error:
        raise ApiError("INVALID_STATE", str(error)) from error
    return PlanResponse(
        run_id=run_id, status="planned", plan=plan, notices=_notices(None, schema))


def get_profile(session: Session, run_id: str, *, settings: Settings) -> ProfileContract:
    """profile.json for the run (SPECS section 8: GET /api/runs/{id}/profile). Read-only:
    no work claim, since nothing here can race a step that changes the run's status."""
    run = run_state.load_run(session, run_id)
    run_state.require_status(
        run,
        RunStatus.PROFILED, RunStatus.PLANNED, RunStatus.CLEANING,
        RunStatus.CLEANED, RunStatus.ANALYZED, RunStatus.IMPORTED,
        step="load the profile",
    )
    path = run_file(settings.runs_dir, run_id, PROFILE_FILENAME)
    if not path.exists():
        raise stage_errors.files_gone()
    return ProfileContract.model_validate_json(path.read_text(encoding="utf-8"))


def read_schema(runs_root: Path, run_id: str) -> SchemaInferenceContract | None:
    """schema_inference.json as a contract, or None when the step has not run (or
    ended without an answer)."""
    path = run_file(runs_root, run_id, SCHEMA_FILENAME)
    if not path.exists():
        return None
    return SchemaInferenceContract.model_validate_json(path.read_text(encoding="utf-8"))


def is_not_inventory(schema: SchemaInferenceContract | None) -> bool:
    return schema is not None and schema.domain_confidence < NOT_INVENTORY_BELOW


def not_inventory_notice(schema: SchemaInferenceContract | None) -> Notice | None:
    if schema is None or not is_not_inventory(schema):
        return None
    return Notice(
        code="NOT_INVENTORY",
        message=(
            "This file does not look like inventory or sales data. You can still clean it "
            "and download the result; importing it and the analysis stages are not available."
        ),
        details={
            "domain_confidence": schema.domain_confidence,
            "domain_reasoning": schema.domain_reasoning,
        },
    )


def _notices(unavailable: Notice | None, schema: SchemaInferenceContract | None) -> list[Notice]:
    return [n for n in (unavailable, not_inventory_notice(schema)) if n is not None]


def _ai_unavailable(error: AIUnavailable, doing: str) -> Notice:
    return Notice(
        code="AI_UNAVAILABLE",
        message=(
            f"The AI assistant could not {doing}. Profiling is done: try again, "
            "or build the cleaning plan by hand."
        ),
        details={"reason": error.reason},
    )


def _require_raw(runs_root: Path, run_id: str) -> None:
    """The run's row exists; its file must too. Checked here, not left to a stage's
    FileNotFoundError, which could just as well be a missing prompt template (a bad
    deployment, not a run that expired) with a server path in its message."""
    if not run_file(runs_root, run_id, RAW_FILENAME).exists():
        raise stage_errors.files_gone()


def _profile_exists(runs_root: Path, run_id: str) -> bool:
    return run_file(runs_root, run_id, PROFILE_FILENAME).exists()


def _profile(session: Session, run: Run, runs_root: Path) -> None:
    try:
        profile_run(runs_root, run.id)
    except ProfilingError as error:
        # The file itself is the problem, so a retry changes nothing: the run
        # fails, and the user uploads again.
        refused = stage_errors.profiling_failed(error)
        run_state.fail(
            session, run.id, refused.code, only_from=(RunStatus.UPLOADED, RunStatus.PROFILED))
        raise refused from error
    run_state.advance(session, run.id, RunStatus.PROFILED, only_from=(RunStatus.UPLOADED,))
    # Whether that moved the run or it was already `profiled`, what counts is where it
    # is now: anything further along is out of order.
    session.refresh(run)
    run_state.require_status(run, RunStatus.PROFILED, step="analyze the schema")


def _still_in_the_ai_phase(
    session: Session, run: Run, expected: RunStatus, budgets: RetryBudgets, step: str
) -> None:
    """A step of up to a minute can end after the run was executed or failed by another
    request. Its answer must not claim a state the run no longer has."""
    session.refresh(run)
    if run.status is expected:
        return
    if run.status not in (RunStatus.UPLOADED, RunStatus.PROFILED, RunStatus.PLANNED):
        budgets.forget(run.id)
    run_state.require_status(run, expected, step=step)
