"""Run directories: `runs/<run_id>/` creation and path resolution
(docs/CONTRACTS.md section 1).

Infrastructure only. The runs root is passed in by the caller (the backend
passes `Settings.runs_dir`, already anchored to the repo root) because `shared/`
may not import the backend (tests/test_architecture.py, SPECS SEC-4).
"""

import uuid
from dataclasses import dataclass
from pathlib import Path


class RunNotFoundError(LookupError):
    """The run id is well formed but no run directory exists for it."""


class InvalidRunIdError(ValueError):
    """The run id is not a canonical UUID, so it can never name a run."""


@dataclass(frozen=True)
class NewRun:
    run_id: str
    path: Path


def create_run(runs_root: Path) -> NewRun:
    _require_absolute(runs_root)
    run_id = str(uuid.uuid4())
    path = runs_root / run_id
    runs_root.mkdir(parents=True, exist_ok=True)
    # exist_ok=False: a reused id would mix two runs' files, so fail loudly.
    path.mkdir(exist_ok=False)
    return NewRun(run_id=run_id, path=path)


def run_dir(runs_root: Path, run_id: str) -> Path:
    _require_absolute(runs_root)
    _require_canonical_uuid(run_id)
    path = runs_root / run_id
    if not path.is_dir():
        raise RunNotFoundError(f"no run directory for run_id {run_id} under {runs_root}")
    return path


def run_file(runs_root: Path, run_id: str, filename: str) -> Path:
    """Path of a file inside an existing run. The file itself need not exist:
    stages use this to find where to write their output."""
    if filename in {"", ".", ".."} or Path(filename).name != filename or "\\" in filename:
        raise ValueError(f"filename must be a bare file name, got {filename!r}")
    return run_dir(runs_root, run_id) / filename


def _require_absolute(runs_root: Path) -> None:
    # A relative root would silently follow the process's working directory.
    if not runs_root.is_absolute():
        raise ValueError(f"runs_root must be absolute, got {runs_root}")


def _require_canonical_uuid(run_id: str) -> None:
    # Run ids reach us from URLs; only the exact form create_run produces is
    # accepted, so an id can never climb out of runs_root or alias another run.
    try:
        canonical = str(uuid.UUID(run_id))
    except ValueError:
        raise InvalidRunIdError(f"run_id is not a UUID: {run_id!r}") from None
    if canonical != run_id:
        raise InvalidRunIdError(f"run_id is not in canonical form: {run_id!r}")
