from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_allowed_origins_parsed_from_comma_separated_env() -> None:
    settings = Settings(  # type: ignore[call-arg]  # remaining fields come from env
        _env_file=None, allowed_origins="http://a.test, http://b.test"
    )

    assert settings.allowed_origins == ["http://a.test", "http://b.test"]


def test_cors_allows_only_configured_origins(settings: Settings) -> None:
    client = TestClient(create_app(settings))

    allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
    blocked = client.get("/health", headers={"Origin": "http://evil.test"})

    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers
