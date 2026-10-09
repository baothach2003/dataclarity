"""Session 4C (ninth run), rewritten for the report redesign's step 4 as
Thach's option (d): stage 4 assembles forecast.json 2.1 - the computed
forecast always, and the code-written suggested actions by their state
(docs/CONTRACTS.md section 8; design 4.1-4.4): "list" (the actions, or none
when no claim can be selected), "suppressed" (claims possible but nothing to
act on); never "off"; no model; 4B's free-text blocks null (Q42, Q53). It
asks no AI and refuses a diagnosis of other months than the metrics'.
Written before the code."""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.metrics import MetricsContract
from stages.predict.assemble import SCHEMA_VERSION, DiagnosisMismatchError, predict, predict_run
from stages.predict.claims import BLOCKED, NOT_COMPARABLE
from stages.predict.forecast import forecast
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_metrics import metrics_payload
from tests.stages.report.real_runs import files

NOW = datetime(2026, 9, 29, tzinfo=UTC)


def _files(**period: object) -> tuple[MetricsContract, DiagnosisContract]:
    metrics = metrics_payload()
    metrics["period"] |= period
    return MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis_payload())


def _real(run: str) -> tuple[MetricsContract, DiagnosisContract]:
    data = files(run)
    return (MetricsContract.model_validate(data["metrics.json"]),
            DiagnosisContract.model_validate(data["diagnosis.json"]))


def test_the_forecast_and_the_code_written_actions_make_the_file() -> None:
    prediction = predict(*_real("kaggle"), NOW)
    contract = prediction.contract

    # 2.2: actions[].name (Q65)
    assert (contract.schema_version, SCHEMA_VERSION, contract.generated_at) == ("2.2", "2.2", NOW)
    assert (contract.actions_status, contract.actions_model, prediction.why_none) == ("list", None, None)
    # B1 and B2 moved out of the claims (step 4's scoped review): P2 remains.
    assert [(a.claim, a.hypothesis_id) for a in contract.actions] == [("K1", "P2")]
    assert contract.actions[0].action == "Show a pricier alternative next to the cheaper products customers chose."
    assert (contract.model_used, contract.recommendations, contract.do_not_do) == (None, None, None)  # Q42, Q53
    assert contract.forecast == forecast(_real("kaggle")[0])


@pytest.mark.parametrize("run", ["demo_classed", "demo_unanswered"])
def test_no_cause_named_lists_no_action(run: str) -> None:
    prediction = predict(*_real(run), NOW)

    assert (prediction.contract.actions_status, prediction.contract.actions) == ("list", [])
    assert prediction.why_none == "no suggested action: the diagnosis names no cause an action in the shop works on"


def test_a_blocked_diagnosis_lists_no_action() -> None:
    metrics, _ = _files()
    blocked = diagnosis_payload()
    blocked["trust"]["verdict"] = "blocked"
    blocked.update({"calendar": None, "signals": None, "tree": None, "localization": None,
                    "headline": {"rule": 1, "hypothesis_id": None, "lens": None, "message": "m"}})
    prediction = predict(metrics, DiagnosisContract.model_validate(blocked), NOW)

    assert (prediction.contract.actions_status, prediction.contract.actions, prediction.why_none) == (
        "list", [], BLOCKED)


def test_months_that_cannot_be_compared_list_no_action() -> None:
    metrics, diagnosis = _real("kaggle")
    incomplete = metrics.model_copy(update={"period": metrics.period.model_copy(update={"previous_complete": False})})
    prediction = predict(incomplete, diagnosis, NOW)

    assert (prediction.contract.actions_status, prediction.contract.actions, prediction.why_none) == (
        "list", [], NOT_COMPARABLE)


