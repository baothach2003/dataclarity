from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

ONE_MB = 1_048_576  # SEC-1


@pytest.fixture
def runs_root(tmp_path: Path) -> Path:
    return tmp_path / "runs"


@pytest.fixture
def client(runs_root: Path) -> TestClient:
    # max_upload_mb=1 keeps the SEC-1 boundary tests at 1 MB instead of 50 MB;
    # the MB-to-bytes rule is the same.
    settings = Settings(  # type: ignore[call-arg]  # remaining fields come from env
        _env_file=None, runs_dir=str(runs_root), max_upload_mb=1
    )
    return TestClient(create_app(settings))


def post_file(client: TestClient, content: bytes, filename: str = "sales.csv",
              content_type: str = "text/csv") -> httpx.Response:
    return client.post("/api/runs", files={"file": (filename, content, content_type)})


def csv_of_exact_size(size: int) -> bytes:
    header = b"sku,qty\n"
    return header + b"1" * (size - len(header))


def test_valid_upload_returns_201_and_stores_raw_csv(client: TestClient, runs_root: Path) -> None:
    content = b"sku,qty\nA1,3\n"  # 13 bytes

    response = post_file(client, content)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"run_id", "filename", "size_bytes", "status"}
    assert body["filename"] == "sales.csv"
    assert body["size_bytes"] == 13
    assert body["status"] == "uploaded"
    # The response and the filesystem agree.
    raw = runs_root / body["run_id"] / "raw.csv"
    assert raw.read_bytes() == content
    assert raw.stat().st_size == body["size_bytes"]


def test_file_of_exactly_the_limit_is_accepted(client: TestClient) -> None:
    response = post_file(client, csv_of_exact_size(ONE_MB))

    assert response.status_code == 201
    assert response.json()["size_bytes"] == ONE_MB


def test_file_one_byte_over_the_limit_is_rejected(client: TestClient, runs_root: Path) -> None:
    response = post_file(client, csv_of_exact_size(ONE_MB + 1))

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert not runs_root.exists() or list(runs_root.iterdir()) == []


@pytest.mark.parametrize("filename", ["sales.xlsx", "sales.csv.exe", "sales.txt"])
def test_other_extensions_are_rejected(client: TestClient, filename: str) -> None:
    response = post_file(client, b"sku,qty\nA1,3\n", filename=filename)

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "UNSUPPORTED_TYPE",
            "message": "Only .csv files are accepted.",
            "details": {"filename": filename},
        }
    }


def test_uppercase_extension_is_accepted(client: TestClient) -> None:
    assert post_file(client, b"sku,qty\nA1,3\n", filename="SALES.CSV").status_code == 201


def test_browser_mime_type_is_not_checked(client: TestClient) -> None:
    response = post_file(client, b"sku,qty\nA1,3\n", content_type="application/octet-stream")

    assert response.status_code == 201


def test_empty_file_is_rejected(client: TestClient, runs_root: Path) -> None:
    response = post_file(client, b"")

    assert response.status_code == 400
    assert response.json() == {"error": {"code": "EMPTY_FILE", "message": "The file is empty."}}
    assert not runs_root.exists() or list(runs_root.iterdir()) == []


def test_binary_file_renamed_to_csv_is_rejected(client: TestClient) -> None:
    response = post_file(client, b"PK\x03\x04\x14\x00\x06\x00" + b"\x00" * 100)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PARSE_FAILED"
