"""Session 5D: the CLI's failures - each a message and an exit code, never
a traceback - the pair of files kept whole, and the output that never fails
a run that succeeded (reviews 1 and 2)."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from stages.report import builder, cli
from stages.report.cli import main
from tests.stages.report.report_fixtures import RUN, run_dir
from tests.stages.report.test_5d_cli import ROOT, _args, _report


@pytest.fixture(autouse=True)
def _no_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "DOTENV", tmp_path / "no.env")


def _damage(run: Path, problem: str) -> None:
    def rewrite(name: str, change: dict) -> None:  # type: ignore[type-arg]  # any JSON object
        data = json.loads((run / name).read_text(encoding="utf-8"))
        (run / name).write_text(json.dumps(data | change), encoding="utf-8")

    if problem == "no forecast":
        (run / "forecast.json").unlink()
    elif problem == "no diagnosis":
        (run / "diagnosis.json").unlink()
    elif problem == "other months":
        data = json.loads((run / "diagnosis.json").read_text(encoding="utf-8"))
        data["frame"] |= {"current": "2011-08", "previous": "2011-07"}
        (run / "diagnosis.json").write_text(json.dumps(data), encoding="utf-8")
    elif problem == "another version":
        rewrite("forecast.json", {"schema_version": "9.0"})
    elif problem == "damaged":
        (run / "forecast.json").write_text('{"schema_version": "1.0", "forecast"', encoding="utf-8")
    elif problem == "optional not JSON":
        (run / "plan_proposed.json").write_text("not json", encoding="utf-8")
    elif problem == "plan damaged":
        data = json.loads((run / "plan_proposed.json").read_text(encoding="utf-8"))
        del data["source"]
        (run / "plan_proposed.json").write_text(json.dumps(data), encoding="utf-8")
    elif problem == "not UTF-8":
        (run / "metrics.json").write_bytes(b'{"schema_version": "caf\xe9"}')
    elif problem == "a field missing":
        data = json.loads((run / "forecast.json").read_text(encoding="utf-8"))
        del data["forecast"]
        (run / "forecast.json").write_text(json.dumps(data), encoding="utf-8")


@pytest.mark.parametrize("problem,run_id,code,said", [
    ("unknown run", "00000000-0000-4000-8000-000000000000", 1, "no run directory"),
    ("not a run id", "../etc", 2, "not a UUID"),
    ("no forecast", RUN, 1, "this run has no forecast.json: run the prediction first"),
    ("no diagnosis", RUN, 1, "this run has no diagnosis.json: run the diagnosis first"),
    ("other months", RUN, 1, "run the diagnosis again"),
    ("another version", RUN, 1, "forecast.json cannot be read: schema_version: Value error, unsupported major version"),
    ("damaged", RUN, 1, "forecast.json cannot be read: Invalid JSON"),
    ("optional not JSON", RUN, 1, "error: plan_proposed.json cannot be read: it is not a JSON file"),
    ("a field missing", RUN, 1, "forecast.json cannot be read: forecast: Field required"),
    ("plan damaged", RUN, 1, "plan_proposed.json cannot be read: source: Field required"),
    ("not UTF-8", RUN, 1, "metrics.json is not UTF-8 text"),
])
def test_every_failure_is_a_message_and_an_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str], problem: str,
                                                      run_id: str, code: int, said: str) -> None:
    run = run_dir(tmp_path)
    _damage(run, problem)

    assert main(["--run", run_id, "--runs-dir", str(tmp_path), "--source-file", "sales.csv"]) == code

    err = capsys.readouterr().err
    assert said in err and "Traceback" not in err
    assert not (run / "report.json").exists() and not (run / "report.html").exists()


def test_a_page_that_fails_leaves_the_previous_pair_whole(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 5D review #2: both files or neither, as the backend writes them.
    run = run_dir(tmp_path)

    def refused(*args: object, **kwargs: object) -> None:
        raise PermissionError("report.html is locked")

    monkeypatch.setattr(builder, "html_run", refused)
    assert main(_args(tmp_path)) == 1
    assert not {"report.json", "report.html"} & {p.name for p in run.iterdir()}
    monkeypatch.undo()
    monkeypatch.setattr(cli, "DOTENV", tmp_path / "no.env")
    assert main(_args(tmp_path)) == 0
    before = {name: (run / name).read_bytes() for name in ("report.json", "report.html")}
    monkeypatch.setattr(builder, "html_run", refused)
    assert main(["--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "other.csv"]) == 1
    assert {name: (run / name).read_bytes() for name in ("report.json", "report.html")} == before
    assert not [p.name for p in run.iterdir() if p.name.startswith(".aside-")]


def _fresh(*args: str, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if key not in ("RUNS_DIR", "PYTHONIOENCODING")}
    env |= extra_env or {}
    return subprocess.run([sys.executable, *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def test_python_m_stages_report_runs_without_the_backend(tmp_path: Path) -> None:
    # The stage's independence, proved by running it in a fresh interpreter,
    # and nothing of the backend loaded - after a run, not only an import.
    run = run_dir(tmp_path)
    done = _fresh("-m", "stages.report", "--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "sales.csv")
    assert done.returncode == 0, done.stderr
    assert (run / "report.html").exists()
    probe = _fresh("-c", "import sys; from stages.report.cli import main; code = main(['--run', '" + RUN + "', "
                   "'--runs-dir', r'" + str(tmp_path) + "', '--source-file', 'sales.csv']); print(code, sorted({m.split("
                   "'.')[0] for m in sys.modules} & {'app', 'backend', 'fastapi', 'sqlalchemy', 'anthropic'}))")
    assert probe.stdout.strip().splitlines()[-1] == "0 []", probe.stderr
    imported = _fresh("-c", "import stages.report.__main__")  # 5D review #9: an import never exits
    assert imported.returncode == 0, imported.stderr


def test_a_path_the_console_cannot_encode_never_fails_a_run(tmp_path: Path) -> None:
    # 5D review #6: a Vietnamese folder name on a cp1252 console.
    runs = tmp_path / "Thạch runs"
    runs.mkdir()
    run = run_dir(runs)
    done = _fresh("-m", "stages.report", "--run", RUN, "--runs-dir", str(runs), "--source-file", "sales.csv",
                  extra_env={"PYTHONIOENCODING": "cp1252"})
    assert done.returncode == 0, done.stderr
    assert (run / "report.html").exists() and "\\u1ea1" in done.stdout


def test_a_rebuild_over_a_previous_pair_leaves_nothing_aside(tmp_path: Path) -> None:
    run = run_dir(tmp_path)
    assert main(_args(tmp_path)) == 0
    assert main(["--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "other.csv"]) == 0
    assert _report(run).source_file == "other.csv"
    assert not [p.name for p in run.iterdir() if p.name.startswith(".aside-")]


def test_a_set_aside_that_fails_leaves_the_previous_pair_where_it_was(tmp_path: Path) -> None:
    # 5D review 2 #1: the one set-aside the backend uses - a move that fails
    # moves nothing back wrong and deletes nothing.
    run = run_dir(tmp_path)
    assert main(_args(tmp_path)) == 0
    before = {name: (run / name).read_bytes() for name in ("report.json", "report.html")}
    (run / ".aside-report.json").mkdir()  # the move of report.json cannot land

    assert main(["--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "other.csv"]) == 1

    assert {name: (run / name).read_bytes() for name in ("report.json", "report.html")} == before
    assert not (run / ".aside-report.html").exists()


def test_a_set_aside_file_it_cannot_delete_never_fails_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 5D review 2 #2: logged, as the backend does (4A review 1 #14).
    run = run_dir(tmp_path)
    assert main(_args(tmp_path)) == 0
    real = Path.unlink

    def refuse_asides(self: Path, missing_ok: bool = False) -> None:
        if self.name.startswith(".aside-"):
            raise PermissionError(f"{self.name} is held by another program")
        real(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", refuse_asides)
    assert main(["--run", RUN, "--runs-dir", str(tmp_path), "--source-file", "other.csv"]) == 0
    assert _report(run).source_file == "other.csv"


def test_a_closed_output_never_fails_a_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # 5D review 2 #9: the success message has nowhere to go - the run stands.
    import io

    run = run_dir(tmp_path)
    sink = os.open(os.devnull, os.O_WRONLY)

    class Closed(io.StringIO):
        encoding = "utf-8"

        def write(self, text: str) -> int:
            raise OSError(22, "Invalid argument")

        def fileno(self) -> int:
            return sink

    monkeypatch.setattr(sys, "stdout", Closed())
    try:
        assert main(_args(tmp_path)) == 0
    finally:
        os.close(sink)
    assert (run / "report.html").exists()


def test_a_missing_file_that_is_not_an_input_gets_no_step_to_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                 capsys: pytest.CaptureFixture[str]) -> None:
    # 5D review 2 #8: another CLI run's set-aside took report.json away - the
    # earlier stages are not to blame.
    run = run_dir(tmp_path)

    def gone(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError(2, "No such file or directory", str(run / "report.json"))

    monkeypatch.setattr(cli, "build_run", gone)
    assert main(_args(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "No such file or directory" in err and "report.json" in err and "this run has no" not in err