def test_claims_with_nothing_to_act_on_are_suppressed_never_off() -> None:
    # Kaggle with P3 the named cause: no refund in either month, so its figure did
    # not move and no catalog entry applies; P2 under the bar.
    metrics, diagnosis = _real("kaggle")
    hypotheses = [h.model_copy(update={"share": -0.1}) if h.id == "P2" else
                  h.model_copy(update={"verdict": "supported", "against_the_change": False}) if h.id == "P3" else h
                  for h in diagnosis.hypotheses]
    headline = diagnosis.headline.model_copy(update={"hypothesis_id": "P3", "named": ["P3"]})
    flat = diagnosis.model_copy(update={"hypotheses": hypotheses, "headline": headline})
    prediction = predict(metrics, flat, NOW)

    assert (prediction.contract.actions_status, prediction.contract.actions) == ("suppressed", None)
    assert prediction.why_none == "no suggested action: the figures that moved have no action to suggest"


def test_a_diagnosis_of_other_months_is_refused() -> None:
    metrics, diagnosis = _files(current="2011-10", previous="2011-09")
    with pytest.raises(DiagnosisMismatchError, match="run the diagnosis again"):
        predict(metrics, diagnosis, NOW)


def _run_dir(tmp_path: Path, run: str = "kaggle", currency: str | None = None) -> Path:
    path = tmp_path / "11111111-1111-4111-8111-111111111111"
    path.mkdir()
    data = copy.deepcopy(files(run))
    if currency is not None:
        data["cleaning_report.json"]["currency"] = {"code": currency, "source": "user", "evidence": None}
    for name in ("metrics.json", "diagnosis.json", "cleaning_report.json"):
        (path / name).write_text(json.dumps(data[name]), encoding="utf-8")
    return path


def test_predict_run_writes_forecast_json_and_a_failed_write_leaves_the_old_one(tmp_path: Path) -> None:
    run = _run_dir(tmp_path)
    prediction = predict_run(tmp_path, run.name, now=NOW)
    written = ForecastContract.model_validate(json.loads((run / "forecast.json").read_text(encoding="utf-8")))
    assert written == prediction.contract and [a.hypothesis_id for a in written.actions] == ["P2"]
    before = (run / "forecast.json").read_bytes()

    class Refused(Exception):
        pass

    def refuse() -> None:
        raise Refused

    with pytest.raises(Refused):
        predict_run(tmp_path, run.name, now=NOW, around_write=refuse)
    assert (run / "forecast.json").read_bytes() == before


def test_predict_run_writes_money_in_the_files_confirmed_currency(tmp_path: Path) -> None:
    run = _run_dir(tmp_path, currency="GBP")

    assert "about GBP -1,479.65" in predict_run(tmp_path, run.name, now=NOW).contract.actions[0].fact


def test_predict_run_without_a_cleaning_report_writes_no_code(tmp_path: Path) -> None:
    run = _run_dir(tmp_path, currency="GBP")
    (run / "cleaning_report.json").unlink()

    fact = predict_run(tmp_path, run.name, now=NOW).contract.actions[0].fact
    assert "about -1,479.65" in fact and "GBP" not in fact


def test_a_cause_no_action_works_on_is_no_claim_never_nothing_to_act_on() -> None:
    # Rule 5 naming the calendar (T1), or rule 6 naming R2 (Q52): neither is a
    # check a claim may rest on, so the list is empty - never "suppressed".
    data = files("kaggle")
    for hypothesis_id, rule in (("T1", 5), ("R2", 6)):
        diagnosis = copy.deepcopy(data["diagnosis.json"])
        diagnosis["headline"] |= {"rule": rule, "hypothesis_id": None if rule == 5 else hypothesis_id,
                                  "lens": None, "named": [hypothesis_id], "hedge": None}
        for hypothesis in diagnosis["hypotheses"]:
            if hypothesis["id"] not in (hypothesis_id, "D1", "D2", "D3", "T2", "T3", "C4"):
                hypothesis |= {"verdict": "ruled_out", "against_the_change": False}
        if hypothesis_id == "R2":
            next(h for h in diagnosis["hypotheses"] if h["id"] == "R2")["verdict"] = "supported"
        prediction = predict(MetricsContract.model_validate(data["metrics.json"]),
                             DiagnosisContract.model_validate(diagnosis), NOW)

        assert (prediction.contract.actions_status, prediction.contract.actions) == ("list", []), hypothesis_id
