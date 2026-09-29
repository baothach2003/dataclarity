"""`python -m stages.report --run <run_id> [--source-file <name>] [--runs-dir <dir>]`
(session 5D): stage 5 on its own, with no backend and no database - the
stage's independence, proved by running it (CLAUDE.md 3.1).

What only the backend knows comes from the caller or from the backend's own
sources, read here without importing it (SPECS SEC-4):
- RUNS_DIR and STRATEGY_AI_ENABLED are read with pydantic-settings - the
  library, the repo root's `.env` and the rules the backend's Settings use
  (case, quotes, comments; the environment first; input never echoed) - a
  relative RUNS_DIR anchored at the repo root, as the backend anchors it;
  unset, the AI step is off (v1's default). `--runs-dir` overrides RUNS_DIR (a
  relative path from the current directory).
- The uploaded file's name is the database's: `--source-file`, a bare file
  name, or else the name the run's report.json already holds (the backend's).
Both files are written by `build_run`, the one way the backend writes them
too: both or neither within the process. Known limits (8D "From 5D"): the
CLI takes no part in the server's one piece of work per run, nor in another
CLI's - never run it on a run something else is working on.
"""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

import contracts
from contracts._base import ContractFile
from contracts.cleaning import CleaningPlanContract
from shared.run_registry import InvalidRunIdError, RunNotFoundError, run_file
from stages.report.builder import ReportMismatchError, build_run

REPO_ROOT = Path(__file__).resolve().parents[2]
DOTENV = REPO_ROOT / ".env"
USAGE_ERROR, FAILED = 2, 1
# The step that writes each file the report is built from.
_FIRST = {"metrics.json": "run the analysis first", "diagnosis.json": "run the diagnosis first",
          "forecast.json": "run the prediction first", "cleaning_report.json": "run the cleaning first"}
_FILES = {name: model.filename for name in contracts.__all__
          if isinstance(model := getattr(contracts, name), type) and issubclass(model, ContractFile)}
_FILES[CleaningPlanContract.__name__] = "plan_proposed.json"  # the one of its two files the report reads


class UsageError(Exception):
    pass


class _Sources(BaseSettings):
    """The two backend settings stage 5 needs, read as the backend reads
    them (backend/app/config.py) - never by importing it."""

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore", hide_input_in_errors=True)

    runs_dir: Path | None = None
    strategy_ai_enabled: bool = False


def _sources() -> _Sources:
    try:
        return _Sources(_env_file=DOTENV)  # type: ignore[call-arg]  # pydantic-settings' own init argument
    except ValidationError as error:
        problem = error.errors()[0]
        raise UsageError(f"{str(problem['loc'][0]).upper()}: {problem['msg']}") from None


def _runs_root(given: str | None, sources: _Sources) -> Path:
    if given is not None:
        if not given.strip():
            raise UsageError("--runs-dir is empty")
        return Path(given).resolve()
    if sources.runs_dir is None:
        raise UsageError("give --runs-dir, or set RUNS_DIR (as the backend's .env does)")
    root = sources.runs_dir
    return root if root.is_absolute() else REPO_ROOT / root


def _source_file(given: str | None, runs_root: Path, run_id: str) -> str:
    """A bare file name - the page is shared, a path would publish the
    caller's folders (5D review 2 #5) - or the backend's, from the run's
    report.json."""
    if given is None:
        try:
            held = json.loads(run_file(runs_root, run_id, "report.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            held = None
        name = held.get("source_file") if isinstance(held, dict) else None
        if not isinstance(name, str):
            raise UsageError("give --source-file: the uploaded file's name (this run has no report.json to take it "
                             "from)")
        return name
    if not given.strip() or given != Path(given).name or "/" in given or "\\" in given:
        raise UsageError("--source-file must be the uploaded file's bare name, not a path")
    return given


def _say(text: str, stream: TextIO) -> None:
    """A path may hold what the console's code page cannot, and a closed
    pipe cannot take anything: neither fails a run that succeeded (5D
    reviews #6, 2 #9)."""
    encoding = stream.encoding or "utf-8"
    try:
        stream.write(text.encode(encoding, "backslashreplace").decode(encoding) + "\n")
        stream.flush()
    except OSError:
        # The Python documentation's recipe: send what is left to devnull,
        # so the interpreter's own flush at exit fails nothing either.
        os.dup2(os.open(os.devnull, os.O_WRONLY), stream.fileno())


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m stages.report",
                                     description="Build report.json and report.html for one run.")
    parser.add_argument("--run", required=True, help="the run's id (a UUID)")
    parser.add_argument("--source-file", help="the uploaded file's name (default: the one the run's report.json "
                                              "holds)")
    parser.add_argument("--runs-dir", help="the directory holding the runs (default: RUNS_DIR, as the backend)")
    return parser


def _problem(error: ValidationError) -> str:
    problem = error.errors()[0]
    where = ".".join(str(part) for part in problem["loc"])
    return f"{_FILES.get(error.title) or error.title} cannot be read: {where + ': ' if where else ''}{problem['msg']}"


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        sources = _sources()
        runs_root = _runs_root(args.runs_dir, sources)
        source_file = _source_file(args.source_file, runs_root, args.run)
        build_run(runs_root, args.run, source_file=source_file, include_recommendations=sources.strategy_ai_enabled)
    except (UsageError, InvalidRunIdError) as error:
        _say(f"error: {error}", sys.stderr)
        return USAGE_ERROR
    except FileNotFoundError as error:
        name = Path(str(error.filename)).name
        _say(f"error: this run has no {name}: {_FIRST[name]}" if name in _FIRST else f"error: {error}", sys.stderr)
        return FAILED
    except ReportMismatchError as error:
        _say(f"error: the run's files do not describe the same months: {error}", sys.stderr)
        return FAILED
    except ValidationError as error:
        # Another version's file (the contract's own words say what to do:
        # run that stage again, or upload the file again), or a damaged one.
        _say(f"error: {_problem(error)}", sys.stderr)
        return FAILED
    except (RunNotFoundError, OSError, ValueError) as error:
        _say(f"error: {error}", sys.stderr)
        return FAILED
    folder = run_file(runs_root, args.run, "report.json").parent
    _say(f"wrote {folder / 'report.json'}\nwrote {folder / 'report.html'}", sys.stdout)
    return 0
