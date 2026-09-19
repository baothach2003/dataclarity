from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ApiError
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
