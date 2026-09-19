"""Stage 1 entry: validate an uploaded file and store it as `runs/<id>/raw.csv`
(SPECS sections 8, 10 and 11 SEC-1)."""

import os
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import BinaryIO

from app.errors import ApiError
from shared.run_registry import create_run

BYTES_PER_MB = 1_048_576  # SEC-1: 1 MB = 1,048,576 bytes
RAW_FILENAME = "raw.csv"  # CONTRACTS.md section 1

_CHUNK_BYTES = 64 * 1024
_HEAD_BYTES = 8 * 1024
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


@dataclass(frozen=True)
class StoredUpload:
    run_id: str
    filename: str
    size_bytes: int
    path: Path  # the run directory holding raw.csv


def max_upload_bytes(max_upload_mb: int) -> int:
    return max_upload_mb * BYTES_PER_MB


def store_upload(
    filename: str | None, stream: BinaryIO, runs_root: Path, max_bytes: int
) -> StoredUpload:
    """Checks run in the order type -> size -> empty -> binary. The type check
    needs no bytes, so it runs before a run directory exists; any later
    rejection removes the run directory again."""
    if filename is None or PurePath(filename).suffix.lower() != ".csv":
        # The browser-supplied MIME type is not trusted and not checked (SEC-1).
        raise ApiError(
            "UNSUPPORTED_TYPE", "Only .csv files are accepted.", {"filename": filename}
        )

    run = create_run(runs_root)
    try:
        size_bytes = _copy_checked(stream, run.path / RAW_FILENAME, max_bytes)
    except BaseException:
        # Best effort: the original error is what the caller needs to see, and
        # a leftover directory is removed by the retention cleanup (8B).
        shutil.rmtree(run.path, ignore_errors=True)
        raise
    return StoredUpload(
        run_id=run.run_id, filename=filename, size_bytes=size_bytes, path=run.path
    )


def _copy_checked(stream: BinaryIO, target: Path, max_bytes: int) -> int:
    size = 0
    head = b""
    has_content = False
    with target.open("wb") as out:
        while chunk := stream.read(_CHUNK_BYTES):
            size += len(chunk)
            if size > max_bytes:
                raise ApiError(
                    "FILE_TOO_LARGE",
                    f"The file is larger than the {max_bytes / BYTES_PER_MB:g} MB limit.",
                    {"max_bytes": max_bytes},
                )
            if not has_content:
                # A UTF-8 BOM alone is not content; it can only open the file.
                probe = chunk.removeprefix(_UTF8_BOM) if not head else chunk
                has_content = bool(probe.strip())
            if len(head) < _HEAD_BYTES:
                head += chunk[: _HEAD_BYTES - len(head)]
            out.write(chunk)
        # On disk before the caller commits a row that points at this file.
        out.flush()
        os.fsync(out.fileno())

    if not has_content:
        raise ApiError("EMPTY_FILE", "The file is empty.")
    if _looks_binary(head):
        raise ApiError(
            "PARSE_FAILED",
            "The file is not a text CSV file: it contains binary data.",
        )
    return size


def _looks_binary(head: bytes) -> bool:
    # A text CSV never contains a NUL byte, while xlsx/zip/exe files almost
    # always do in their first kilobytes. UTF-16 text is the exception (every
    # ASCII character carries a NUL), so a UTF-16 BOM lets it through to 1B.
    return b"\x00" in head and not head.startswith(_UTF16_BOMS)
