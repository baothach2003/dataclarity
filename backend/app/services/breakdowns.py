"""Review's sales breakdowns (the dashboard, Thach's D4; docs/DASHBOARD_DESIGN.md
section 5): stage 1's eligible columns for the plan as the user edited it, and
the AI's choice among them, asked once per run. Services orchestrate; the
rules are stage 1's (`stages/ingest/breakdowns.py`, CLAUDE.md 3.4). Since
Thach's Q3-Q5 eligibility reads the plan's lines: the raw frame through the
cache, the measure in a heavy slot of its own, the AI asked after the slot is
released (as the currency question; Q68's lock order)."""

import hashlib
import json
import threading
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import Settings
from app.errors import ApiError
from app.schemas import BreakdownResponse
from app.services import run_state, stage_errors
from app.services.analysis import AiClientFactory, is_not_inventory, read_schema
from app.services.plan_execution import frame_of_run, require_raw
from app.services.run_memory import FrameCache, RunWork
from contracts.breakdowns import BreakdownQuestion, BreakdownSuggestion, EligibleColumn
from contracts.cleaning import CleaningPlanContract
from shared.run_registry import RunNotFoundError, run_file
from stages.ingest.breakdown_review import measure_lines
from stages.ingest.breakdowns import (
    NOT_ANALYSED,
    SCHEMA_VERSION,
    breakdown_question_run,
    run_suggestion,
    suggest_breakdowns,
)
from stages.ingest.profiling import PROFILE_FILENAME, ProfilingError

STEP = "suggest sales breakdowns"
# The plan each run was last asked about (the doubt review's R2): a measure waiting for the heavy slot that
# is no longer the latest edit steps aside, so the slot serves the plan as it stands, never a queue of edits.
_LATEST: dict[str, str] = {}
_LATEST_LOCK = threading.Lock()
SUPERSEDED = "A later edit of the plan is being checked; this one was skipped."


def _plan_key(plan: CleaningPlanContract) -> str:
    """What eligibility reads of the plan: all of it but the user's own
    choice - its steps and answers decide the lines measured (Q3-Q5)."""
    return json.dumps(plan.model_dump(mode="json", exclude={"breakdowns", "generated_at"}), sort_keys=True)


def ask_breakdowns(session: Session, run_id: str, body: dict[str, Any], *, settings: Settings,
                   make_client: AiClientFactory, cache: FrameCache, work: RunWork) -> BreakdownResponse:
    """Read only for the run's state, as the currency question: the one thing
    written is the AI's answer, once per run (breakdown_suggestion.json)."""
    runs_root = settings.runs_dir
    run = run_state.load_live_run(session, run_id, runs_root=runs_root, work=work)
    run_state.require_status(run, *run_state.PLANNING_STATUSES, step=STEP)
    plan = stage_errors.parse_plan(body)
    session.commit()  # no connection held while the AI answers
    try:
        if not run_file(runs_root, run_id, PROFILE_FILENAME).exists():
            raise stage_errors.files_gone()
        if is_not_inventory(read_schema(runs_root, run_id)):
            # Generic cleaning analyses nothing: no column is offered, no AI asked.
            return BreakdownResponse(run_id=run_id, question=BreakdownQuestion(
                eligible=[], suggested=[], status="none_eligible", message=NOT_ANALYSED))

        def ask(eligible: list[EligibleColumn]) -> BreakdownSuggestion:
            if not eligible:
                return suggest_breakdowns(make_client, settings.model_reasoning, eligible)
            # Counted, never exclusive: the ask is not in the user's path to Confirm or to the plan's
            # "try again" (design 5.2; the step 4 review #2) - execute does not read its file.
            if not work.attempts_left(run_id, STEP):
                return BreakdownSuggestion(schema_version=SCHEMA_VERSION, generated_at=datetime.now(UTC),
                                           eligible=[c.column for c in eligible], chosen=[],
                                           status="ai_unavailable", model_used=None)
            work.record_attempt(run_id, STEP)
            return suggest_breakdowns(make_client, settings.model_reasoning, eligible)

        def suggestion_for(eligible: list[EligibleColumn]) -> BreakdownSuggestion:
            if not eligible:
                # Nothing to ask and nothing stored: no flight, so no waiter inherits this empty answer
                # (the scoped review's O2).
                return suggest_breakdowns(make_client, settings.model_reasoning, eligible)
            # One reading-or-asking per run at a time, whatever the columns: an ask that arrives while the
            # AI answers waits for that answer and its stored file - never a second call (review #5).
            return work.shared(("breakdown suggestion", run_id),
                               lambda: run_suggestion(runs_root, run_id, eligible, ask))

        key = _plan_key(plan)
        latest = hashlib.sha256(key.encode("utf-8")).hexdigest()  # a short mark per run, not the plan
        with _LATEST_LOCK:
            _LATEST[run_id] = latest

        def read() -> BreakdownQuestion:
            require_raw(runs_root, run_id)
            frame = frame_of_run(work, cache, runs_root, run_id)
            with work.heavy():
                with _LATEST_LOCK:
                    superseded = _LATEST.get(run_id) != latest
                if superseded:
                    raise ApiError("INVALID_STATE", SUPERSEDED)
                measured = measure_lines(frame, plan)
            # The slot released before the AI is asked: an answer of seconds never holds it.
            return breakdown_question_run(runs_root, run_id, plan, measured, suggestion_for)

        # Asks of one run about the same plan share one answer (a StrictMode double ask, two tabs).
        question = work.shared(("breakdowns", run_id, key), read)
    except RunNotFoundError:
        raise stage_errors.files_gone() from None
    except ProfilingError as error:
        raise stage_errors.profiling_failed(error) from error
    return BreakdownResponse(run_id=run_id, question=question)
