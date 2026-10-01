"""Session 2E-t2 (Thach, 2026-09-28): stage 3 and stage 4 read the line
taxonomy - written before the code. docs/LINE_TAXONOMY.md sections 3 and 4.5:

- stage 3's output carries metrics.json's notes (its `return_rate` signal and
  the headline's revenue are figures they qualify) and its own
  `suggested_classes`: every product it names - the product dimension's
  members, new and removed members, R1's top member, R3's products - whose
  key carries a suggestion nobody confirmed;
- diagnosis.json 17.0;
- stage 4's products at stockout risk are "not supported in v1" too;
- the narration's and the strategy's prompts read the notes and the marks.
"""

from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastBlock
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.inputs import build_run_data
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_localization
from stages.diagnose.suggestions import named_suggestions, stage_3_notes
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.stages.analyze.test_2et2_stage2 import ANSWERS, MAPPING, NOW, ROWS

PROMPTS = Path(__file__).resolve().parents[3] / "prompts"


@pytest.fixture(scope="module")
def data():
    df = pd.DataFrame(ROWS, columns=["Day", "Order", "Who", "Sku", "Name", "Qty", "Price", "Type"])
    return build_run_data(df, MAPPING, assemble_metrics(df, MAPPING, NOW, ANSWERS), ANSWERS)


def test_the_notes_are_metrics_jsons(data) -> None:
    assert stage_3_notes(data) == data.metrics.core.notes


