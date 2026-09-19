import io
from pathlib import Path
from typing import Any

import pytest

from app.errors import ApiError
from app.services.uploads import StoredUpload, max_upload_bytes, store_upload

# "sku,qty\n" is 8 bytes and "A1,3\n" is 5: 13 bytes in total.
SMALL_CSV = b"sku,qty\nA1,3\n"


def upload(content: bytes, runs_root: Path, filename: str | None = "sales.csv",
           max_bytes: int = 1_048_576) -> StoredUpload:
    return store_upload(filename, io.BytesIO(content), runs_root, max_bytes)


def rejected_code(content: bytes, runs_root: Path, **kwargs: Any) -> str:
    with pytest.raises(ApiError) as caught:
        upload(content, runs_root, **kwargs)
    return caught.value.code


def leftover_runs(runs_root: Path) -> list[Path]:
    return list(runs_root.iterdir()) if runs_root.exists() else []


# --- accepted ------------------------------------------------------------------


def test_stores_the_bytes_verbatim_as_raw_csv(tmp_path: Path) -> None:
    stored = upload(SMALL_CSV, tmp_path)

    assert stored.size_bytes == 13
    assert stored.filename == "sales.csv"
    assert (tmp_path / stored.run_id / "raw.csv").read_bytes() == SMALL_CSV


def test_accepts_uppercase_extension(tmp_path: Path) -> None:
    stored = upload(SMALL_CSV, tmp_path, filename="SALES.CSV")

    assert stored.filename == "SALES.CSV"


def test_accepts_a_file_of_exactly_the_limit(tmp_path: Path) -> None:
    stored = upload(SMALL_CSV, tmp_path, max_bytes=13)

    assert stored.size_bytes == 13


def test_copies_a_file_larger_than_one_chunk_intact(tmp_path: Path) -> None:
    content = b"sku,qty\n" + b"A1,3\n" * 40_000  # 200,008 bytes, several 64 KB chunks

    stored = upload(content, tmp_path)

    assert stored.size_bytes == 200_008
    assert (tmp_path / stored.run_id / "raw.csv").read_bytes() == content


def test_accepts_utf16_text_even_though_it_contains_nul_bytes(tmp_path: Path) -> None:
    content = "sku,qty\r\nA1,3\r\n".encode("utf-16")  # starts with a BOM

    stored = upload(content, tmp_path)

    assert stored.size_bytes == len(content)


def test_only_the_first_8_kb_are_checked_for_binary_data(tmp_path: Path) -> None:
    # A known limit of the heuristic, kept on purpose: the parser in 1B sees
    # the rest of the file.
    content = b"sku,qty\n" + b"A" * 9000 + b"\x00\n"

    stored = upload(content, tmp_path)

    assert stored.size_bytes == len(content)


# --- rejected ------------------------------------------------------------------


@pytest.mark.parametrize("filename", ["sales.xlsx", "sales.csv.exe", "sales", ".csv", None])
def test_rejects_other_extensions_without_creating_a_run(
    tmp_path: Path, filename: str | None
) -> None:
    assert rejected_code(SMALL_CSV, tmp_path, filename=filename) == "UNSUPPORTED_TYPE"
    assert leftover_runs(tmp_path) == []


def test_rejects_one_byte_over_the_limit_and_removes_the_run(tmp_path: Path) -> None:
    assert rejected_code(SMALL_CSV, tmp_path, max_bytes=12) == "FILE_TOO_LARGE"
    assert leftover_runs(tmp_path) == []


@pytest.mark.parametrize(
    "content",
    [b"", b" \n\t\r\n", b"\xef\xbb\xbf", b"\xef\xbb\xbf\r\n"],
    ids=["zero-bytes", "whitespace", "utf8-bom-only", "utf8-bom-and-newline"],
)
def test_rejects_empty_files_and_removes_the_run(tmp_path: Path, content: bytes) -> None:
    assert rejected_code(content, tmp_path) == "EMPTY_FILE"
    assert leftover_runs(tmp_path) == []


def test_rejects_binary_content_renamed_to_csv(tmp_path: Path) -> None:
    xlsx_like = b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 100  # zip/xlsx signature

    assert rejected_code(xlsx_like, tmp_path) == "PARSE_FAILED"
    assert leftover_runs(tmp_path) == []


def test_size_is_checked_before_content(tmp_path: Path) -> None:
    oversized_binary = b"\x00" * 20

    assert rejected_code(oversized_binary, tmp_path, max_bytes=10) == "FILE_TOO_LARGE"


def test_too_large_error_reports_the_limit(tmp_path: Path) -> None:
    with pytest.raises(ApiError) as caught:
        upload(b"x" * 1_048_577, tmp_path)

    assert caught.value.message == "The file is larger than the 1 MB limit."
    assert caught.value.details == {"max_bytes": 1_048_576}


# --- limit conversion (SEC-1: 1 MB = 1,048,576 bytes) --------------------------


@pytest.mark.parametrize(("mb", "expected"), [(1, 1_048_576), (50, 52_428_800)])
def test_max_upload_bytes_uses_binary_megabytes(mb: int, expected: int) -> None:
    assert max_upload_bytes(mb) == expected
