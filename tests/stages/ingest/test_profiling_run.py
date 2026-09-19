import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contracts import ProfileContract
from shared.run_registry import RunNotFoundError, create_run
from stages.ingest.profiling import EmptyCsvError, profile_run

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)


def run_with_raw(runs_root: Path, content: bytes) -> str:
    run = create_run(runs_root)
    (run.path / "raw.csv").write_bytes(content)
    return run.run_id


def test_writes_profile_json_next_to_raw_csv(tmp_path: Path) -> None:
    run_id = run_with_raw(tmp_path, b"sku,qty\nA1,3\nB2,5\n")

    returned = profile_run(tmp_path, run_id, now=NOW)

    written = tmp_path / run_id / "profile.json"
    assert ProfileContract.model_validate_json(written.read_text(encoding="utf-8")) == returned
    assert returned.dataset.rows == 2
    assert returned.columns[1].mean == 4.0  # (3 + 5) / 2


def test_leaves_only_raw_and_profile_in_the_run_directory(tmp_path: Path) -> None:
    run_id = run_with_raw(tmp_path, b"sku,qty\nA1,3\n")

    profile_run(tmp_path, run_id, now=NOW)

    assert sorted(p.name for p in (tmp_path / run_id).iterdir()) == ["profile.json", "raw.csv"]


def test_rerun_replaces_its_own_output(tmp_path: Path) -> None:
    run_id = run_with_raw(tmp_path, b"sku,qty\nA1,3\n")
    profile_run(tmp_path, run_id, now=NOW)
    (tmp_path / run_id / "raw.csv").write_bytes(b"sku,qty\nA1,3\nB2,4\n")

    profile_run(tmp_path, run_id, now=NOW)

    reread = ProfileContract.model_validate_json(
        (tmp_path / run_id / "profile.json").read_text(encoding="utf-8")
    )
    assert reread.dataset.rows == 2


def test_header_only_file_writes_no_profile(tmp_path: Path) -> None:
    run_id = run_with_raw(tmp_path, b"sku,qty\n")

    with pytest.raises(EmptyCsvError):
        profile_run(tmp_path, run_id, now=NOW)

    assert not (tmp_path / run_id / "profile.json").exists()


def test_unknown_run_is_reported_by_the_registry(tmp_path: Path) -> None:
    with pytest.raises(RunNotFoundError):
        profile_run(tmp_path, str(uuid.uuid4()), now=NOW)
