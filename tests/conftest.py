import os

import pytest

# Set before any test module imports `app.main`, whose module-level `app` reads
# settings at import time. Environment variables take precedence over `.env`, so
# a developer's real API key is never picked up by the test suite.
TEST_ENV = {
    "ANTHROPIC_API_KEY": "test-key-not-real",
    "DATABASE_URL": "postgresql://test:test@localhost:5432/cleanstock_test",
    "ALLOWED_ORIGINS": "http://localhost:5173",
    "MODEL_REASONING": "test-model-reasoning",
    "MODEL_BULK": "test-model-bulk",
    "MAX_UPLOAD_MB": "50",
    "RUNS_DIR": "runs",
    "RETENTION_HOURS": "24",
}
os.environ.update(TEST_ENV)

from app.config import Settings  # noqa: E402  # must follow the env setup above


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None)  # type: ignore[call-arg]  # values come from env
