"""Session 3G-lite review 3 and the DEMO session's review (fresh contexts,
2026-09-29) - the order in which a stage run again replaces a run's files, at
both stages, and which refusals are the user's amounts.

3G-lite review 3 #1-#2: stage 3's order was pinned by no test; the later
outputs were removed before the new file was staged. DEMO review #2: removed
before the rename, they were lost when the rename failed. Now they are SET
ASIDE around the rename (`around_write`): deleted once it succeeds, put back
when anything fails - all or nothing.
DEMO review #1 (superseding 3G-lite review 3 #3): a NaN is an overflow's
trace too - the attribution multiplies amounts past a float and subtracts
inf from inf - so any number JSON cannot carry is the user's amounts, as in
metrics.json (2E-v).
"""

import json
import os
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Iterator

import pytest
from pydantic import ValidationError

from contracts.diagnosis import Calendar, DiagnosisContract
from contracts.lines import TOO_LARGE_TO_ADD, refused_as_too_large
from shared import contract_files
from shared.contract_files import write_atomically
from stages.analyze.assemble import analyze_run
from stages.diagnose.assemble import DIAGNOSIS_FILENAME, diagnose, diagnose_run
from tests.stages.diagnose.diagnose_fixtures import row, run_data
from tests.stages.diagnose.test_3glite_assemble import NOW, _run_on_disk, _steady_with_a_drop

LATER = "forecast.json"
LATER_TIME = datetime(2026, 9, 30, tzinfo=UTC)


def _diagnosed(tmp_path: Path) -> tuple[str, Path]:
    run_id = _run_on_disk(tmp_path, _steady_with_a_drop())
    diagnose_run(tmp_path, run_id, NOW)
    (tmp_path / run_id / LATER).write_text("{}", encoding="utf-8")
    return run_id, tmp_path / run_id


def _staged(path: Path) -> list[str]:
    return [p.name for p in path.iterdir() if p.name.startswith(".stage-")]


def _run(stage: str, tmp_path: Path, run_id: str, around) -> None:
    if stage == "analyze":
        analyze_run(tmp_path, run_id, LATER_TIME, around_write=around)
    else:
        diagnose_run(tmp_path, run_id, LATER_TIME, around_write=around)


def _target(path: Path, stage: str) -> Path:
    return path / ("metrics.json" if stage == "analyze" else DIAGNOSIS_FILENAME)


@pytest.mark.parametrize("stage", ["analyze", "diagnose"])
def test_the_later_outputs_are_set_aside_around_the_rename(tmp_path: Path, stage: str) -> None:
    run_id, path = _diagnosed(tmp_path)
    target = _target(path, stage)
    before = target.read_bytes()
    seen: dict[str, object] = {}

    @contextmanager
    def aside() -> Iterator[None]:
        # Entered once the new bytes are staged, the old file still in place.
        seen.update(staged=len(_staged(path)), old=target.read_bytes() == before)
        (path / LATER).rename(path / f".aside-{LATER}")
        yield
        (path / f".aside-{LATER}").unlink()

    _run(stage, tmp_path, run_id, aside)

    assert seen == {"staged": 1, "old": True}
    assert target.read_bytes() != before and not (path / LATER).exists() and _staged(path) == []


@pytest.mark.parametrize("stage", ["analyze", "diagnose"])
def test_a_rename_that_fails_leaves_every_file_as_it_was(tmp_path: Path, stage: str,
                                                          monkeypatch: pytest.MonkeyPatch) -> None:
    # DEMO review #2: the target held open by another program (Windows).
    from app.services import later_outputs

    run_id, path = _diagnosed(tmp_path)
    files = {p.name: p.read_bytes() for p in path.iterdir()}
    real = os.replace

    def replace(source: object, destination: object) -> None:
        if Path(str(destination)) == _target(path, stage):
            raise PermissionError("the file is open in another program")
        real(source, destination)

    monkeypatch.setattr(contract_files.os, "replace", replace)
    with pytest.raises(PermissionError):
        _run(stage, tmp_path, run_id,
             lambda: later_outputs.set_aside(tmp_path, run_id, after_stage=2 if stage == "analyze" else 3))

    assert {p.name: p.read_bytes() for p in path.iterdir()} == files


