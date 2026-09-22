"""Downloading a run's cleaned output (docs/SPECS.md section 8 mentions
"download urls" on `execute`'s response; not built in 1G). Read-only: no work
claim, since nothing here can race a step that changes the run's status.
"""

import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import RunStatus
from app.services import run_state, stage_errors
from shared.run_registry import run_file
from stages.ingest.cleaning import CLEANED_FILENAME

# The statuses whose run has a cleaned.csv on disk (SPECS section 3).
_HAS_CLEANED_FILE = (RunStatus.CLEANED, RunStatus.ANALYZED, RunStatus.IMPORTED)
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True)
class DownloadFile:
    content: bytes
    media_type: str
    filename: str  # sanitized: safe to put in a Content-Disposition header as-is


def _safe_stem(name: str, *, default: str) -> str:
    """The uploaded filename is user-supplied and only its extension was ever
    checked (SEC-1); a control character or quote in it must never reach a
    response header, so only a plain allowlist of characters survives."""
    cleaned = _UNSAFE_FILENAME_CHARS.sub("_", Path(name).stem).strip("._")
    return cleaned or default


def download_cleaned_csv(session: Session, run_id: str, *, settings: Settings) -> DownloadFile:
    run = run_state.load_run(session, run_id)
    run_state.require_status(run, *_HAS_CLEANED_FILE, step="download the cleaned file")
    path = run_file(settings.runs_dir, run_id, CLEANED_FILENAME)
    if not path.exists():
        raise stage_errors.files_gone()
    stem = _safe_stem(run.filename, default="data")
    return DownloadFile(content=path.read_bytes(), media_type="text/csv", filename=f"cleaned_{stem}.csv")
