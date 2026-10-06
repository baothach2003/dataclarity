"""Session 3G-lite (Thach, 2026-09-29): diagnosis.json from steps 1-7, in
the designed degraded mode - written before the code.

docs/AI_PIPELINE.md section 7: steps 1-7 are deterministic and fill every
block but `ai_findings`; if step 2 blocks, steps 3-6 are skipped, their
blocks null, and the headline reports the data problem (rule 1). Section 9:
with no AI narration `ai_findings` and `model_used` are null and every
computed block, the code-written headline included, still stands. The file
is written atomically; a re-run overwrites only diagnosis.json (CONTRACTS
section 1).
"""

import json
from dataclasses import asdict
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from contracts.diagnosis import DiagnosisContract, NotTestable
from shared.run_registry import create_run
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.assemble import DIAGNOSIS_FILENAME, SCHEMA_VERSION, diagnose, diagnose_run
from stages.diagnose.calendar_effect import compute_calendar
from stages.diagnose.catalog import NOT_TESTABLE
from stages.diagnose.frame import build_frame, history_window
from stages.diagnose.headline import choose_headline
from stages.diagnose.hypotheses import evaluate_hypotheses
from stages.diagnose.inputs import load_run
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_localization
from stages.diagnose.signals import compute_signals
from stages.diagnose.step7_inputs import Step7Inputs, changes
from stages.diagnose.suggestions import named_suggestions
from stages.diagnose.tree import compute_tree
from stages.diagnose.trust import evaluate_trust
from tests.stages.diagnose.diagnose_fixtures import MAPPING, daily_rows, month_span, run_data

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def _steady_with_a_drop() -> list[dict]:
    """23 complete months of three products; the last month sells less."""
    start, end = month_span("2010-01", 23)
    rows = daily_rows(start, end, products=3)
    return [r for r in rows if not (r["Date"] >= "2011-11-01" and r["Product"] == "Widget2")]