def test_a_diagnosis_that_fails_to_compute_touches_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id, path = _diagnosed(tmp_path)
    entered: list[str] = []

    @contextmanager
    def aside() -> Iterator[None]:
        entered.append("entered")
        yield

    def broken(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("a step failed")

    monkeypatch.setattr("stages.diagnose.assemble.evaluate_hypotheses", broken)
    with pytest.raises(RuntimeError):
        diagnose_run(tmp_path, run_id, NOW, around_write=aside)
    assert entered == [] and (path / LATER).exists()


def test_write_atomically_wraps_only_the_rename(tmp_path: Path) -> None:
    target = tmp_path / "x.json"
    target.write_bytes(b"old")
    seen: list[tuple[int, bytes]] = []

    @contextmanager
    def around() -> Iterator[None]:
        seen.append((len(_staged(tmp_path)), target.read_bytes()))
        yield
        seen.append((len(_staged(tmp_path)), target.read_bytes()))

    write_atomically(target, b"new", around_replace=around)
    assert seen == [(1, b"old"), (0, b"new")]


def _calendar(**figures: float) -> dict:
    return {"method": "weekday_weights", "expected_cur": 10.0, "expected_prev": 10.0, "calendar_effect": 0.0,
            "calendar_adjusted_change": 0.0, "evidence": {}} | figures


def _refusal(model: type, payload: dict) -> ValidationError:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(payload)
    return caught.value


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan")])
def test_any_number_json_cannot_carry_is_too_large_to_add(value: float) -> None:
    # Retargeted by the DEMO review #1 (3G-lite review 3 had made a NaN alone
    # a bug): one rule, as metrics.json's.
    assert refused_as_too_large(_refusal(Calendar, _calendar(calendar_effect=value)))
    written = diagnose(run_data(_steady_with_a_drop()), NOW).model_dump(mode="python")
    share = next(i for i, h in enumerate(written["hypotheses"]) if h["contribution"] is not None)
    written["hypotheses"][share]["contribution"] = value
    assert refused_as_too_large(_refusal(DiagnosisContract, written))


@pytest.mark.filterwarnings("ignore:overflow encountered:RuntimeWarning")  # the overflow is the case
@pytest.mark.filterwarnings("ignore:invalid value encountered:RuntimeWarning")  # inf - inf
def test_a_nan_born_of_the_users_overflowing_amounts_is_too_large_to_add() -> None:
    # DEMO review #1: ten lines a day in January, two in February at 1e306 -
    # the Shapley value multiplies them past a float and subtracts inf from
    # inf: a NaN in the first factor, no infinity beside it.
    rows = []
    for offset in range(31):
        rows += [row(date(2024, 1, 1) + timedelta(days=offset), price=10.0) for _ in range(10)]
    for offset in range(29):
        rows += [row(date(2024, 2, 1) + timedelta(days=offset), price=1e306) for _ in range(2)]
    rows.append(row(date(2024, 3, 1), price=10.0))
    with pytest.raises(ValidationError) as caught:
        diagnose(run_data(rows), NOW)
    assert refused_as_too_large(caught.value)
    assert TOO_LARGE_TO_ADD in str(caught.value)


def test_the_contracts_example_note_is_one_the_contract_reads() -> None:
    # 3G-lite review 3 #4: CONTRACTS section 6's example note carried one measure.
    from contracts.lines import FigureNote

    text = (Path(__file__).resolve().parents[3] / "docs" / "CONTRACTS.md").read_text(encoding="utf-8")
    start = text.index('{"code": "same_day_cancellations",')
    example = text[start:text.index('"always_on": false}', start) + len('"always_on": false}')]
    note = json.loads(example.replace('"text": "Returns and the return rate include same-day cancellations, which '
                                      'the data cannot separate: ..."', '"text": "..."'))
    assert FigureNote.model_validate(note).always_on is False
