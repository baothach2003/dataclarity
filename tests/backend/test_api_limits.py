"""GET /api/limits (PROJECT_PLAN 6A, decided alone 2026-10-04): the Upload
page's size check learns the server's MAX_UPLOAD_MB from the server itself -
one source of truth for a number that can differ per deployment (SEC-1: it may
only lower SPECS' 50 MB ceiling). Written before the endpoint."""

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.config import Settings
from app.main import create_app
from app.models import Base
from tests.backend.api_support import MakeApi


def test_the_client_is_told_the_servers_own_limit(make_api: MakeApi) -> None:
    api = make_api()  # the test app's MAX_UPLOAD_MB is 1

    response = api.client.get("/api/limits")

    assert response.status_code == 200
    assert response.json() == {"max_upload_mb": 1}


def test_a_deployment_with_another_limit_says_that_one(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'limits.db'}")
    Base.metadata.create_all(engine)
    settings = Settings(  # type: ignore[call-arg]  # remaining fields come from env
        _env_file=None, runs_dir=str(tmp_path / "runs"), max_upload_mb=20)
    with TestClient(create_app(settings, engine=engine)) as client:
        assert client.get("/api/limits").json() == {"max_upload_mb": 20}
    engine.dispose()
