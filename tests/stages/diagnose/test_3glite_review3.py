"""Session 3G-lite review 3 (fresh context, 2026-09-29) - the order a stage
run again replaces a run's files, at both stages, and which refusals are the
user's amounts.

#1 stage 3's order was pinned by no test (two mutants survived the suite).
#2 the later outputs were removed before the new file was serialised and
   staged: a failure after the removal deleted them and wrote nothing. Now
   the new bytes are on disk first, the removal runs, then the rename.
#3 a NaN with no infinity comes from the code, never the user's amounts: it
   stays a bug (a 500), unmarked.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from contracts.diagnosis import Calendar, DiagnosisContract
from contracts.lines import TOO_LARGE_TO_ADD, refused_as_too_large
from shared.contract_files import write_atomically
from stages.analyze.assemble import analyze_run
from stages.diagnose.assemble import DIAGNOSIS_FILENAME, diagnose, diagnose_run
from tests.stages.diagnose.test_3glite_assemble import NOW, _run_on_disk, _steady_with_a_drop
from tests.stages.diagnose.diagnose_fixtures import run_data

LATER = "forecast.json"


def _diagnosed(tmp_path: Path) -> tuple[str, Path]:
    run_id = _run_on_disk(tmp_path, _steady_with_a_drop())
    diagnose_run(tmp_path, run_id, NOW)
    (tmp_path / run_id / LATER).write_text("{}", encoding="utf-8")
    return run_id, tmp_path / run_id


def _staged(path: Path) -> list[str]:
    return [p.name for p in path.iterdir() if p.name.startswith(".stage-")]


@pytest.mark.parametrize("stage", ["analyze", "diagnose"])
def test_the_removal_runs_once_the_new_file_is_staged_before_it_replaces_the_old(tmp_path: Path, stage: str) -> None:
    run_id, path = _diagnosed(tmp_path)
    target = path / ("metrics.json" if stage == "analyze" else DIAGNOSIS_FILENAME)
    before = target.read_bytes()
    seen: dict[str, object] = {}

    def remove() -> None:
        seen.update(staged=_staged(path), old=target.read_bytes() == before)
        (path / LATER).unlink()

    later = datetime(2026, 9, 30, tzinfo=UTC)
    if stage == "analyze":
        analyze_run(tmp_path, run_id, later, before_write=remove)
    else:
        diagnose_run(tmp_path, run_id, later, before_write=remove)

    assert seen["old"] is True and len(seen["staged"]) == 1  # type: ignore[arg-type]  # a list of names
    assert target.read_bytes() != before and not (path / LATER).exists() and _staged(path) == []


@pytest.mark.parametrize("stage", ["analyze", "diagnose"])
def test_a_removal_that_fails_leaves_every_file_as_it_was(tmp_path: Path, stage: str) -> None:
    run_id, path = _diagnosed(tmp_path)
    files = {p.name: p.read_bytes() for p in path.iterdir()}

    def locked() -> None:
        raise PermissionError("forecast.json is open in another program")

    with pytest.raises(PermissionError):
        if stage == "analyze":
            analyze_run(tmp_path, run_id, datetime(2026, 9, 30, tzinfo=UTC), before_write=locked)
        else:
            diagnose_run(tmp_path, run_id, datetime(2026, 9, 30, tzinfo=UTC), before_write=locked)

    assert {p.name: p.read_bytes() for p in path.iterdir()} == files


def test_a_diagnosis_that_fails_to_compute_removes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id, path = _diagnosed(tmp_path)
    removed: list[str] = []

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("a step failed")

    monkeypatch.setattr("stages.diagnose.assemble.evaluate_hypotheses", broken)
    with pytest.raises(RuntimeError):
        diagnose_run(tmp_path, run_id, NOW, before_write=lambda: removed.append("called"))
    assert removed == [] and (path / LATER).exists()


def test_write_atomically_runs_the_hook_between_the_staged_bytes_and_the_rename(tmp_path: Path) -> None:
    target = tmp_path / "x.json"
    target.write_bytes(b"old")
    seen: list[tuple[list[str], bytes]] = []
    write_atomically(target, b"new", before_replace=lambda: seen.append((_staged(tmp_path), target.read_bytes())))
    assert len(seen) == 1 and len(seen[0][0]) == 1 and seen[0][1] == b"old"
    assert target.read_bytes() == b"new" and _staged(tmp_path) == []


def _calendar(**figures: float) -> dict:
    return {"method": "weekday_weights", "expected_cur": 10.0, "expected_prev": 10.0, "calendar_effect": 0.0,
            "calendar_adjusted_change": 0.0, "evidence": {}} | figures


def _refusal(model: type, payload: dict) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload)
    return caught.value


def test_an_infinity_is_too_large_to_add_a_nan_alone_is_a_bug() -> None:
    assert refused_as_too_large(_refusal(Calendar, _calendar(calendar_effect=float("inf"))))
    nan_only = _refusal(Calendar, _calendar(calendar_effect=float("nan")))
    assert not refused_as_too_large(nan_only)
    assert TOO_LARGE_TO_ADD not in str(nan_only)


def test_the_diagnosis_files_whole_check_tells_a_nan_from_an_infinity() -> None:
    written = diagnose(run_data(_steady_with_a_drop()), NOW).model_dump(mode="python")
    share = next(i for i, h in enumerate(written["hypotheses"]) if h["contribution"] is not None)
    written["hypotheses"][share]["contribution"] = float("nan")
    nan_only = _refusal(DiagnosisContract, written)
    assert not refused_as_too_large(nan_only) and "from the code" in str(nan_only)
    written["hypotheses"][share]["contribution"] = float("-inf")
    assert refused_as_too_large(_refusal(DiagnosisContract, written))


def test_the_contracts_example_note_is_one_the_contract_reads() -> None:
    # Review 3 #4: CONTRACTS section 6's example note carried one measure.
    from contracts.lines import FigureNote

    text = (Path(__file__).resolve().parents[3] / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    start = text.index('{"code": "same_day_cancellations",')
    example = text[start:text.index('"always_on": false}', start) + len('"always_on": false}')]
    note = json.loads(example.replace('"text": "Returns and the return rate include same-day cancellations, which '
                                      'the data cannot separate: ..."', '"text": "..."'))
    assert FigureNote.model_validate(note).always_on is False
