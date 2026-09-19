from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_returns_ok(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
