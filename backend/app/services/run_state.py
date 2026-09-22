"""The run state machine (SPECS section 3), enforced on the server.

Every move is one conditional UPDATE ("set X where the status is still Y"), never a
read followed by a write, so two requests for one run cannot both pass the same
check. The row lock a database takes for the UPDATE is the whole mutual exclusion:
PostgreSQL re-evaluates the WHERE of a waiting UPDATE after the first commits.
"""

import logging
import uuid
from pathlib import Path
from typing import Any, cast

from sqlalchemy import CursorResult, update
from sqlalchemy.orm import Session

from app.errors import ApiError, ErrorCode
from app.models import Run, RunStatus
from app.services.run_memory import RunWork
from stages.ingest.cleaning import REPORT_FILENAME

logger = logging.getLogger(__name__)

# The statuses a plan may be previewed or executed from. `profiled` is here on
# purpose: with the AI unavailable, or a file that is not inventory data, the run
# never reaches `planned` and the user builds the plan by hand (SPECS section 10).
PLANNING_STATUSES = (RunStatus.PROFILED, RunStatus.PLANNED)

_CLAIM_ATTEMPTS = 3  # a run can move twice under one request (profiled -> planned -> cleaning)
_GONE = "The run has expired and its files are deleted. Upload the file again."


def load_run(session: Session, run_id: str) -> Run:
    """The run row, or NOT_FOUND / EXPIRED.

    Looked up before the file system is touched, so an id that is not a UUID (or
    that climbs a path) can never reach `runs/`: only an id in the table does. An
    id that is not in the canonical form the registry writes is refused before the
    database is asked: PostgreSQL rejects some strings (a NUL) with an error, which
    would be a 500 instead of the 404 SPECS section 10 gives an id that names no run.
    """
    run = session.get(Run, run_id) if _is_canonical_uuid(run_id) else None
    if run is None:
        raise ApiError("NOT_FOUND", "There is no run with this id.")
    if run.status is RunStatus.EXPIRED:
        raise ApiError("EXPIRED", _GONE)
    return run


def require_status(run: Run, *allowed: RunStatus, step: str) -> None:
    """INVALID_STATE (409) unless the run is in one of `allowed`."""
    if run.status in allowed:
        return
    details: dict[str, Any] = {
        "status": run.status.value,
        "allowed": [status.value for status in allowed],
    }
    if run.error_code is not None:
        details["error_code"] = run.error_code
    raise ApiError(
        "INVALID_STATE", f"Cannot {step}: the run is {run.status.value}.", details)


def advance(
    session: Session,
    run_id: str,
    to: RunStatus,
    *,
    only_from: tuple[RunStatus, ...],
) -> bool:
    """Move the run to `to` if its status is (still) one of `only_from`. False
    means another request moved it first, and nothing was changed."""
    return _transition(session, run_id, to, only_from, error_code=None)


def fail(
    session: Session,
    run_id: str,
    code: ErrorCode,
    *,
    only_from: tuple[RunStatus, ...],
) -> bool:
    """The run failed for a reason that will not change on a retry (SPECS section
    3, `failed(reason)`): its status and the SPECS section 10 code are stored."""
    return _transition(session, run_id, RunStatus.FAILED, only_from, error_code=code)


def claim_for_cleaning(session: Session, run_id: str) -> RunStatus:
    """Take the run for execution: `profiled` or `planned` -> `cleaning`, atomically.

    Returns the status it was taken from, for `release`. A second claim while the
    first is held finds `cleaning` and gets INVALID_STATE (409); nothing in the
    stage stops two executions of one run, which is why this exists (1F review).
    """
    run = load_run(session, run_id)
    for _ in range(_CLAIM_ATTEMPTS):
        require_status(run, *PLANNING_STATUSES, step="execute the plan")
        taken_from = run.status
        # Compare-and-swap on the status just read: if another request moved the run
        # between the read and this UPDATE, no row matches and this one must look again.
        if _transition(session, run_id, RunStatus.CLEANING, (taken_from,), error_code=None):
            return taken_from
        # The session keeps the row it read (`expire_on_commit=False`): without the
        # refresh the check above would judge the old status and misreport the loss.
        # A run that merely moved from `profiled` to `planned` is still claimable.
        session.refresh(run)
    raise ApiError("INVALID_STATE", "The run is being changed by another request. Try again.")


def recover_claim(session: Session, run_id: str, runs_root: Path) -> RunStatus | None:
    """Free a run left in `cleaning` that nothing is executing. The caller has checked
    that (`load_live_run`). A run whose report exists finished (the report is written
    last, and only one execution can succeed per run) and only lost its status update:
    `cleaned`. Any other goes to `planned`, which accepts both a preview and an
    execute, so it loses nothing whether it was claimed from `profiled` or `planned`.
    None when the run was no longer `cleaning`."""
    finished = (runs_root / run_id / REPORT_FILENAME).exists()
    target = RunStatus.CLEANED if finished else RunStatus.PLANNED
    if not _transition(session, run_id, target, (RunStatus.CLEANING,), error_code=None):
        return None
    logger.warning("Recovered run %s from an abandoned claim: now %s", run_id, target.value)
    return target


def load_live_run(session: Session, run_id: str, *, runs_root: Path, work: RunWork) -> Run:
    """`load_run`, first freeing the run if it is stuck in `cleaning`.

    The claim is work done inside this process, so a `cleaning` run that this process
    is not working on was left by a process that died, or by a request whose own
    status update failed (the database blinked): it would refuse every call for good.
    The check takes the run's execution slot, so a run that IS executing is never
    mistaken for a stuck one and its claim is never stolen. One process only (v1).
    """
    run = load_run(session, run_id)
    if run.status is RunStatus.CLEANING:
        try:
            with work.execution(run_id):
                recover_claim(session, run_id, runs_root)
        except ApiError:
            pass  # really executing right now: leave it be
        session.refresh(run)
    return run


def release(session: Session, run_id: str, back_to: RunStatus) -> None:
    """Give a claimed run back, unchanged, after an execution that changed
    nothing (the plan was invalid: the user edits it and confirms again). Never
    touches a run that is no longer `cleaning`."""
    _transition(session, run_id, back_to, (RunStatus.CLEANING,), error_code=None)


def _is_canonical_uuid(run_id: str) -> bool:
    try:
        return str(uuid.UUID(run_id)) == run_id
    except ValueError:
        return False


def _transition(
    session: Session,
    run_id: str,
    to: RunStatus,
    only_from: tuple[RunStatus, ...],
    *,
    error_code: str | None,
) -> bool:
    values: dict[str, Any] = {"status": to}
    if error_code is not None:
        values["error_code"] = error_code
    result = cast(CursorResult[Any], session.execute(
        update(Run).where(Run.id == run_id, Run.status.in_(only_from)).values(**values),
        # The Python object is refreshed by the caller when it needs the new value.
        execution_options={"synchronize_session": False},
    ))
    session.commit()
    return result.rowcount == 1
