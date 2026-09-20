from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import REPO_ROOT, Settings


def test_relative_runs_dir_resolves_against_repo_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Start "the process" somewhere else: the result must not follow the cwd.
    monkeypatch.chdir(tmp_path)

    settings = Settings(_env_file=None, runs_dir="runs")  # type: ignore[call-arg]  # remaining fields come from env

    assert settings.runs_dir == REPO_ROOT / "runs"
    assert settings.runs_dir.is_absolute()


def test_nested_relative_runs_dir_resolves_against_repo_root() -> None:
    settings = Settings(_env_file=None, runs_dir="data/runs")  # type: ignore[call-arg]  # remaining fields come from env

    assert settings.runs_dir == REPO_ROOT / "data" / "runs"


def test_absolute_runs_dir_is_kept(tmp_path: Path) -> None:
    settings = Settings(_env_file=None, runs_dir=str(tmp_path))  # type: ignore[call-arg]  # remaining fields come from env

    assert settings.runs_dir == tmp_path


def test_test_settings_keep_runs_outside_the_repo(settings: Settings) -> None:
    # Guards tests/conftest.py: runs created in tests must never land in runs/.
    assert settings.runs_dir.is_absolute()
    assert REPO_ROOT not in settings.runs_dir.parents


# SEC-1: MAX_UPLOAD_MB must be a positive integer no greater than the 50MB
# design ceiling (SPECS section 1), or the app refuses to start.


@pytest.mark.parametrize("value", ["0", "51", "-1"])
def test_max_upload_mb_outside_1_to_50_stops_startup(value: str) -> None:
    with pytest.raises(ValidationError, match="max_upload_mb"):
        Settings(_env_file=None, max_upload_mb=value)  # type: ignore[call-arg]  # remaining fields come from env


@pytest.mark.parametrize("value", [1, 50])
def test_max_upload_mb_accepts_the_edges_of_the_range(value: int) -> None:
    settings = Settings(_env_file=None, max_upload_mb=value)  # type: ignore[call-arg]  # remaining fields come from env

    assert settings.max_upload_mb == value


@pytest.mark.parametrize("key", ["", "   "])
def test_an_empty_anthropic_api_key_stops_startup(key: str) -> None:
    # An empty key would crash the SDK while building the request instead of
    # taking the degraded path; refuse it where every other setting is checked.
    with pytest.raises(ValidationError, match="anthropic_api_key"):
        Settings(_env_file=None, anthropic_api_key=key)  # type: ignore[call-arg]  # remaining fields come from env


def test_the_api_key_is_stored_without_surrounding_whitespace() -> None:
    settings = Settings(_env_file=None, anthropic_api_key="  sk-ant-test\n")  # type: ignore[call-arg]  # remaining fields come from env

    assert settings.anthropic_api_key.get_secret_value() == "sk-ant-test"
