"""Writing stage 1 contract files (docs/CONTRACTS.md section 1)."""

import os
import secrets
import tempfile
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel


class StaleInputError(ValueError):
    """A contract file that a step needs describes other data than the file it is
    checked against (the file was profiled again after the schema was inferred).
    A ValueError so existing callers keep working; the backend answers INVALID_STATE
    (409) and needs it apart from the other ValueErrors, a pydantic ValidationError
    among them."""


def write_contract(target: Path, contract: BaseModel) -> None:
    """Write atomically (see `write_files_atomically`): a later stage reads the
    previous file or the complete new one, never half of it."""
    write_files_atomically([(target, contract.model_dump_json(indent=2).encode("utf-8"))])


def write_files_atomically(files: Sequence[tuple[Path, bytes]]) -> None:
    """Write several files so that a failure leaves nothing half-written and no
    mixture of old and new.

    Every file is written in full to a temp file beside its target and flushed to
    disk first. Only when all of them exist are they renamed into place, in the
    order given: each existing target is moved aside to a backup, then its new
    file is renamed in. If anything fails (a full disk, a folder that is gone, a
    file another process holds open, which Windows refuses to replace), every
    target is put back as it was, or removed if it did not exist, and no temp or
    backup file is left. A restore that itself fails is added to the error as a
    note, not swallowed. Order the files so that the one that says "this run is
    complete" comes last.

    Bytes, not text, so no newline is translated on Windows.
    """
    temps: list[tuple[Path, Path]] = []
    undo: list[tuple[Path, Path | None]] = []  # (target, its old contents moved aside)
    try:
        for target, data in files:
            handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".stage-", suffix=".tmp")
            temps.append((Path(temp_name), target))
            with os.fdopen(handle, "wb") as out:
                out.write(data)
                out.flush()
                os.fsync(out.fileno())  # or a crash could leave an empty file behind a finished report
        for temp, target in temps:
            backup = None
            if target.exists():
                backup = target.with_name(f".stage-{secrets.token_hex(6)}.bak")
                os.replace(target, backup)
            undo.append((target, backup))
            os.replace(temp, target)
        for _, backup in undo:
            if backup is not None:
                backup.unlink(missing_ok=True)
    except BaseException as error:
        for target, backup in reversed(undo):
            try:
                if backup is not None:
                    os.replace(backup, target)  # over the new file, if it was already in place
                else:
                    target.unlink(missing_ok=True)
            except OSError as failure:
                error.add_note(f"could not restore {target.name}: {failure}")
        for temp, _ in temps:
            temp.unlink(missing_ok=True)
        raise
