"""Writing several stage files so that a failure leaves nothing half-written
(stages/ingest/contract_files.write_files_atomically)."""

import os
from pathlib import Path

import pytest

from stages.ingest import contract_files
from stages.ingest.contract_files import write_files_atomically


def leftovers(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir())


def test_every_file_gets_exactly_its_bytes(tmp_path: Path) -> None:
    write_files_atomically([(tmp_path / "a.csv", b"x,y\r\n1,2\n"), (tmp_path / "b.json", b"{}")])

    # Bytes, not text: no newline translation on Windows.
    assert (tmp_path / "a.csv").read_bytes() == b"x,y\r\n1,2\n"
    assert (tmp_path / "b.json").read_bytes() == b"{}"
    assert leftovers(tmp_path) == ["a.csv", "b.json"]


def test_an_older_file_is_replaced_whole(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_bytes(b"old and much longer than the new one")

    write_files_atomically([(tmp_path / "a.csv", b"new")])

    assert (tmp_path / "a.csv").read_bytes() == b"new"


def test_a_failure_while_writing_the_last_file_leaves_no_new_file_and_no_temp_file(
    tmp_path: Path,
) -> None:
    files = [
        (tmp_path / "a.csv", b"1"),
        (tmp_path / "b.json", b"2"),
        (tmp_path / "no-such-folder" / "c.json", b"3"),  # its temp file cannot be created
    ]

    with pytest.raises(OSError):
        write_files_atomically(files)

    assert leftovers(tmp_path) == []  # nothing was renamed into place, nothing left behind


def test_a_failure_keeps_the_files_that_were_already_there(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_bytes(b"previous run")

    with pytest.raises(OSError):
        write_files_atomically([(tmp_path / "a.csv", b"new"), (tmp_path / "gone" / "b", b"2")])

    assert (tmp_path / "a.csv").read_bytes() == b"previous run"
    assert leftovers(tmp_path) == ["a.csv"]


def test_a_failure_during_the_renames_still_removes_the_temp_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real, calls = os.replace, []

    def flaky(source: str, target: str) -> None:
        calls.append(target)
        if len(calls) == 2:
            raise OSError("cannot replace")
        real(source, target)

    monkeypatch.setattr(contract_files.os, "replace", flaky)

    with pytest.raises(OSError):
        write_files_atomically([(tmp_path / "a.csv", b"1"), (tmp_path / "b.json", b"2")])

    # The first rename had happened, and is undone: neither file exists, and no
    # temp or backup file is left. (Before the 1F review this asserted that the
    # first file stayed, which is the mixture of old and new the rollback prevents.)
    assert leftovers(tmp_path) == []


# --- a failure while renaming puts everything back (1F review) --------------------------------
# On Windows a file another process holds open cannot be replaced. With three files
# renamed one after the other, the third failing left the first two new and the
# report old: a cleaned.csv from one plan next to the report of another.


def old_files(tmp_path: Path) -> dict[str, bytes]:
    files = {"cleaned.csv": b"old csv", "plan_final.json": b"old plan", "cleaning_report.json": b"old report"}
    for name, data in files.items():
        (tmp_path / name).write_bytes(data)
    return files


def new_files(tmp_path: Path) -> list[tuple[Path, bytes]]:
    return [(tmp_path / "cleaned.csv", b"new csv"), (tmp_path / "plan_final.json", b"new plan"),
            (tmp_path / "cleaning_report.json", b"new report")]


def state(tmp_path: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(tmp_path.iterdir())}


def failing_when(monkeypatch: pytest.MonkeyPatch, wanted: str) -> None:
    """os.replace fails for the call that puts a new file (a .tmp) at `wanted`."""
    real = os.replace

    def flaky(source: str, target: str) -> None:
        if str(target).endswith(wanted) and str(source).endswith(".tmp"):
            raise PermissionError(f"the file {wanted} is in use")
        real(source, target)

    monkeypatch.setattr(contract_files.os, "replace", flaky)


def test_a_failure_placing_the_last_file_restores_the_first_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = old_files(tmp_path)
    failing_when(monkeypatch, "cleaning_report.json")

    with pytest.raises(PermissionError):
        write_files_atomically(new_files(tmp_path))

    assert state(tmp_path) == before  # all old, and no temp or backup file left


def test_a_failure_moving_the_old_last_file_aside_restores_the_first_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = old_files(tmp_path)
    real = os.replace

    def flaky(source: str, target: str) -> None:
        if str(source).endswith("cleaning_report.json"):  # moving the old report to a backup
            raise PermissionError("the report is in use")
        real(source, target)

    monkeypatch.setattr(contract_files.os, "replace", flaky)

    with pytest.raises(PermissionError):
        write_files_atomically(new_files(tmp_path))

    assert state(tmp_path) == before


def test_a_first_time_write_that_fails_leaves_no_file_at_all(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    failing_when(monkeypatch, "cleaning_report.json")

    with pytest.raises(PermissionError):
        write_files_atomically(new_files(tmp_path))

    assert state(tmp_path) == {}


def test_a_file_that_is_really_held_open_never_leaves_a_mixed_set(tmp_path: Path) -> None:
    # No monkeypatching: on Windows a plain open() blocks the rename, elsewhere it
    # does not. Either way the result is all old or all new, never a mixture.
    before = old_files(tmp_path)
    refused: OSError | None = None

    with open(tmp_path / "cleaning_report.json", "rb"):
        try:
            write_files_atomically(new_files(tmp_path))
        except OSError as error:
            refused = error

    new = {"cleaned.csv": b"new csv", "plan_final.json": b"new plan", "cleaning_report.json": b"new report"}
    assert state(tmp_path) == (before if refused is not None else new)


def test_a_rollback_that_itself_fails_is_reported_not_swallowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_files(tmp_path)
    real = os.replace

    def flaky(source: str, target: str) -> None:
        if str(target).endswith("cleaning_report.json") and str(source).endswith(".tmp"):
            raise PermissionError("in use")
        if str(source).endswith(".bak") and str(target).endswith("cleaned.csv"):
            raise OSError("cannot restore")  # the rollback fails too
        real(source, target)

    monkeypatch.setattr(contract_files.os, "replace", flaky)

    with pytest.raises(PermissionError) as caught:
        write_files_atomically(new_files(tmp_path))

    assert any("could not restore cleaned.csv" in note for note in caught.value.__notes__)


def test_a_successful_write_leaves_no_backup_files(tmp_path: Path) -> None:
    old_files(tmp_path)

    write_files_atomically(new_files(tmp_path))

    assert sorted(state(tmp_path)) == ["cleaned.csv", "cleaning_report.json", "plan_final.json"]
    assert state(tmp_path)["cleaned.csv"] == b"new csv"


def test_every_file_is_flushed_to_disk_before_it_is_renamed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Without it a crash could leave a zero-length file behind a finished report.
    synced: list[int] = []
    real = os.fsync
    monkeypatch.setattr(contract_files.os, "fsync", lambda fd: (synced.append(fd), real(fd))[1])

    write_files_atomically(new_files(tmp_path))

    assert len(synced) == 3


def test_write_contract_writes_line_feeds_like_the_other_stage_files(tmp_path: Path) -> None:
    from contracts.cleaning import CleaningWarning  # any small pydantic model will do

    contract_files.write_contract(tmp_path / "x.json", CleaningWarning(code="a", detail="b"))

    assert b"\r\n" not in (tmp_path / "x.json").read_bytes()
