import uuid
from pathlib import Path

import pytest

from shared.run_registry import (
    InvalidRunIdError,
    RunNotFoundError,
    create_run,
    run_dir,
    run_file,
)

# --- create_run ---------------------------------------------------------------


def test_create_run_returns_canonical_uuid4(tmp_path: Path) -> None:
    run = create_run(tmp_path)

    parsed = uuid.UUID(run.run_id)
    assert parsed.version == 4
    assert str(parsed) == run.run_id  # lowercase, hyphenated: one spelling per run


def test_create_run_makes_an_empty_directory_named_after_the_id(tmp_path: Path) -> None:
    run = create_run(tmp_path)

    assert run.path == tmp_path / run.run_id
    assert run.path.is_dir()
    assert list(run.path.iterdir()) == []


def test_create_run_creates_a_missing_runs_root(tmp_path: Path) -> None:
    # First run on a fresh checkout: runs/ is gitignored, so it does not exist.
    runs_root = tmp_path / "runs"

    run = create_run(runs_root)

    assert run.path.parent == runs_root
    assert run.path.is_dir()


def test_two_runs_get_different_directories(tmp_path: Path) -> None:
    first = create_run(tmp_path)
    second = create_run(tmp_path)

    assert first.run_id != second.run_id
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [first.run_id, second.run_id]
    )


def test_create_run_rejects_relative_runs_root_without_touching_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    with pytest.raises(ValueError, match="absolute"):
        create_run(Path("runs"))

    assert list(tmp_path.iterdir()) == []


# --- run_dir / run_file -------------------------------------------------------


def test_run_dir_resolves_an_existing_run(tmp_path: Path) -> None:
    run = create_run(tmp_path)

    assert run_dir(tmp_path, run.run_id) == run.path


def test_run_file_resolves_a_contract_file_inside_the_run(tmp_path: Path) -> None:
    run = create_run(tmp_path)

    path = run_file(tmp_path, run.run_id, "profile.json")

    # The file need not exist yet: stages use this path to write their output.
    assert path == tmp_path / run.run_id / "profile.json"
    assert not path.exists()


def test_run_dir_raises_for_unknown_run(tmp_path: Path) -> None:
    unknown = str(uuid.uuid4())

    with pytest.raises(RunNotFoundError, match=unknown):
        run_dir(tmp_path, unknown)


def test_run_file_raises_for_unknown_run(tmp_path: Path) -> None:
    unknown = str(uuid.uuid4())

    with pytest.raises(RunNotFoundError, match=unknown):
        run_file(tmp_path, unknown, "profile.json")


def test_run_dir_raises_when_the_id_names_a_file_not_a_directory(tmp_path: Path) -> None:
    stray = str(uuid.uuid4())
    (tmp_path / stray).write_text("not a run")

    with pytest.raises(RunNotFoundError):
        run_dir(tmp_path, stray)


def test_run_dir_raises_when_runs_root_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(RunNotFoundError):
        run_dir(tmp_path / "missing", str(uuid.uuid4()))


@pytest.mark.parametrize(
    "run_id",
    [
        "",
        "not-a-uuid",
        "../etc",
        "..",
        "3F0C9A1E-5B7D-4C2E-9A8B-1D2E3F4A5B6C",  # valid UUID, non-canonical case
        "{3f0c9a1e-5b7d-4c2e-9a8b-1d2e3f4a5b6c}",
        "3f0c9a1e5b7d4c2e9a8b1d2e3f4a5b6c",
    ],
)
def test_run_dir_rejects_ids_that_are_not_canonical_uuids(
    tmp_path: Path, run_id: str
) -> None:
    with pytest.raises(InvalidRunIdError):
        run_dir(tmp_path, run_id)


@pytest.mark.parametrize(
    "filename", ["", ".", "..", "../raw.csv", "sub/profile.json", "sub\profile.json"]
)
def test_run_file_rejects_anything_but_a_bare_filename(
    tmp_path: Path, filename: str
) -> None:
    run = create_run(tmp_path)

    with pytest.raises(ValueError, match="filename"):
        run_file(tmp_path, run.run_id, filename)


def test_errors_map_to_distinct_caller_categories() -> None:
    # Callers (Phase 1 routers) can map these to 404 and 400 without string matching.
    assert issubclass(RunNotFoundError, LookupError)
    assert issubclass(InvalidRunIdError, ValueError)
