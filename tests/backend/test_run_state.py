"""The run state machine (SPECS section 3) and the claim (PROJECT_PLAN 1G)."""

import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Base, Run, RunStatus
from app.services import run_state

RUN_ID = "11111111-1111-4111-8111-111111111111"
LETTERS_ID = "abcdefab-abcd-4bcd-8bcd-abcdefabcdef"  # hex letters, so upper-casing changes it
NOW = datetime(2026, 9, 22, 9, 0, tzinfo=UTC)


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    # A file, so every thread's session gets its own real connection: the claim
    # is only proved by connections that can race, not by one shared connection.
    engine = create_engine(f"sqlite:///{tmp_path / 'state.db'}")
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine, expire_on_commit=False) as session:
        yield session


def add_run(session: Session, status: RunStatus, run_id: str = RUN_ID) -> None:
    session.add(Run(
        id=run_id, filename="sales.csv", size_bytes=10, status=status,
        created_at=NOW, expires_at=NOW + timedelta(hours=24),
    ))
    session.commit()


def status_of(engine: Engine, run_id: str = RUN_ID) -> tuple[RunStatus, str | None]:
    with Session(engine) as fresh:
        run = fresh.scalars(select(Run).where(Run.id == run_id)).one()
        return run.status, run.error_code


def error_of(call: object) -> ApiError:
    with pytest.raises(ApiError) as caught:
        call()  # type: ignore[operator]
    return caught.value


# --- finding the run -----------------------------------------------------------


def test_load_run_returns_the_row(session: Session) -> None:
    add_run(session, RunStatus.PROFILED)

    assert run_state.load_run(session, RUN_ID).status is RunStatus.PROFILED


@pytest.mark.parametrize("run_id", [
    "22222222-2222-4222-8222-222222222222",  # well formed, no such run
    "not-a-uuid",
    "..",
    "",
])
def test_an_id_that_names_no_run_is_not_found(session: Session, run_id: str) -> None:
    add_run(session, RunStatus.PROFILED)

    error = error_of(lambda: run_state.load_run(session, run_id))

    assert error.code == "NOT_FOUND"


def test_an_expired_run_is_gone_with_a_reupload_hint(session: Session) -> None:
    add_run(session, RunStatus.EXPIRED)

    error = error_of(lambda: run_state.load_run(session, RUN_ID))

    assert error.code == "EXPIRED"
    assert "upload" in error.message.lower()


# --- the guard -----------------------------------------------------------------


def test_require_status_accepts_a_listed_status(session: Session) -> None:
    add_run(session, RunStatus.PLANNED)
    run = run_state.load_run(session, RUN_ID)

    run_state.require_status(run, RunStatus.PROFILED, RunStatus.PLANNED, step="preview")


@pytest.mark.parametrize("status", [
    RunStatus.UPLOADED, RunStatus.CLEANING, RunStatus.CLEANED, RunStatus.ANALYZED,
    RunStatus.IMPORTED, RunStatus.FAILED,
])
def test_require_status_refuses_any_other_status_with_409(
    session: Session, status: RunStatus
) -> None:
    add_run(session, status)
    run = run_state.load_run(session, RUN_ID)

    error = error_of(lambda: run_state.require_status(
        run, RunStatus.PROFILED, RunStatus.PLANNED, step="preview"))

    assert error.code == "INVALID_STATE"
    assert error.details == {"status": status.value, "allowed": ["profiled", "planned"]}
    assert "preview" in error.message


def test_a_failed_run_reports_why_it_failed(session: Session) -> None:
    add_run(session, RunStatus.FAILED)
    session.execute(Run.__table__.update().values(error_code="CLEANING_FAILED"))
    session.commit()
    run = run_state.load_run(session, RUN_ID)

    error = error_of(lambda: run_state.require_status(run, RunStatus.PLANNED, step="execute"))

    assert error.details == {
        "status": "failed", "allowed": ["planned"], "error_code": "CLEANING_FAILED"}


# --- moving between states -----------------------------------------------------


def test_advance_moves_a_run_that_is_in_a_listed_status(session: Session, engine: Engine) -> None:
    add_run(session, RunStatus.UPLOADED)

    moved = run_state.advance(
        session, RUN_ID, RunStatus.PROFILED, only_from=(RunStatus.UPLOADED,))

    assert moved is True
    assert status_of(engine) == (RunStatus.PROFILED, None)


