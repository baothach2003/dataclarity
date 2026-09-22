from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from app.models import Base, Run, RunStatus

CREATED = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
RUN_ID = "3f0c9a1e-5b7d-4c2e-9a8b-1d2e3f4a5b6c"


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def make_run(**overrides: object) -> Run:
    fields: dict[str, object] = {
        "id": RUN_ID,
        "filename": "sales.csv",
        "size_bytes": 13,
        "status": RunStatus.UPLOADED,
        "created_at": CREATED,
        "expires_at": CREATED + timedelta(hours=24),
    }
    fields.update(overrides)
    return Run(**fields)


def reload(session: Session) -> Run:
    session.commit()
    session.expunge_all()
    run = session.get(Run, RUN_ID)
    assert run is not None
    return run


def test_run_round_trips_every_column(session: Session) -> None:
    session.add(make_run())

    run = reload(session)

    assert run.filename == "sales.csv"
    assert run.size_bytes == 13
    assert run.status is RunStatus.UPLOADED
    assert run.expires_at - run.created_at == timedelta(hours=24)
    assert run.error_code is None


def test_timestamps_come_back_timezone_aware_in_utc(session: Session) -> None:
    # SQLite stores no timezone; without UtcDateTime this would come back naive
    # here but aware on PostgreSQL.
    session.add(make_run())

    run = reload(session)

    assert run.created_at == CREATED
    assert run.created_at.tzinfo is UTC


def test_non_utc_timestamps_are_stored_as_the_same_instant_in_utc(session: Session) -> None:
    sydney = timezone(timedelta(hours=10))
    session.add(make_run(created_at=datetime(2026, 9, 19, 20, 0, tzinfo=sydney)))

    run = reload(session)

    assert run.created_at == CREATED  # 20:00 at +10:00 is 10:00 UTC
    assert run.created_at.tzinfo is UTC


def test_naive_timestamps_are_rejected(session: Session) -> None:
    session.add(make_run(created_at=datetime(2026, 9, 19, 10, 0)))

    with pytest.raises(StatementError, match="timezone"):
        session.commit()


def test_every_specs_state_is_a_run_status() -> None:
    # SPECS section 3 state machine, plus `cleaning` (the claim held while a
    # plan executes, 1G), failed and expired.
    assert [s.value for s in RunStatus] == [
        "uploaded", "profiled", "planned", "cleaning", "cleaned", "analyzed", "imported",
        "failed", "expired",
    ]


def test_database_rejects_an_unknown_status_even_without_the_orm(session: Session) -> None:
    # The CHECK constraint, not only the Python enum, guards the column.
    with pytest.raises(IntegrityError, match="CHECK"):
        session.execute(
            text(
                "INSERT INTO runs (id, filename, size_bytes, status, created_at, expires_at)"
                " VALUES (:id, 'a.csv', 1, 'bogus', '2026-09-19', '2026-09-20')"
            ),
            {"id": RUN_ID},
        )


@pytest.mark.parametrize("column", ["filename", "size_bytes", "created_at", "expires_at"])
def test_required_columns_reject_null(session: Session, column: str) -> None:
    session.add(make_run(**{column: None}))

    with pytest.raises((IntegrityError, StatementError)):
        session.commit()
