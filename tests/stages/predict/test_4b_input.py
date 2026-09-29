"""Session 4B (ninth run): the strategy step's input - the consumer
contract's 4B rows only (docs/CONTRACTS.md section 11), never the whole
files; every list capped to its largest movers; every note worded by its
code (contracts.lines.NOTE_TEXTS), never by the file's sentence (3G0,
adjustment 2). Written before the code.
"""

import json
from typing import Any

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastBlock
from contracts.lines import NOTE_TEXTS
from contracts.metrics import MetricsContract
from stages.predict.strategy_input import MEMBERS_SHOWN, strategy_input
from tests.contracts.test_consumer_contract import section_11
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_forecast import forecast_payload
from tests.contracts.test_metrics import metrics_payload

# The one key the input adds: a note's sentence, from its code.
DERIVED = {"core.notes[].says", "notes[].says"}


def _inputs(metrics: dict | None = None, diagnosis: dict | None = None) -> dict[str, Any]:
    return strategy_input(MetricsContract.model_validate(metrics or metrics_payload()),
                          DiagnosisContract.model_validate(diagnosis or diagnosis_payload()),
                          ForecastBlock.model_validate(forecast_payload()["forecast"]))


def _paths(value: Any, prefix: str, stop: set[str]) -> set[str]:
    """Every key path in `value`, as section 11 writes them ([] for a list);
    a dict-typed field (product names as keys) is one path."""
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else key
            found.add(path)
            if path not in stop:
                found |= _paths(item, path, stop)
    elif isinstance(value, list):
        for item in value:
            found |= _paths(item, f"{prefix}[]", stop)
    return found


def test_the_input_holds_only_the_4b_rows_of_section_11() -> None:
    rows, _ = section_11()
    payload = _inputs()
    for part, filename in (("metrics", "metrics.json"), ("diagnosis", "diagnosis.json")):
        four_b = {path for path, (_, readers) in rows[filename].items() if "4B" in readers}
        dicts = {path for path, (kind, _) in rows[filename].items() if kind.startswith("dict[")}
        stray = _paths(payload[part], "", dicts) - four_b - DERIVED
        assert not stray, f"{filename}: {sorted(stray)}"


def test_the_filled_blocks_hold_only_4b_rows_too() -> None:
    # 4B review 1 #17: the examples' notes carry no measures and their
    # non-product and unmeasurable lists are empty - their fields were never
    # walked. A note with measures, a non-product line, an unmeasurable one.
    note = {"code": "same_day_cancellations", "figures": ["gross_sales", "returns", "return_rate", "orders", "aov",
                                                          "customers", "products", "diagnosis"],
            "text": "t", "measures": [{"name": name, "scope": scope, "lines": 10, "amount": amount, "orders": 5,
                                       "keys": None}
                                      for name, amount in (("returns", -345.5), ("sales", 414.6),
                                                           ("returns_unchecked", -219.6))
                                      for scope in ("file", "current", "previous")]}
    metrics, diagnosis = metrics_payload(), diagnosis_payload()
    metrics["core"]["notes"].append(note)
    diagnosis["notes"].append(note)
    metrics["core"]["non_product"] = [{"line_class": "discount", "lines": 54, "amount": -6835.57,
                                       "amount_current": -160.27, "amount_previous": 0.0, "reason": "r"}]
    metrics["core"]["unmeasurable"] = [{"scope": "file", "reason": "no price", "lines": 3}]
    rows, _ = section_11()
    payload = _inputs(metrics, diagnosis)
    for part, filename in (("metrics", "metrics.json"), ("diagnosis", "diagnosis.json")):
        four_b = {path for path, (_, readers) in rows[filename].items() if "4B" in readers}
        dicts = {path for path, (kind, _) in rows[filename].items() if kind.startswith("dict[")}
        walked = _paths(payload[part], "", dicts)
        assert not walked - four_b - DERIVED, f"{filename}: {sorted(walked - four_b - DERIVED)}"
    assert {"core.notes[].measures[].amount", "core.non_product[].reason", "core.unmeasurable[].lines"} <= _paths(
        payload["metrics"], "", set())


def test_the_forecast_block_is_passed_whole() -> None:
    assert _inputs()["forecast"] == ForecastBlock.model_validate(forecast_payload()["forecast"]).model_dump(
        mode="json")


def test_a_note_is_worded_by_its_code_never_by_the_files_sentence() -> None:
    metrics = metrics_payload()
    metrics["core"]["notes"][0]["text"] = "A SENTENCE THE FILE CARRIES"
    payload = _inputs(metrics=metrics)
    note = payload["metrics"]["core"]["notes"][0]
    assert note["says"] == NOTE_TEXTS[note["code"]]
    assert "A SENTENCE THE FILE CARRIES" not in json.dumps(payload)
    assert set(note) == {"code", "says", "figures", "measures", "always_on"}


def test_hypothesis_evidence_and_the_narration_are_never_sent() -> None:
    # Not 4B rows (section 11): the evidence is free-form per hypothesis,
    # and the strategy reads the deterministic diagnosis, not its narration
    # (4B's S4).
    payload = _inputs()
    assert all("evidence" not in h for h in payload["diagnosis"]["hypotheses"])
    assert "ai_findings" not in payload["diagnosis"] and "model_used" not in payload["diagnosis"]


def test_a_dimensions_members_are_capped_to_the_largest_movers() -> None:
    # 25 members whose change is -12, -11, ..., 12: the ten largest by size
    # are 12, -12, 11, -11, 10, -10, 9, -9, 8, -8.
    diagnosis = diagnosis_payload()
    dimension = diagnosis["localization"]["dimensions"][0]
    template = dimension["members"][0]
    dimension["members"] = [template | {"name": f"m{delta:+d}", "delta": float(delta)} for delta in range(-12, 13)]
    members = _inputs(diagnosis=diagnosis)["diagnosis"]["localization"]["dimensions"][0]["members"]
    assert MEMBERS_SHOWN == 10
    assert sorted(m["delta"] for m in members) == [-12, -11, -10, -9, -8, 8, 9, 10, 11, 12]


def test_the_countries_and_the_products_are_capped() -> None:
    # 15 countries whose revenue moved by 0..14 (current = previous + k): the
    # ten that moved most are 5..14. 15 top products and decliners: the
    # first ten as the file ranks them.
    metrics = metrics_payload()
    metrics["by_dimension"]["country"] = [
        {"name": f"c{k}", "revenue_current": 100.0 + k, "revenue_previous": 100.0, "contribution_pct": float(k)}
        for k in range(15)]
    top = metrics["products"]["top_products"][0]
    metrics["products"]["top_products"] = [top | {"product": f"p{k}", "revenue": 1000.0 - k} for k in range(15)]
    payload = _inputs(metrics=metrics)["metrics"]
    assert sorted(c["name"] for c in payload["by_dimension"]["country"]) == sorted(f"c{k}" for k in range(5, 15))
    assert [p["product"] for p in payload["products"]["top_products"]] == [f"p{k}" for k in range(10)]
