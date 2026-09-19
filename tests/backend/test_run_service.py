import io
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.errors import ApiError
from app.models import Base, Run, RunStatus
from app.services.runs import create_run_from_upload

NOW = datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
SMALL_CSV = b"sku,qty\nA1,3\n"  # 13 bytes


@pytest.fixture
def engine() -> Iterator[Engine]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with Session(engine) as session:
        yield session


def upload(session: Session, runs_root: Path, content: bytes = SMALL_CSV,
           filename: str = "sales.csv") -> Run:
    return create_run_from_upload(
        session, filename, io.BytesIO(content), runs_root,
        max_bytes=1_048_576, retention_hours=24, now=NOW,
    )


def all_runs(engine: Engine) -> list[Run]:
    with Session(engine) as fresh:
        return list(fresh.scalars(select(Run)))


def test_row_and_directory_agree(session: Session, engine: Engine, tmp_path: Path) -> None:
    run = upload(session, tmp_path)

    [row] = all_runs(engine)  # read back through a separate session
    raw = tmp_path / row.id / "raw.csv"
    assert row.id == run.id
    assert raw.read_bytes() == SMALL_CSV
    assert row.size_bytes == raw.stat().st_size == 13
    assert row.filename == "sales.csv"
    assert row.status is RunStatus.UPLOADED
    assert row.error_code is None
    assert [p.name for p in tmp_path.iterdir()] == [row.id]


def test_expiry_is_creation_plus_retention(session: Session, engine: Engine,
                                           tmp_path: Path) -> None:
    upload(session, tmp_path)

    [row] = all_runs(engine)
    assert row.created_at == datetime(2026, 9, 19, 10, 0, tzinfo=UTC)
    assert row.expires_at == datetime(2026, 9, 20, 10, 0, tzinfo=UTC)  # +24 h


def test_rejected_upload_creates_neither_row_nor_directory(
    session: Session, engine: Engine, tmp_path: Path
) -> None:
    with pytest.raises(ApiError):
        upload(session, tmp_path, content=b"")

    assert all_runs(engine) == []
    assert list(tmp_path.iterdir()) == []


def test_failed_insert_removes_the_directory(tmp_path: Path) -> None:
    # No tables: the INSERT fails at flush, before anything can be committed.
    engine = create_engine("sqlite://", poolclass=StaticPool)
    with Session(engine) as session, pytest.raises(OperationalError):
        upload(session, tmp_path)

    assert list(tmp_path.iterdir()) == []


def test_failed_commit_keeps_the_directory(
    session: Session, engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A commit that errors may still have committed on the server; deleting
    # the file then could leave a row without raw.csv. Keeping it can at worst
    # leave a directory without a row, which retention cleanup removes (8B).
    def commit_fails() -> None:
        raise OperationalError("COMMIT", {}, Exception("connection lost"))

    monkeypatch.setattr(session, "commit", commit_fails)

    with pytest.raises(OperationalError):
        upload(session, tmp_path)

    [kept] = list(tmp_path.iterdir())
    assert (kept / "raw.csv").read_bytes() == SMALL_CSV
