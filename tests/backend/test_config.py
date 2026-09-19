from pathlib import Path

import pytest

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
