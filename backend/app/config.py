"""Application settings, loaded from environment variables and the repo-root `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Resolved from this file rather than the working directory, so the same `.env`
# is found whether uvicorn is started from `backend/` or pytest from the repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration.

    No field has a default on purpose: a missing variable should stop the app at
    startup, not surface later as a wrong model id or an open CORS policy.
    """

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # Validation errors would otherwise echo the input, API key included, into logs.
        hide_input_in_errors=True,
    )

    anthropic_api_key: SecretStr
    database_url: str
    # NoDecode: the env value is a plain comma-separated string, not JSON.
    allowed_origins: Annotated[list[str], NoDecode]
    model_reasoning: str
    model_bulk: str
    max_upload_mb: int
    runs_dir: Path
    retention_hours: int

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    # Cached so `.env` is parsed once per process; tests build Settings directly.
    return Settings()  # type: ignore[call-arg]  # values come from env, not kwargs
