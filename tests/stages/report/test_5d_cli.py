"""Session 5D: `python -m stages.report --run <id> --source-file <name>` -
stage 5 run on its own, no backend, no database (the stage's independence,
CLAUDE.md 3.1). The runs root and the AI step's switch come from the
backend's own sources (SPECS SEC-4: never by importing it); the file's name
from the caller. Written before the code; widened by its review.
"""

from pathlib import Path

import pytest

from contracts.report import ReportContract
from stages.report import cli
from stages.report.cli import main
from tests.stages.report.report_fixtures import RUN, run_dir

ROOT = Path(__file__).resolve().parents[3]


def _report(run: Path) -> ReportContract:
    return ReportContract.model_validate_json((run / "report.json").read_text(encoding="utf-8"))


def _args(tmp_path: Path, *more: str) -> list[str]:
    return ["--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "sales.csv", *more]


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Never the developer's real .env: each test says what the sources hold.
    monkeypatch.setattr(cli, "DOTENV", tmp_path / "no.env")


def test_the_cli_writes_both_files(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run = run_dir(tmp_path)

    assert main(_args(tmp_path)) == 0

    report = _report(run)
    assert (report.run_id, report.source_file) == (RUN, "sales.csv")
    assert report.layer_3_actions.recommendations_status == "switched_off"  # v1's default
    assert (run / "report.html").read_text(encoding="utf-8").startswith("<!doctype html>")
    out = capsys.readouterr().out
    assert str(run / "report.json") in out and str(run / "report.html") in out


def test_the_uploaded_files_name_is_the_callers_or_the_backends(tmp_path: Path,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    # 5D reviews #1 and 2 #5: report.json names the uploaded file - given by
    # the caller, or the one the run's report.json already holds; never a
    # path (the page is shared) and never empty.
    run = run_dir(tmp_path)
    bare = ["--run", RUN, "--runs-dir", str(tmp_path)]
    assert main(bare) == 2
    assert "give --source-file" in capsys.readouterr().err
    for bad in (" ", "C:\\Clients\\Acme\\sales.csv", "clients/sales.csv"):
        assert main([*bare, "--source-file", bad]) == 2
    assert not (run / "report.json").exists()
    assert main([*bare, "--source-file", "b\u00e1o c\u00e1o.csv"]) == 0
    assert main(bare) == 0
    assert _report(run).source_file == "b\u00e1o c\u00e1o.csv"


@pytest.mark.parametrize("switch", ["true", "FALSE", None])
def test_a_leftover_ai_switch_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, switch: str | None) -> None:
    # Step 4 as option (d): STRATEGY_AI_ENABLED is gone (Q53); a .env or an
    # environment that still holds it changes nothing - no AI writes a recommendation.
    run = run_dir(tmp_path)
    if switch is not None:
        monkeypatch.setenv("STRATEGY_AI_ENABLED", switch)
    assert main(_args(tmp_path)) == 0
    assert _report(run).layer_3_actions.recommendations_status == "switched_off"


def test_a_leftover_switch_carrying_a_secret_is_never_read_nor_echoed(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # 5D review 2 #4: the backend's rule - input never echoed (a merged line
    # may carry a secret); the setting is no longer read at all (Q53).
    run = run_dir(tmp_path)
    monkeypatch.setenv("STRATEGY_AI_ENABLED", "false ANTHROPIC_API_KEY=sk-ant-FAKE-DISTINCTIVE")
    assert main(_args(tmp_path)) == 0
    captured = capsys.readouterr()
    assert "FAKE-DISTINCTIVE" not in captured.err + captured.out
    assert (run / "report.json").exists()


def test_the_runs_root_comes_from_the_backends_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 5D review #3: --runs-dir, else RUNS_DIR from the environment, else from
    # the repo's .env; a relative RUNS_DIR from the repo root, as the backend.
    runs = tmp_path / "runs"
    runs.mkdir()
    run = run_dir(runs)
    source = ["--run", RUN, "--source-file", "sales.csv"]
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "elsewhere"))
    assert main([*source, "--runs-dir", str(runs)]) == 0  # the argument first
    monkeypatch.setenv("RUNS_DIR", str(runs))
    assert main(source) == 0
    monkeypatch.setattr(cli, "REPO_ROOT", tmp_path)
    monkeypatch.setenv("RUNS_DIR", "runs")
    monkeypatch.chdir(runs)  # not the current directory's
    assert main(source) == 0
    monkeypatch.delenv("RUNS_DIR")
    dotenv = tmp_path / ".env"
    # 5D review 2 #3: as pydantic-settings reads it - any case, quotes, a
    # comment after a quoted value.
    dotenv.write_text('# the backend\'s settings\nruns_dir=runs\nStrategy_AI_Enabled="true"  # the demo\n',
                      encoding="utf-8")
    monkeypatch.setattr(cli, "DOTENV", dotenv)
    assert main(source) == 0
    assert _report(run).layer_3_actions.recommendations_status == "switched_off"  # the leftover line ignored


def test_a_relative_runs_dir_argument_is_taken_from_the_current_directory(tmp_path: Path,
                                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    run = run_dir(tmp_path)
    monkeypatch.chdir(tmp_path.parent)
    assert main(["--run", RUN, "--runs-dir", tmp_path.name, "--source-file", "sales.csv"]) == 0
    assert (run / "report.html").exists()


def test_no_runs_root_anywhere_is_a_usage_error(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv("RUNS_DIR", raising=False)
    assert main(["--run", RUN, "--source-file", "sales.csv"]) == 2
    assert "--runs-dir" in capsys.readouterr().err
    # 5D review 2 #7: an empty argument is a mistake, never "use RUNS_DIR".
    monkeypatch.setenv("RUNS_DIR", "somewhere")
    assert main(["--run", RUN, "--runs-dir", "", "--source-file", "sales.csv"]) == 2
    assert "--runs-dir is empty" in capsys.readouterr().err
