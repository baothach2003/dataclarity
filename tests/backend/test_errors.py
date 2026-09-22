from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import Settings
from app.errors import STATUS_BY_CODE, ApiError, ErrorCode
from app.main import create_app


def client_raising(error: ApiError, settings: Settings) -> TestClient:
    app = create_app(settings)

    def boom() -> None:
        raise error

    app.add_api_route("/boom", boom)
    return TestClient(app)


def test_api_error_uses_the_specs_envelope_and_status(settings: Settings) -> None:
    client = client_raising(
        ApiError("FILE_TOO_LARGE", "File is larger than 50 MB.", {"max_bytes": 52428800}),
        settings,
    )

    response = client.get("/boom")

    assert response.status_code == 413
    assert response.json() == {
        "error": {
            "code": "FILE_TOO_LARGE",
            "message": "File is larger than 50 MB.",
            "details": {"max_bytes": 52428800},
        }
    }


def test_api_error_omits_details_when_there_are_none(settings: Settings) -> None:
    client = client_raising(ApiError("EMPTY_FILE", "The file is empty."), settings)

    response = client.get("/boom")

    assert response.status_code == 400
    assert response.json() == {"error": {"code": "EMPTY_FILE", "message": "The file is empty."}}


# --- SPECS section 10: the code -> HTTP status table (1G) ---------------------

STATUS_TABLE = {
    "FILE_TOO_LARGE": 413,
    "UNSUPPORTED_TYPE": 400,
    "EMPTY_FILE": 400,
    "PARSE_FAILED": 400,
    "INVALID_STATE": 409,
    "INVALID_PLAN": 422,
    "CLEANING_FAILED": 422,
    "EXPIRED": 410,
    "RATE_LIMITED": 429,
    # Not in SPECS section 10 before 1G: every response is inside the envelope.
    "NOT_FOUND": 404,
    "INVALID_REQUEST": 400,
    "INTERNAL_ERROR": 500,
}


def test_every_code_maps_to_its_specs_status() -> None:
    assert STATUS_BY_CODE == STATUS_TABLE


@pytest.mark.parametrize("code", sorted(STATUS_TABLE))
def test_each_code_is_answered_with_its_status_and_the_envelope(
    code: ErrorCode, settings: Settings
) -> None:
    response = client_raising(ApiError(code, "message"), settings).get("/boom")

    assert response.status_code == STATUS_TABLE[code]
    assert response.json() == {"error": {"code": code, "message": "message"}}


# --- what used to escape the envelope -----------------------------------------


def test_a_request_without_the_file_part_is_invalid_request_not_fastapis_detail(
    settings: Settings,
) -> None:
    client = TestClient(create_app(settings))

    response = client.post("/api/runs", data={"note": "no file here"})

    assert response.status_code == 400
    body = response.json()
    assert "detail" not in body
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["details"]["problems"] == ["body.file: Field required"]


def test_the_problems_never_echo_the_value_the_client_sent(settings: Settings) -> None:
    # FastAPI's default answer repeats the input; a rejected request body can be a
    # whole plan or a large upload part.
    client = TestClient(create_app(settings))

    response = client.post("/api/runs", data={"file": "SECRET-VALUE-" + "x" * 500})

    assert response.status_code == 400
    assert "SECRET-VALUE" not in response.text


def test_an_unknown_path_is_not_found_in_the_envelope(settings: Settings) -> None:
    response = TestClient(create_app(settings)).get("/api/nothing-here")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_wrong_method_keeps_its_405_and_the_envelope(settings: Settings) -> None:
    response = TestClient(create_app(settings)).delete("/health")

    assert response.status_code == 405
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert "GET" in response.headers["allow"]  # a 405 must say what is allowed


def test_an_unexpected_exception_is_internal_error_without_its_text(settings: Settings) -> None:
    app = create_app(settings)

    def boom() -> None:
        raise RuntimeError("password=hunter2 at /secret/path")

    app.add_api_route("/boom", boom)

    response = TestClient(app).get("/boom")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}
    }


def test_a_database_that_is_down_during_upload_is_internal_error(
    settings: Settings, tmp_path: Path
) -> None:
    # No tables: the INSERT fails the way a missing or unreachable database does.
    runs_root = tmp_path / "runs"
    settings = settings.model_copy(update={"runs_dir": runs_root})
    app = create_app(settings, engine=create_engine("sqlite://"))
    client = TestClient(app)

    response = client.post("/api/runs", files={"file": ("a.csv", b"a,b\n1,2\n", "text/csv")})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert list(runs_root.iterdir()) == []  # the file was removed with the failed row


def test_the_internal_error_envelope_carries_the_cors_headers(settings: Settings) -> None:
    # A 500 answered outside the CORS middleware would reach the browser as an
    # opaque network failure: the frontend (another origin) could not read the envelope.
    app = create_app(settings)

    def boom() -> None:
        raise RuntimeError("anything")

    app.add_api_route("/boom", boom)
    origin = settings.allowed_origins[0]

    response = TestClient(app).get("/boom", headers={"Origin": origin})

    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == origin
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"


def test_an_unexpected_exception_is_logged_for_the_operator(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    app = create_app(settings)

    def boom() -> None:
        raise RuntimeError("the reason an operator needs")

    app.add_api_route("/boom", boom)

    with caplog.at_level("ERROR"):
        TestClient(app).get("/boom")

    assert "the reason an operator needs" in caplog.text
