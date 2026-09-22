"""What the 1G doubt-review found in the run state machine: an id that cannot
name a run, a claim racing another status change, and a claim nothing will ever
release."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from app.errors import ApiError
from app.models import Base, Run, RunStatus
from app.services import run_state
from app.services.run_memory import RunWork

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


# --- ids that can never name a run (review M3) ------------------------------------------


class ExplodingSession:
    """A session that fails if it is used: the id check must come first."""

    def get(self, *_: object, **__: object) -> object:
        raise AssertionError("the database was asked about an id that cannot be a run id")


@pytest.mark.parametrize("run_id", [
    "abc\x00def",  # PostgreSQL refuses a NUL in a string: it was a 500 there
    LETTERS_ID.upper(),  # a UUID, but not the canonical form the registry writes
    LETTERS_ID.replace("-", ""),
    RUN_ID + " ",
    "x" * 5000,
    "../" + RUN_ID,
])
def test_an_id_that_is_not_a_canonical_uuid_is_not_found_without_asking_the_database(
    run_id: str,
) -> None:
    error = error_of(lambda: run_state.load_run(ExplodingSession(), run_id))  # type: ignore[arg-type]

    assert error.code == "NOT_FOUND"


# --- a claim whose status moved between the read and the swap (review M4) ---------------


def test_a_claim_survives_the_run_moving_from_profiled_to_planned_under_it(
    session: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    # `plan` finishes between execute's read and its UPDATE. The run is still
    # claimable; refusing it as "claimed by another request" would be a false 409.
    add_run(session, RunStatus.PROFILED)
    real_load = run_state.load_run

    def load_then_move(s: Session, run_id: str) -> Run:
        run = real_load(s, run_id)
        with Session(engine) as other:
            run_state.advance(other, run_id, RunStatus.PLANNED, only_from=(RunStatus.PROFILED,))
        monkeypatch.setattr(run_state, "load_run", real_load)  # only the first read is stale
        return run

    monkeypatch.setattr(run_state, "load_run", load_then_move)

    previous = run_state.claim_for_cleaning(session, RUN_ID)

    assert previous is RunStatus.PLANNED  # what the run really was when it was taken
    assert status_of(engine) == (RunStatus.CLEANING, None)


def test_a_claim_that_loses_to_another_claim_says_the_run_is_cleaning(
    session: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    add_run(session, RunStatus.PLANNED)
    real_load = run_state.load_run

    def load_then_claim(s: Session, run_id: str) -> Run:
        monkeypatch.setattr(run_state, "load_run", real_load)  # the inner claim reads for real
        run = real_load(s, run_id)
        with Session(engine) as other:
            run_state.claim_for_cleaning(other, run_id)
        return run

    monkeypatch.setattr(run_state, "load_run", load_then_claim)

    error = error_of(lambda: run_state.claim_for_cleaning(session, RUN_ID))

    assert error.code == "INVALID_STATE"
    assert error.details is not None and error.details["status"] == "cleaning"


# --- claims nobody will ever release (review H2) ------------------------------------------


def make_run_dir(root: Path, run_id: str, files: tuple[str, ...]) -> None:
    (root / run_id).mkdir(parents=True)
    for name in files:
        (root / run_id / name).write_text("x", encoding="utf-8")


def test_an_unfinished_claim_goes_back_to_planned(
    session: Session, engine: Engine, tmp_path: Path
) -> None:
    add_run(session, RunStatus.CLEANING)
    make_run_dir(tmp_path, RUN_ID, ("raw.csv", "profile.json"))

    recovered = run_state.recover_claim(session, RUN_ID, tmp_path)

    assert recovered is RunStatus.PLANNED
    assert status_of(engine) == (RunStatus.PLANNED, None)


def test_a_claim_whose_report_exists_finished_and_is_cleaned(
    session: Session, engine: Engine, tmp_path: Path
) -> None:
    # The report is written last: its presence means the execution completed and
    # only the status update was lost.
    add_run(session, RunStatus.CLEANING)
    make_run_dir(tmp_path, RUN_ID, (
        "raw.csv", "cleaned.csv", "plan_final.json", "cleaning_report.json"))

    recovered = run_state.recover_claim(session, RUN_ID, tmp_path)

    assert recovered is RunStatus.CLEANED
    assert status_of(engine) == (RunStatus.CLEANED, None)


def test_a_claimed_run_whose_directory_is_gone_goes_back_to_planned(
    session: Session, tmp_path: Path
) -> None:
    add_run(session, RunStatus.CLEANING)  # no directory: the next call will say EXPIRED

    assert run_state.recover_claim(session, RUN_ID, tmp_path) is RunStatus.PLANNED


@pytest.mark.parametrize("status", [RunStatus.PLANNED, RunStatus.CLEANED, RunStatus.FAILED])
def test_recovery_never_touches_a_run_that_is_not_claimed(
    session: Session, engine: Engine, tmp_path: Path, status: RunStatus
) -> None:
    add_run(session, status)

    assert run_state.recover_claim(session, RUN_ID, tmp_path) is None
    assert status_of(engine)[0] is status


def test_load_live_run_frees_a_run_nothing_is_executing(
    session: Session, engine: Engine, tmp_path: Path
) -> None:
    add_run(session, RunStatus.CLEANING)  # a dead process left it here
    make_run_dir(tmp_path, RUN_ID, ("raw.csv",))

    run = run_state.load_live_run(session, RUN_ID, runs_root=tmp_path, work=RunWork())

    assert run.status is RunStatus.PLANNED
    assert status_of(engine)[0] is RunStatus.PLANNED
    # ...and it can be claimed, which is what a stuck run could not do.
    assert run_state.claim_for_cleaning(session, RUN_ID) is RunStatus.PLANNED


def test_load_live_run_never_steals_the_claim_of_a_run_being_executed(
    session: Session, engine: Engine, tmp_path: Path
) -> None:
    add_run(session, RunStatus.CLEANING)
    work = RunWork()

    with work.execution(RUN_ID):  # this process is executing it right now
        run = run_state.load_live_run(session, RUN_ID, runs_root=tmp_path, work=work)

    assert run.status is RunStatus.CLEANING
    assert status_of(engine)[0] is RunStatus.CLEANING


@pytest.mark.parametrize("status", [
    RunStatus.UPLOADED, RunStatus.PROFILED, RunStatus.PLANNED, RunStatus.CLEANED,
    RunStatus.FAILED,
])
def test_load_live_run_leaves_every_other_status_as_it_is(
    session: Session, tmp_path: Path, status: RunStatus
) -> None:
    add_run(session, status)

    run = run_state.load_live_run(session, RUN_ID, runs_root=tmp_path, work=RunWork())

    assert run.status is status


def test_load_live_run_still_answers_not_found_and_expired(
    session: Session, tmp_path: Path
) -> None:
    add_run(session, RunStatus.EXPIRED)

    assert error_of(lambda: run_state.load_live_run(
        session, RUN_ID, runs_root=tmp_path, work=RunWork())).code == "EXPIRED"
    assert error_of(lambda: run_state.load_live_run(
        session, "nope", runs_root=tmp_path, work=RunWork())).code == "NOT_FOUND"
