"""Session 3G-lite review 2 (fresh context, 2026-09-29): the services' new
functions, unit by unit, and the order in which a re-run replaces a run's
files - written before the fixes.

#1 the later outputs were removed AFTER the new file was written: a removal
   that failed left new metrics beside an old diagnosis, and a 500.
#4 `too_large_to_add`, `amounts_too_large` and `later_outputs.set_aside` had
   no unit test; an analysis that fails must remove nothing; an analysis
   during a diagnosis is refused.
#5 the "too large" test matched "finite" anywhere - a product called
   "Infinite Scarf" quoted in a refusal made a bug look like the user's data.
"""

import threading
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from pydantic import BaseModel, ValidationError, field_validator

from app.models import RunStatus
from app.services import later_outputs, stage_errors
from contracts.lines import TOO_LARGE_TO_ADD
from shared.run_registry import create_run
from tests.backend.api_support import MakeApi, make_api_with_plan


class _Refused(BaseModel):
    value: str

    @field_validator("value")
    @classmethod
    def _as_said(cls, value: str) -> str:
        raise ValueError(value)


def _refusal(message: str) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        _Refused(value=message)
    return caught.value


def test_too_large_to_add_is_the_markers_refusal_only() -> None:
    assert stage_errors.too_large_to_add(_refusal(f"{TOO_LARGE_TO_ADD}: JSON cannot carry it"))
    assert stage_errors.too_large_to_add(_refusal(f"core.revenue_by_month[0].revenue: {TOO_LARGE_TO_ADD} (inf)"))
    assert stage_errors.too_large_to_add(_refusal(f"{TOO_LARGE_TO_ADD}: factor 'price_per_unit' must carry finite "
                                                  "figures"))
    # User text quoted in another refusal is never the marker (#5).
    assert not stage_errors.too_large_to_add(_refusal(
        "suggested_classes marks products this file does not name: ['Infinite Scarf']"))
    assert not stage_errors.too_large_to_add(_refusal(
        f"suggested_classes marks products this file does not name: ['{TOO_LARGE_TO_ADD}']"))


def test_amounts_too_large_says_which_stage_could_not_compute() -> None:
    analysis, diagnosis = stage_errors.amounts_too_large(2), stage_errors.amounts_too_large(3)
    assert (analysis.code, analysis.details) == (diagnosis.code, diagnosis.details) == (
        "ANALYSIS_FAILED", {"reason": "amounts_too_large"})
    assert "metrics" in analysis.message and "diagnosis" in diagnosis.message
    assert all("upload it again" in answer.message for answer in (analysis, diagnosis))


def _run_with(tmp_path: Path, names: list[str]) -> tuple[str, Path]:
    run = create_run(tmp_path)
    for name in names:
        (run.path / name).write_text("{}", encoding="utf-8")
    return run.run_id, run.path


def test_set_aside_removes_every_later_output_once_the_block_succeeds(tmp_path: Path) -> None:
    every = ["metrics.json", "diagnosis.json", "forecast.json", "report.json", "report.html", "cleaned.csv"]
    run_id, path = _run_with(tmp_path, every)
    with later_outputs.set_aside(tmp_path, run_id, after_stage=3):
        # Moved aside, not yet gone: nothing reads a ".aside-" file.
        assert sorted(p.name for p in path.iterdir() if not p.name.startswith(".aside-")) == [
            "cleaned.csv", "diagnosis.json", "metrics.json"]
    assert sorted(p.name for p in path.iterdir()) == ["cleaned.csv", "diagnosis.json", "metrics.json"]
    with later_outputs.set_aside(tmp_path, run_id, after_stage=2):
        pass
    assert sorted(p.name for p in path.iterdir()) == ["cleaned.csv", "metrics.json"]
    with later_outputs.set_aside(tmp_path, run_id, after_stage=2):  # nothing left to set aside: no error
        pass


def test_set_aside_puts_every_file_back_when_the_block_fails(tmp_path: Path) -> None:
    # DEMO review #2: a failed rename must lose nothing.
    names = ["metrics.json", "diagnosis.json", "forecast.json", "report.json", "report.html"]
    run_id, path = _run_with(tmp_path, names)
    with pytest.raises(PermissionError), later_outputs.set_aside(tmp_path, run_id, after_stage=2):
        raise PermissionError("the rename failed")
    assert sorted(p.name for p in path.iterdir()) == sorted(names)


