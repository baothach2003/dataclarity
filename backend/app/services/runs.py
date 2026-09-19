"""Run lifecycle: create a run from an upload (file + `runs` row).

Invariant: a `runs` row exists only if its raw.csv is complete on disk. The
reverse (a directory without a row) can happen only when a commit fails with
an unknown outcome; the retention cleanup (PROJECT_PLAN 8B) removes it.
"""

import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

from sqlalchemy.orm import Session

from app.models import Run, RunStatus
from app.services.uploads import store_upload


def create_run_from_upload(
    session: Session,
    filename: str | None,
    stream: BinaryIO,
    runs_root: Path,
    max_bytes: int,
    retention_hours: int,
    now: datetime | None = None,
) -> Run:
    # 1. File first: validation needs the bytes, a rejected upload must never
    #    create a row, and raw.csv is fsynced before any row points at it.
    stored = store_upload(filename, stream, runs_root, max_bytes)

    created_at = now or datetime.now(UTC)
    run = Run(
        id=stored.run_id,
        filename=stored.filename,
        size_bytes=stored.size_bytes,
        status=RunStatus.UPLOADED,
        created_at=created_at,
        expires_at=created_at + timedelta(hours=retention_hours),
    )

    # 2. Flush: the INSERT runs inside the open transaction, so a database
    #    that is down or rejects the row fails here, with nothing committed.
    #    Removing the directory then leaves no trace.
    session.add(run)
    try:
        session.flush()
    except BaseException:
        session.rollback()
        shutil.rmtree(stored.path, ignore_errors=True)
        raise

    # 3. Commit: an error here does not prove the row was not committed (the
    #    connection can drop after the server committed). Deleting the file
    #    could leave a row without raw.csv, so the directory is kept.
    session.commit()
    return run
