"""Application settings, loaded from environment variables and the repo-root `.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Resolved from this file rather than the working directory, so the same `.env`
# is found whatever directory the server or pytest is started from.
REPO_ROOT = Path(__file__).resolve().parents[2]

# The design ceiling from SPECS section 1: synchronous processing is only sized
# for files up to this. MAX_UPLOAD_MB may lower the limit, never raise it.
MAX_UPLOAD_MB_CEILING = 50


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
    max_upload_mb: Annotated[int, Field(gt=0, le=MAX_UPLOAD_MB_CEILING)]
    runs_dir: Path
    retention_hours: int

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("anthropic_api_key")
    @classmethod
    def key_is_not_empty(cls, value: SecretStr) -> SecretStr:
        # "Required" alone lets ANTHROPIC_API_KEY= through; the SDK then crashes
        # while building a request instead of taking the degraded path.
        key = value.get_secret_value().strip()
        if not key:
            raise ValueError("must not be empty")
        # Stored trimmed: a quoted .env value or a trailing newline would
        # otherwise reach the API as part of the key and come back as a 401.
        return SecretStr(key)

    @field_validator("runs_dir")
    @classmethod
    def anchor_runs_dir(cls, value: Path) -> Path:
        # A relative RUNS_DIR means relative to the repo, like `.env` above; left
        # alone it would follow whatever directory the process started in.
        return value if value.is_absolute() else REPO_ROOT / value


@lru_cache
def get_settings() -> Settings:
    # Cached so `.env` is parsed once per process; tests build Settings directly.
    return Settings()  # type: ignore[call-arg]  # values come from env, not kwargs
