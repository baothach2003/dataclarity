import os
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import httpx2
import pytest

# Set before any test module imports `app.main`, whose module-level `app` reads
# settings at import time. Environment variables take precedence over `.env`, so
# a developer's real API key is never picked up by the test suite.
TEST_ENV = {
    "ANTHROPIC_API_KEY": "test-key-not-real",
    # Never a network database: a test that forgets to inject its own engine
    # fails on missing tables instead of reaching a real server.
    "DATABASE_URL": "sqlite://",
    "ALLOWED_ORIGINS": "http://localhost:5173",
    "MODEL_REASONING": "test-model-reasoning",
    "MODEL_BULK": "test-model-bulk",
    "MAX_UPLOAD_MB": "50",
    # Absolute and outside the repo, so no test that creates runs through
    # Settings can ever write into the real, gitignored runs/ folder.
    "RUNS_DIR": str(Path(tempfile.gettempdir()) / "dataclarity-test-runs"),
    "RETENTION_HOURS": "24",
    "PREVIEW_CACHE_MAX_MB": "300",
    "PREVIEW_CACHE_TTL_SECONDS": "900",
}
os.environ.update(TEST_ENV)

from app.config import Settings  # noqa: E402  # must follow the env setup above


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]  # values come from env


# --- CONSTRAINTS F4: no real HTTP call leaves the test suite -----------------


class RealNetworkBlocked(RuntimeError):
    """Raised by the real network transports while tests run."""


@pytest.fixture(autouse=True)
def real_http_attempts(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[str]]:
    """Blocks the real transports of httpx2 (the Anthropic SDK's) and httpx.

    Raising alone is not enough: the SDK or our AI client may catch the error
    and degrade gracefully, and the test would pass. So every attempt is also
    recorded, and the test fails at teardown if any was made. FastAPI's
    TestClient uses its own in-process transport and is not affected.
    """
    attempts: list[str] = []

    def blocked(_transport: object, request: Any) -> Any:
        attempts.append(str(request.url))
        raise RealNetworkBlocked(f"real HTTP call attempted in a test: {request.url}")

    async def blocked_async(_transport: object, request: Any) -> Any:
        return blocked(_transport, request)

    for module in (httpx, httpx2):
        monkeypatch.setattr(module.HTTPTransport, "handle_request", blocked)
        monkeypatch.setattr(module.AsyncHTTPTransport, "handle_async_request", blocked_async)
    yield attempts
    assert not attempts, f"real HTTP calls attempted during this test: {attempts}"