def test_set_aside_puts_back_what_it_moved_when_a_move_fails(tmp_path: Path,
                                                              monkeypatch: pytest.MonkeyPatch) -> None:
    names = ["diagnosis.json", "forecast.json", "report.json", "report.html"]
    run_id, path = _run_with(tmp_path, names)
    real = later_outputs.os.replace

    def replace(source: object, destination: object) -> None:
        if Path(str(source)).name == "forecast.json":
            raise PermissionError("forecast.json is open in another program")
        real(source, destination)

    monkeypatch.setattr(later_outputs.os, "replace", replace)
    with pytest.raises(PermissionError), later_outputs.set_aside(tmp_path, run_id, after_stage=2):
        pass
    assert sorted(p.name for p in path.iterdir()) == sorted(names)


def _diagnosed_run(make_api: MakeApi) -> tuple[Any, str]:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    assert api.post(run_id, "analyze").status_code == 200
    assert api.post(run_id, "diagnose").status_code == 200
    return api, run_id


def test_a_removal_that_fails_writes_no_new_metrics(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    # #1: the new metrics are written only once the stale files are gone.
    api, run_id = _diagnosed_run(make_api)
    before = api.file(run_id, "metrics.json").read_bytes()

    def locked(*_args: Any, **_kwargs: Any) -> None:
        raise PermissionError("diagnosis.json is open in another program")

    monkeypatch.setattr(later_outputs, "set_aside", locked)
    response = api.post(run_id, "analyze")

    assert response.status_code == 500
    assert api.file(run_id, "metrics.json").read_bytes() == before
    assert "diagnosis.json" in api.files(run_id)


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
def test_an_analysis_that_fails_removes_nothing(make_api: MakeApi) -> None:
    # SPECS 10: ANALYSIS_FAILED writes nothing and leaves the run as it was.
    api, run_id = _diagnosed_run(make_api)
    diagnosis = api.file(run_id, "diagnosis.json").read_bytes()
    cleaned = api.file(run_id, "cleaned.csv")
    frame = pd.read_csv(cleaned, dtype=str)
    sales = frame.index[frame["line_class"].eq("sale")][:2]
    frame.loc[sales, "qty"], frame.loc[sales, "price"] = "1", "1e308"
    frame.to_csv(cleaned, index=False)

    response = api.post(run_id, "analyze")

    assert (response.status_code, response.json()["error"]["details"]) == (422, {"reason": "amounts_too_large"})
    assert api.file(run_id, "diagnosis.json").read_bytes() == diagnosis


def test_an_analysis_during_a_diagnosis_is_refused(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    api, run_id = _diagnosed_run(make_api)
    from stages.diagnose import assemble

    real = assemble.diagnose_run
    inside, proceed = threading.Event(), threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        inside.set()
        assert proceed.wait(timeout=10), "the test never released the diagnosis"
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.diagnosis.diagnose_run", slow)
    first: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: first.update(response=api.post(run_id, "diagnose")))
    worker.start()
    assert inside.wait(timeout=10)

    during = api.post(run_id, "analyze")
    proceed.set()
    worker.join(timeout=20)

    assert during.status_code == 409 and during.json()["error"]["details"]["reason"] == "step_in_progress"
    assert first["response"].status_code == 200
    assert api.status(run_id) is RunStatus.ANALYZED


class _TwoRefused(BaseModel):
    first: str
    second: str

    @field_validator("first", "second")
    @classmethod
    def _as_said(cls, value: str) -> str:
        raise ValueError(value)


def test_too_large_to_add_needs_every_problem_to_be_the_marker() -> None:
    # A refusal of two problems, one of them anything else, is a bug (review 2 #4).
    with pytest.raises(ValidationError) as caught:
        _TwoRefused(first=f"{TOO_LARGE_TO_ADD}: a sum", second="factor 'x' is unknown")
    assert not stage_errors.too_large_to_add(caught.value)
