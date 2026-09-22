"""Preview and execute the user's plan (SPECS sections 4.2, 5 and 8).

The plan is the user's, not the AI's: it is validated here as a contract, then again
by the stage against the real file, and what runs is exactly what was submitted
(CLAUDE.md 3.3). The backend adds three things the stage cannot know: which runs may
be previewed or executed (the state machine), the parsed frame kept between previews,
and the claim that stops two executions of one run.
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RunStatus
from app.schemas import ExecuteResponse, PreviewResponse
from app.services import run_state, stage_errors
from app.services.analysis import is_not_inventory, not_inventory_notice, read_schema
from app.services.run_memory import FrameCache, RetryBudgets, RunWork
from contracts import CleaningPlanContract
from contracts.cleaning import PlanSource
from shared.run_registry import RunNotFoundError, run_file
from stages.ingest.ai_plan import OUTPUT_FILENAME as PROPOSAL_FILENAME
from stages.ingest.cleaning import CleaningError, execute_run
from stages.ingest.plan_validation import InvalidPlanError, validate_final_plan
from stages.ingest.preview import preview_frame
from stages.ingest.profiling import RAW_FILENAME, ProfilingError, read_csv_text

logger = logging.getLogger(__name__)


def preview_plan(
    session: Session,
    run_id: str,
    body: dict[str, Any],
    *,
    settings: Settings,
    cache: FrameCache,
    work: RunWork,
) -> PreviewResponse:
    """The sample before and after the plan, for the review screen. Changes nothing:
    no file, no status. The run is only read, and a plan that does not work (illegal,
    or failing on this data) is an error the user fixes by editing, not a failed run."""
    run = run_state.load_live_run(session, run_id, runs_root=settings.runs_dir, work=work)
    run_state.require_status(run, *run_state.PLANNING_STATUSES, step="preview the plan")
    plan = stage_errors.parse_plan(body)
    session.commit()  # the read transaction ends here: a preview can take seconds
    try:
        _require_raw(settings.runs_dir, run_id)
        frame = cache.get_or_load(run_id, lambda: _read_frame(settings.runs_dir, run_id))
        # `preview_frame` trusts its plan (it is for the already-checked case), so the
        # check `preview_run` makes on a plan is made here, on the cached frame.
        validate_final_plan(plan, [str(name) for name in frame.columns], for_execution=False)
        result = preview_frame(frame, plan)
    except InvalidPlanError as error:
        raise stage_errors.invalid_plan(error) from error
    except CleaningError as error:
        raise stage_errors.cleaning_failed(error) from error
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except ProfilingError as error:
        raise stage_errors.profiling_failed(error) from error
    return PreviewResponse(run_id=run_id, preview=result)


def execute_plan(
    session: Session,
    run_id: str,
    body: dict[str, Any],
    *,
    settings: Settings,
    cache: FrameCache,
    budgets: RetryBudgets,
    work: RunWork,
) -> ExecuteResponse:
    """Run the plan on the whole file: `profiled` or `planned` -> `cleaning` (the
    claim) -> `cleaned`.

    What happens to the run when it does not work out:
    * the plan is invalid (INVALID_PLAN): the claim is released, the run is as it was,
      and the user edits the plan and confirms again;
    * the plan is valid but fails on this data (CLEANING_FAILED): the run is `failed`
      (decided by Thach in 1F), nothing was written;
    * anything else (a full disk, memory, a bug): the claim is released so the user can
      retry, and the error is a 500.
    Should the write of that final status itself fail, or the process die while the
    claim is held, the run is left in `cleaning` and freed by the next call that
    reaches it (`run_state.load_live_run`): the state is recovered, not stranded.
    """
    runs_root = settings.runs_dir
    run = run_state.load_live_run(session, run_id, runs_root=runs_root, work=work)
    run_state.require_status(run, *run_state.PLANNING_STATUSES, step="execute the plan")
    # Before the claim: a body that is no plan at all, or a run with no file, never takes it.
    plan = stage_errors.parse_plan(body)
    try:
        _require_raw(runs_root, run_id)
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    # Registered BEFORE the claim and left AFTER the settling below: while it is, the
    # run's `cleaning` status is known to be a live execution and never recovered.
    with work.execution(run_id):
        taken_from = run_state.claim_for_cleaning(session, run_id)
        try:
            schema = read_schema(runs_root, run_id)
            plan = plan.model_copy(update={"source": _source_of(plan, runs_root, run_id)})
            report = execute_run(
                runs_root, run_id, plan,
                # Generic cleaning of a file that is not inventory data has nothing to map.
                require_required_fields=not is_not_inventory(schema),
            )
        except InvalidPlanError as error:
            _settle(session, run_id, "release the claim",
                    lambda: run_state.release(session, run_id, taken_from))
            raise stage_errors.invalid_plan(error) from error
        except (CleaningError, ProfilingError) as error:
            refused = (
                stage_errors.cleaning_failed(error) if isinstance(error, CleaningError)
                else stage_errors.profiling_failed(error)
            )
            _settle(session, run_id, "fail the run", lambda: run_state.fail(
                session, run_id, refused.code, only_from=(RunStatus.CLEANING,)))
            _forget(run_id, cache, budgets, work)
            raise refused from error
        except BaseException:
            # A full disk, memory, a bug, or a client that disconnected mid-request:
            # nothing was written, and the claim must not outlive the request.
            _settle(session, run_id, "release the claim",
                    lambda: run_state.release(session, run_id, taken_from))
            raise
        # The files are complete and durable; if this status write is lost the run is
        # freed as `cleaned` by its next visit (the report exists), so it is not fatal.
        _settle(session, run_id, "mark the run cleaned", lambda: run_state.advance(
            session, run_id, RunStatus.CLEANED, only_from=(RunStatus.CLEANING,)))
    _forget(run_id, cache, budgets, work)
    notice = not_inventory_notice(schema)
    return ExecuteResponse(
        run_id=run_id, status="cleaned", report=report, notices=[notice] if notice else [])


def _settle(session: Session, run_id: str, what: str, write: Callable[[], object]) -> None:
    """Write the run's final status, trying twice. Never raises: this runs while the
    real outcome (the answer, or the error being handled) is waiting, and a database
    failure here must not replace it. A failure is logged and the run stays
    `cleaning`, for `load_live_run` to free."""
    for attempt in (1, 2):
        try:
            write()
            return
        except Exception:
            session.rollback()
            logger.exception("Could not %s for run %s (attempt %d of 2)", what, run_id, attempt)


def _forget(run_id: str, cache: FrameCache, budgets: RetryBudgets, work: RunWork) -> None:
    """The run is out of the interactive phase: its frame, its AI retry and its AI
    attempt counts are no longer needed."""
    cache.evict(run_id)
    budgets.forget(run_id)
    work.forget(run_id)


def _require_raw(runs_root: Path, run_id: str) -> None:
    """Explicit, so that a missing upload is EXPIRED (410) and any other file-not-found
    inside a stage (a bad deployment) is not mistaken for it."""
    if not run_file(runs_root, run_id, RAW_FILENAME).exists():
        raise stage_errors.files_gone()


def _read_frame(runs_root: Path, run_id: str) -> pd.DataFrame:
    return read_csv_text(run_file(runs_root, run_id, RAW_FILENAME).read_bytes()).frame


def _source_of(plan: CleaningPlanContract, runs_root: Path, run_id: str) -> PlanSource:
    """`ai` when the submitted plan is the AI's proposal untouched, `user_edited`
    when there is a proposal and the plan differs from it, `manual` when there is no
    proposal (the AI was unavailable). The `source` the client sent is not believed:
    it is what CONTRACTS section 4 relies on to say who decided. The per-action
    `edited_by_user` flags are the review screen's own bookkeeping and are stored as sent."""
    path = run_file(runs_root, run_id, PROPOSAL_FILENAME)
    if not path.exists():
        return "manual"
    proposed = CleaningPlanContract.model_validate_json(path.read_text(encoding="utf-8"))
    return "ai" if _decisions(plan) == _decisions(proposed) else "user_edited"


def _decisions(plan: CleaningPlanContract) -> dict[str, Any]:
    """What the plan decides, without the bookkeeping flag a client may set freely."""
    skip = {"edited_by_user"}
    return {
        "dataset_actions": [a.model_dump(exclude=skip) for a in plan.dataset_actions],
        "column_actions": [a.model_dump(exclude=skip) for a in plan.column_actions],
    }