def test_every_product_stage_3_names_with_an_unconfirmed_suggestion(data) -> None:
    period = data.metrics.period
    loc = compute_localization(data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    names = {m.name for d in loc.dimensions if d.name == "product" for m in d.members}
    assert "DOTCOM POSTAGE" in names  # it fell from 5 to -3

    assert named_suggestions(data, loc, []) == {"DOTCOM POSTAGE": "charge"}


@pytest.mark.parametrize("field", ["new_members", "removed_members"])
def test_a_new_or_removed_member_is_marked_too(data, field: str) -> None:
    period = data.metrics.period
    loc = compute_localization(data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    only = {"members": [], "new_members": [], "removed_members": [], field: ["DOTCOM POSTAGE"]}
    dimensions = [d.model_copy(update=only) if d.name == "product" else d for d in loc.dimensions]

    assert named_suggestions(data, loc.model_copy(update={"dimensions": dimensions}), []) == {
        "DOTCOM POSTAGE": "charge"}


def test_a_suggested_product_this_output_does_not_name_is_not_marked(data) -> None:
    # Review 1 #6: the filter by what the output names was untested.
    period = data.metrics.period
    loc = compute_localization(data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    only_mug = [d.model_copy(update={"members": [m for m in d.members if m.name == "Mug"], "new_members": [],
                                     "removed_members": []}) if d.name == "product" else d for d in loc.dimensions]

    assert named_suggestions(data, loc.model_copy(update={"dimensions": only_mug}), []) == {}
    assert named_suggestions(data, None, []) == {}


def test_r3s_products_are_marked(data) -> None:
    from contracts.diagnosis import Hypothesis

    r3 = Hypothesis.model_validate({
        "id": "R3", "family": "localization_lifecycle", "lens": "localization", "statement": "x",
        "verdict": "inconclusive", "contribution": None, "share": None,
        "evidence": {"products": [{"product": "DOTCOM POSTAGE"}, {"product": "Mug"}]}, "rule": "r"})

    assert named_suggestions(data, None, [r3]) == {"DOTCOM POSTAGE": "charge"}


def test_repeated_row_labels_do_not_stop_stage_3() -> None:
    # Review 1 #15: a frame put together from others repeats its labels.
    halves = pd.DataFrame(ROWS, columns=["Day", "Order", "Who", "Sku", "Name", "Qty", "Price", "Type"])
    df = pd.concat([halves.iloc[:9], halves.iloc[9:].reset_index(drop=True)])
    assert df.index.has_duplicates
    run = build_run_data(df, MAPPING, assemble_metrics(df, MAPPING, NOW, ANSWERS), ANSWERS)
    period = run.metrics.period
    loc = compute_localization(run, month_revenue(run, period.current) - month_revenue(run, period.previous))

    assert named_suggestions(run, loc, []) == {"DOTCOM POSTAGE": "charge"}


def test_the_evidence_keys_the_contract_reads_are_the_ones_stage_3_writes(data) -> None:
    # Review 2 #10: `named_products` reads R1's `top_member` and R3's
    # `products[].product`; renamed in stage 3, the marks would drop silently.
    from dataclasses import fields

    from stages.diagnose.calendar_effect import compute_calendar
    from stages.diagnose.frame import build_frame, history_window
    from stages.diagnose.hypotheses import evaluate_hypotheses
    from stages.diagnose.signals import compute_signals
    from stages.diagnose.step7_inputs import Step7Inputs
    from stages.diagnose.stockout import Stockout
    from stages.diagnose.tree import compute_tree
    from stages.diagnose.trust import evaluate_trust

    history = history_window(data)
    period = data.metrics.period
    loc = compute_localization(data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    inputs = Step7Inputs(data, history, build_frame(data), evaluate_trust(data, history),
                         compute_calendar(data, history), compute_signals(data, history),
                         compute_tree(data, history), loc)
    by_id = {h.id: h for h in evaluate_hypotheses(inputs)}

    assert "top_member" in by_id["R1"].evidence
    assert "products" in by_id["R3"].evidence
    assert "product" in {f.name for f in fields(Stockout)}


def test_a_name_in_a_hypothesis_is_marked_too(data) -> None:
    from contracts.diagnosis import Hypothesis

    period = data.metrics.period
    loc = compute_localization(data, month_revenue(data, period.current) - month_revenue(data, period.previous))
    loc = loc.model_copy(update={"dimensions": []})
    r1 = Hypothesis.model_validate({
        "id": "R1", "family": "localization_lifecycle", "lens": "localization", "statement": "x",
        "verdict": "ruled_out", "contribution": None, "share": None,
        "evidence": {"top_member": "DOTCOM POSTAGE"}, "rule": "r"})
    r3 = r1.model_copy(update={"id": "R3", "evidence": {"products": [{"product": "Mug"}]}})

    assert named_suggestions(data, loc, [r1, r3]) == {"DOTCOM POSTAGE": "charge"}


def test_diagnosis_json_is_17_0_with_the_notes_and_the_marks(data) -> None:
    payload = diagnosis_payload()
    assert payload["schema_version"] == "18.0"
    payload["notes"] = [n.model_dump(mode="json") for n in stage_3_notes(data)]
    payload["hypotheses"].append({"id": "R1", "family": "localization_lifecycle", "lens": "localization",
                                  "statement": "x", "verdict": "ruled_out", "contribution": None, "share": None,
                                  "evidence": {"top_member": "DOTCOM POSTAGE"}, "rule": "r"})
    payload["suggested_classes"] = {"DOTCOM POSTAGE": "charge"}
    diagnosis = DiagnosisContract.model_validate(payload)
    assert (diagnosis.notes, diagnosis.suggested_classes) == (data.metrics.core.notes, {"DOTCOM POSTAGE": "charge"})

    payload["schema_version"] = "16.0"
    with pytest.raises(ValidationError, match="re-analyse"):
        DiagnosisContract.model_validate(payload)


def test_stage_4s_stockout_risk_is_not_supported_in_v1() -> None:
    base = {"method": "rolling", "horizon_periods": 0, "revenue": [], "insufficient_history": True,
            "months_used": 2, "history_note": None, "season_years": None, "season_note": None}  # 4A: the enforced shape
    block = ForecastBlock.model_validate({**base, "products_at_stockout_risk": None,
                                          "products_at_stockout_risk_reason": "stock figures are not supported in v1"})
    assert block.products_at_stockout_risk is None
    with pytest.raises(ValidationError, match="not supported in v1"):
        ForecastBlock.model_validate({**base, "products_at_stockout_risk_reason": None, "products_at_stockout_risk": [
            {"product": "Mug", "days_to_stockout": 8.6, "suggested_reorder_units": 420}]})


def test_the_prompts_read_the_notes_and_the_marks() -> None:
    for name in ("root_cause.md", "strategy.md"):
        text = (PROMPTS / name).read_text(encoding="utf-8")
        assert "suggested_classes" in text and "notes" in text, name
    strategy = (PROMPTS / "strategy.md").read_text(encoding="utf-8")
    assert "reorder recommendation with a unit figure" not in strategy