def _by_hand(data) -> dict:
    """The blocks composed in AI_PIPELINE 7's order, as the regression
    anchor's harness composes them."""
    history = history_window(data)
    trust = evaluate_trust(data, history)
    blocked = trust.verdict == "blocked"
    period = data.metrics.period
    calendar = None if blocked else compute_calendar(data, history)
    signals = None if blocked else compute_signals(data, history)
    tree = None if blocked else compute_tree(data, history)
    localization = None if blocked else compute_localization(
        data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    inputs = Step7Inputs(data, history, build_frame(data), trust, calendar, signals, tree, localization)
    hypotheses = evaluate_hypotheses(inputs)
    return {"frame": inputs.frame, "trust": trust, "calendar": calendar, "signals": signals, "tree": tree,
            "localization": localization, "hypotheses": hypotheses,
            # 18.7: assemble says whether the headline is rule 6's offsetting case.
            "headline": choose_headline(trust, hypotheses, tree, changes(inputs)).model_copy(
                update={"offsetting": bool(choose_headline(trust, hypotheses, tree, changes(inputs)).offsetting)}),
            "suggested_classes": named_suggestions(data, localization, hypotheses)}


def test_the_diagnosis_is_the_seven_steps_composed_in_order() -> None:
    data = run_data(_steady_with_a_drop())

    found = diagnose(data, NOW)

    expected = _by_hand(data)
    assert expected["trust"].verdict != "blocked" and found.tree is not None
    for block, value in expected.items():
        assert getattr(found, block) == value, block
    assert found.not_testable == [NotTestable(**asdict(spec)) for spec in NOT_TESTABLE]
    assert found.notes == data.metrics.core.notes
    assert (found.schema_version, found.generated_at) == (SCHEMA_VERSION, NOW)


def test_no_ai_narration_the_code_written_headline_stands() -> None:
    found = diagnose(run_data(_steady_with_a_drop()), NOW)
    assert (found.model_used, found.ai_findings) == (None, None)
    assert found.headline.message.startswith("Revenue went from")


def test_a_blocked_run_skips_steps_3_to_6_and_says_why() -> None:
    # An export that starts on 15 January: the previous month is half a month.
    data = run_data(daily_rows(date(2011, 1, 15), date(2011, 2, 28)))

    found = diagnose(data, NOW)

    assert found.trust.verdict == "blocked"
    assert (found.calendar, found.signals, found.tree, found.localization) == (None, None, None, None)
    assert found.headline.rule == 1
    assert found.hypotheses == _by_hand(data)["hypotheses"]


def _run_on_disk(tmp_path, rows: list[dict]) -> str:
    run = create_run(tmp_path)
    frame = pd.DataFrame(rows)
    frame.to_csv(run.path / "cleaned.csv", index=False)
    (run.path / "cleaning_report.json").write_text(json.dumps({
        "schema_version": "4.0", "generated_at": "2026-09-29T00:00:00Z", "rows_in": len(rows),
        "rows_out": len(rows), "columns_in": 5, "columns_out": 5, "changes": [], "warnings": [],
        "column_mapping": MAPPING}), encoding="utf-8")
    metrics = assemble_metrics(frame.astype(str), MAPPING, now=NOW)
    (run.path / "metrics.json").write_text(metrics.model_dump_json(indent=2), encoding="utf-8")
    return run.run_id


def test_diagnose_run_writes_the_diagnosis_and_it_reads_back(tmp_path) -> None:
    run_id = _run_on_disk(tmp_path, _steady_with_a_drop())

    written = diagnose_run(tmp_path, run_id, NOW)

    stored = DiagnosisContract.model_validate_json((tmp_path / run_id / DIAGNOSIS_FILENAME).read_text(encoding="utf-8"))
    assert stored == written == diagnose(load_run(tmp_path, run_id), NOW)
    assert DIAGNOSIS_FILENAME == DiagnosisContract.filename


def test_a_rerun_overwrites_only_the_diagnosis(tmp_path) -> None:
    run_id = _run_on_disk(tmp_path, _steady_with_a_drop())
    diagnose_run(tmp_path, run_id, NOW)
    others = {p.name: p.read_bytes() for p in (tmp_path / run_id).iterdir() if p.name != DIAGNOSIS_FILENAME}

    diagnose_run(tmp_path, run_id, datetime(2026, 9, 30, tzinfo=UTC))

    assert {p.name: p.read_bytes() for p in (tmp_path / run_id).iterdir() if p.name != DIAGNOSIS_FILENAME} == others
    stored = json.loads((tmp_path / run_id / DIAGNOSIS_FILENAME).read_text(encoding="utf-8"))
    assert stored["generated_at"].startswith("2026-09-30")


def test_a_step_that_fails_leaves_the_previous_diagnosis_whole(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = _run_on_disk(tmp_path, _steady_with_a_drop())
    diagnose_run(tmp_path, run_id, NOW)
    before = (tmp_path / run_id / DIAGNOSIS_FILENAME).read_bytes()

    def broken(*_args, **_kwargs):
        raise RuntimeError("a step failed")

    monkeypatch.setattr("stages.diagnose.assemble.evaluate_hypotheses", broken)
    with pytest.raises(RuntimeError):
        diagnose_run(tmp_path, run_id, datetime(2026, 9, 30, tzinfo=UTC))

    assert (tmp_path / run_id / DIAGNOSIS_FILENAME).read_bytes() == before
    assert [p.name for p in (tmp_path / run_id).iterdir() if p.name.startswith(".stage-")] == []


def test_the_marks_and_notes_of_the_line_taxonomy_are_carried() -> None:
    # 2E-t2's file: DOTCOM POSTAGE, a key suggested as a charge nobody
    # confirmed, is a product the diagnosis names; the notes are metrics.json's.
    from stages.diagnose.inputs import build_run_data
    from tests.stages.analyze.test_2et2_stage2 import ANSWERS, MAPPING as MAPPING_2ET2, NOW as NOW_2ET2, ROWS

    df = pd.DataFrame(ROWS, columns=["Day", "Order", "Who", "Sku", "Name", "Qty", "Price", "Type"])
    data = build_run_data(df, MAPPING_2ET2, assemble_metrics(df, MAPPING_2ET2, NOW_2ET2, ANSWERS), ANSWERS)

    found = diagnose(data, NOW)

    assert found.suggested_classes == {"DOTCOM POSTAGE": "charge"} == _by_hand(data)["suggested_classes"]
    assert found.notes == data.metrics.core.notes and len(found.notes) >= 2


def test_diagnosis_json_refuses_a_number_json_cannot_carry() -> None:
    # Review 1 #1: as metrics.json, the file never holds a figure written as
    # null - here in a hypothesis's contribution, which no block checks alone.
    from pydantic import ValidationError

    from contracts.lines import TOO_LARGE_TO_ADD

    written = diagnose(run_data(_steady_with_a_drop()), NOW).model_dump(mode="python")
    share = next(i for i, h in enumerate(written["hypotheses"]) if h["contribution"] is not None)
    written["hypotheses"][share]["contribution"] = float("inf")
    with pytest.raises(ValidationError) as caught:
        DiagnosisContract.model_validate(written)
    assert all(TOO_LARGE_TO_ADD in str(p["msg"]) for p in caught.value.errors())