def test_advance_leaves_a_run_in_another_status_alone(session: Session, engine: Engine) -> None:
    add_run(session, RunStatus.CLEANED)

    moved = run_state.advance(
        session, RUN_ID, RunStatus.PROFILED, only_from=(RunStatus.UPLOADED,))

    assert moved is False
    assert status_of(engine) == (RunStatus.CLEANED, None)


def test_fail_records_the_code_of_the_failure(session: Session, engine: Engine) -> None:
    add_run(session, RunStatus.CLEANING)

    run_state.fail(session, RUN_ID, "CLEANING_FAILED", only_from=(RunStatus.CLEANING,))

    assert status_of(engine) == (RunStatus.FAILED, "CLEANING_FAILED")


# --- the claim -----------------------------------------------------------------


@pytest.mark.parametrize("status", [RunStatus.PROFILED, RunStatus.PLANNED])
def test_claim_returns_the_status_it_took_the_run_from(
    session: Session, engine: Engine, status: RunStatus
) -> None:
    add_run(session, status)

    previous = run_state.claim_for_cleaning(session, RUN_ID)

    assert previous is status
    assert status_of(engine) == (RunStatus.CLEANING, None)


@pytest.mark.parametrize("status", [
    RunStatus.UPLOADED, RunStatus.CLEANING, RunStatus.CLEANED, RunStatus.ANALYZED,
    RunStatus.IMPORTED, RunStatus.FAILED, RunStatus.EXPIRED,
])
def test_claim_is_refused_from_every_other_status(
    session: Session, engine: Engine, status: RunStatus
) -> None:
    add_run(session, status)

    error = error_of(lambda: run_state.claim_for_cleaning(session, RUN_ID))

    # EXPIRED reads as gone (410), every other status as out of order (409).
    assert error.code == ("EXPIRED" if status is RunStatus.EXPIRED else "INVALID_STATE")
    assert status_of(engine)[0] is status


def test_a_second_claim_is_refused_while_the_first_is_held(session: Session) -> None:
    add_run(session, RunStatus.PLANNED)
    run_state.claim_for_cleaning(session, RUN_ID)

    error = error_of(lambda: run_state.claim_for_cleaning(session, RUN_ID))

    assert error.code == "INVALID_STATE"
    assert error.details is not None and error.details["status"] == "cleaning"


def test_release_puts_a_claimed_run_back_where_it_was(session: Session, engine: Engine) -> None:
    add_run(session, RunStatus.PLANNED)
    run_state.claim_for_cleaning(session, RUN_ID)

    run_state.release(session, RUN_ID, RunStatus.PLANNED)

    assert status_of(engine) == (RunStatus.PLANNED, None)
    # ...and the run can be claimed again, which is the point of releasing it.
    assert run_state.claim_for_cleaning(session, RUN_ID) is RunStatus.PLANNED


def test_release_never_touches_a_run_that_is_no_longer_claimed(
    session: Session, engine: Engine
) -> None:
    add_run(session, RunStatus.CLEANED)

    run_state.release(session, RUN_ID, RunStatus.PLANNED)

    assert status_of(engine) == (RunStatus.CLEANED, None)


@pytest.mark.parametrize("attempt", range(10))
def test_of_many_simultaneous_claims_exactly_one_wins(
    engine: Engine, attempt: int
) -> None:
    # 1F's review reproduced two executes of one run interleaving their file
    # renames. The claim is the fix, so it is tested with real connections racing
    # from a common start, not with calls one after the other.
    with Session(engine) as setup:
        add_run(setup, RunStatus.PLANNED)
    threads = 8
    start = threading.Barrier(threads)
    outcomes: list[str] = []
    lock = threading.Lock()

    def claim() -> None:
        with Session(engine, expire_on_commit=False) as own:
            start.wait()
            try:
                run_state.claim_for_cleaning(own, RUN_ID)
                result = "won"
            except ApiError as refused:
                result = refused.code
        with lock:
            outcomes.append(result)

    workers = [threading.Thread(target=claim) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert sorted(outcomes) == ["INVALID_STATE"] * (threads - 1) + ["won"]
    assert status_of(engine)[0] is RunStatus.CLEANING
