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
from app.schemas import CurrencyResponse, ExecuteResponse, LineSummaryResponse, PreviewResponse
from app.services import run_state, stage_errors
from app.services.analysis import is_not_inventory, not_inventory_notice, read_schema
from app.services.run_memory import FrameCache, RetryBudgets, RunWork
from contracts import CleaningPlanContract
from contracts.cleaning import PlanSource
from contracts.currency import CurrencyQuestion
from shared.run_registry import RunNotFoundError, run_file
from stages.ingest.ai_plan import OUTPUT_FILENAME as PROPOSAL_FILENAME
from stages.ingest.cleaning import CleaningError, execute_run
from stages.ingest.currency_question import currency_question, plan_currency
from stages.ingest.line_summary import line_summary
from stages.ingest.plan_validation import InvalidPlanError, validate_final_plan
from stages.ingest.preview import preview_frame, run_proven_formats
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
        # Parsing the whole file on a cache miss is a heavy step (Thach,
        # 2026-10-02); a hit costs nothing.
        frame = frame_of_run(work, cache, settings.runs_dir, run_id)
        # `preview_frame` trusts its plan (it is for the already-checked case), so the
        # check `preview_run` makes on a plan is made here, on the cached frame.
        validate_final_plan(plan, [str(name) for name in frame.columns], for_execution=False)
        # The whole file's proven decimal marks are profile.json's: the
        # sample is read by them, never the whole column again (2E-u1).
        result = preview_frame(frame, plan, proven=run_proven_formats(settings.runs_dir, run_id))
    except InvalidPlanError as error:
        raise stage_errors.invalid_plan(error) from error
    except CleaningError as error:
        raise stage_errors.cleaning_failed(error) from error
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except ProfilingError as error:
        raise stage_errors.profiling_failed(error) from error
    return PreviewResponse(run_id=run_id, preview=result)


def ask_currency(
    session: Session,
    run_id: str,
    body: dict[str, Any],
    *,
    settings: Settings,
    cache: FrameCache,
    work: RunWork,
) -> CurrencyResponse:
    """Review's currency question for the plan as the user edited it (design
    6.2, 6.3): stage 1 reads the raw file on the plan's money column as
    execute will. Read only, the preview's rules: nothing written, no status."""
    run = run_state.load_live_run(session, run_id, runs_root=settings.runs_dir, work=work)
    run_state.require_status(run, *run_state.PLANNING_STATUSES, step="ask the file's currency")
    plan = stage_errors.parse_plan(body)
    session.commit()  # the read transaction ends here: a first load parses the whole file
    try:
        _require_raw(settings.runs_dir, run_id)
        question = currency_question_for(work, cache, settings.runs_dir, run_id, plan)
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except ProfilingError as error:
        raise stage_errors.profiling_failed(error) from error
    return CurrencyResponse(run_id=run_id, question=question)


def currency_question_for(
    work: RunWork, cache: FrameCache, runs_dir: Path, run_id: str, plan: CleaningPlanContract
) -> CurrencyQuestion:
    """The raw frame, then stage 1's reading of it in a slot of its own (it
    takes 10-16 s on a large file) - after the frame is in hand, never
    around the cache's load (Q68). Asks of one run about the same money
    columns share one reading (Q68's review)."""
    money = tuple(action.source_name for action in plan.column_actions if action.canonical_field == "unit_price")

    def read() -> CurrencyQuestion:
        frame = frame_of_run(work, cache, runs_dir, run_id)
        with work.heavy():
            return currency_question(plan_currency(frame, plan))

    return work.shared(("currency", run_id, *money), read)


def summarise_lines(
    session: Session,
    run_id: str,
    body: dict[str, Any],
    *,
    settings: Settings,
    cache: FrameCache,
    work: RunWork,
) -> LineSummaryResponse:
    """Review's whole-file view of the line taxonomy for the plan and the
    answers as they stand (2E-t3): the preview's rules - read only, nothing
    written, a plan that does not work is an error the user fixes by editing -
    on the whole file rather than a sample."""
    run = run_state.load_live_run(session, run_id, runs_root=settings.runs_dir, work=work)
    run_state.require_status(run, *run_state.PLANNING_STATUSES, step="summarise the lines")
    plan = stage_errors.parse_plan(body)
    session.commit()  # the read transaction ends here: the whole file takes seconds
    try:
        _require_raw(settings.runs_dir, run_id)
        with work.summary(run_id):
            # The frame first, then the summary in a slot of its own - never the
            # slot around the cache's load, which inverted the lock order against
            # the preview and the currency question and could hang the server
            # for good (Q68, a deploy blocker).
            frame = frame_of_run(work, cache, settings.runs_dir, run_id)
            with work.heavy():
                found = line_summary(frame, plan)
    except InvalidPlanError as error:
        raise stage_errors.invalid_plan(error) from error
    except CleaningError as error:
        raise stage_errors.cleaning_failed(error) from error
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except ProfilingError as error:
        raise stage_errors.profiling_failed(error) from error
    return LineSummaryResponse(run_id=run_id, reserved_renames=found.reserved_renames, summary=found.summary,
                               summary_unavailable_reason=found.unavailable)


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
            with work.heavy():
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
            _forget(run_id, cache, work, budgets)  # a failed run asks the AI nothing more
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
    # The run goes on to stages 2-4: its AI retry stays, shared with stage 4
    # (SPECS 11: "max 4 calls per run plus 1 shared retry"; 4C).
    _forget(run_id, cache, work, None)
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


def _forget(run_id: str, cache: FrameCache, work: RunWork, budgets: RetryBudgets | None) -> None:
    """The run is out of the interactive phase: its frame and its AI attempt
    counts are no longer needed; its AI retry only when it failed (`budgets`),
    as a run that goes on shares it with stage 4."""
    cache.evict(run_id)
    work.forget(run_id)
    if budgets is not None:
        budgets.forget(run_id)


def _require_raw(runs_root: Path, run_id: str) -> None:
    """Explicit, so that a missing upload is EXPIRED (410) and any other file-not-found
    inside a stage (a bad deployment) is not mistaken for it."""
    if not run_file(runs_root, run_id, RAW_FILENAME).exists():
        raise stage_errors.files_gone()


def frame_of_run(work: RunWork, cache: FrameCache, runs_root: Path, run_id: str) -> pd.DataFrame:
    """The run's parsed raw file - the one way every path gets it (Q68): the
    cache's per-run load lock first, the heavy slot inside it for the parse.
    Asked from inside a slot, the slot would be held while waiting for the
    load lock - the order the preview takes the other way round - so that is
    refused at once, never left to hang."""
    if work.holds_heavy():
        raise RuntimeError("the frame is loaded with the load lock first: never asked for inside a heavy step")
    return cache.get_or_load(run_id, lambda: _read_frame_heavy(work, runs_root, run_id))


def _read_frame_heavy(work: RunWork, runs_root: Path, run_id: str) -> pd.DataFrame:
    with work.heavy():
        return _read_frame(runs_root, run_id)


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
    # The answers to Review's questions are always the user's (2E-e2 review
    # cycle 2 F10): a plan changed only by them is not the AI's untouched.
    return {
        "dataset_actions": [a.model_dump(exclude=skip) for a in plan.dataset_actions],
        "column_actions": [a.model_dump(exclude=skip) for a in plan.column_actions],
        "confirmations": plan.confirmations.model_dump(),
    }
