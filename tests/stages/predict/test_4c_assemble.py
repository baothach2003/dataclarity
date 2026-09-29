"""Session 4C (ninth run): stage 4 assembles forecast.json - the computed
forecast always; the AI's checked recommendations only when the step is on,
the AI is asked and answers; the AI blocks null together otherwise (CONTRACTS
8) - and refuses a diagnosis of other months than the metrics'. The AI
faked. Written before the code.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import DoNotDo, ForecastContract, Recommendation
from contracts.metrics import MetricsContract
from shared.ai_client import AIUnavailable
from stages.predict.ai_strategy import BLOCKED, NOT_COMPARABLE, Strategy
from stages.predict.assemble import (
    SCHEMA_VERSION,
    SWITCHED_OFF,
    DiagnosisMismatchError,
    Skip,
    predict,
    predict_run,
)
from stages.predict.forecast import forecast
from tests.contracts.test_diagnosis import diagnosis_payload
from tests.contracts.test_metrics import metrics_payload

NOW = datetime(2026, 9, 29, tzinfo=UTC)
STRATEGY = Strategy(
    recommendations=[Recommendation(priority=i, insight="i", cause="c", action="a", expected_impact="e = 1",
                                    how_to_measure="m over 30 days", confidence=0.5) for i in (1, 2, 3)],
    do_not_do=[DoNotDo(tempting_action="t", why_wrong_here="w")], model="served-model")


def _files(**period: object) -> tuple[MetricsContract, DiagnosisContract]:
    metrics = metrics_payload()
    metrics["period"] |= period
    return MetricsContract.model_validate(metrics), DiagnosisContract.model_validate(diagnosis_payload())


def _answering(*_: object) -> Strategy:
    return STRATEGY


def _unavailable(*_: object) -> Strategy:
    raise AIUnavailable("timeout")


def test_the_forecast_and_the_checked_recommendations_make_the_file() -> None:
    metrics, diagnosis = _files()
    prediction = predict(metrics, diagnosis, _answering, NOW)
    contract = prediction.contract
    assert (contract.schema_version, contract.generated_at, contract.model_used) == ("1.0", NOW, "served-model")
    assert SCHEMA_VERSION == "1.0"
    assert (contract.recommendations, contract.do_not_do) == (STRATEGY.recommendations, STRATEGY.do_not_do)
    assert (prediction.ai, prediction.code) == ("answered", None)


def test_the_step_switched_off_leaves_the_forecast_and_null_ai_blocks() -> None:
    # 4C's C9 (4B blocked at its review bound): off, the AI is never asked.
    metrics, diagnosis = _files()
    prediction = predict(metrics, diagnosis, SWITCHED_OFF, NOW)
    contract = prediction.contract
    assert (contract.model_used, contract.recommendations, contract.do_not_do) == (None, None, None)
    assert contract.forecast == forecast(metrics)  # the computed block, whatever the AI step does
    assert (prediction.ai, prediction.code) == ("not_asked", "switched_off")


def test_an_ai_that_gives_no_accepted_answer_leaves_the_forecast_and_null_ai_blocks() -> None:
    metrics, diagnosis = _files()
    prediction = predict(metrics, diagnosis, _unavailable, NOW)
    assert (prediction.contract.model_used, prediction.contract.recommendations) == (None, None)
    assert (prediction.ai, prediction.code) == ("unavailable", "timeout")


def test_a_blocked_diagnosis_is_not_sent_to_the_ai() -> None:
    metrics, _ = _files()
    blocked = diagnosis_payload()
    blocked["trust"]["verdict"] = "blocked"
    blocked.update({"calendar": None, "signals": None, "tree": None, "localization": None,
                    "headline": {"rule": 1, "hypothesis_id": None, "lens": None, "message": "m"}})
    asked: list[object] = []

    def step(*args: object) -> Strategy:
        asked.append(args)
        return STRATEGY

    prediction = predict(metrics, DiagnosisContract.model_validate(blocked), step, NOW)
    assert asked == [] and (prediction.ai, prediction.code, prediction.sentence) == (
        "not_asked", "diagnosis_blocked", BLOCKED)
    assert prediction.contract.recommendations is None


def test_months_that_cannot_be_compared_are_not_sent_to_the_ai() -> None:
    # CONTRACTS 11: nothing is compared with part of a month.
    metrics, diagnosis = _files()
    incomplete = metrics.model_copy(update={"period": metrics.period.model_copy(update={"previous_complete": False})})
    prediction = predict(incomplete, diagnosis, _answering, NOW)
    assert (prediction.ai, prediction.code, prediction.sentence) == ("not_asked", "not_comparable", NOT_COMPARABLE)


def test_an_answer_already_accepted_is_final_but_never_kept_with_the_step_off() -> None:
    # 4C review #2 (SPECS 11: 4 calls a run) and #4 (the step switched off
    # after an answer: none is kept).
    metrics, diagnosis = _files()
    previous = predict(metrics, diagnosis, _answering, NOW).contract
    asked: list[object] = []

    def step(*args: object) -> Strategy:
        asked.append(args)
        return STRATEGY

    again = predict(metrics, diagnosis, step, NOW, previous)
    assert asked == [] and again.contract.recommendations == previous.recommendations
    assert predict(metrics, diagnosis, SWITCHED_OFF, NOW, previous).contract.recommendations is None
    assert predict(metrics, diagnosis, Skip("attempts_used", "s"), NOW, previous).ai == "answered"


def test_an_unexpected_error_on_the_ai_path_keeps_the_forecast() -> None:
    # 4C review #7: only AIUnavailable was caught; a TypeError lost the forecast.
    metrics, diagnosis = _files()

    def broken(*_: object) -> Strategy:
        raise TypeError("a client that cannot build a request")

    prediction = predict(metrics, diagnosis, broken, NOW)
    assert (prediction.ai, prediction.code, prediction.contract.forecast) == (
        "unavailable", "internal_error", forecast(metrics))


def test_a_diagnosis_of_other_months_is_refused() -> None:
    # PROJECT_PLAN 4C: a hand-edited directory, or a standalone run after a
    # re-analysis (the backend sets stale outputs aside itself).
    metrics, diagnosis = _files(current="2011-10", previous="2011-09")
    with pytest.raises(DiagnosisMismatchError, match="run the diagnosis again"):
        predict(metrics, diagnosis, _answering, NOW)


def _run_dir(tmp_path: Path) -> Path:
    run = tmp_path / "11111111-1111-4111-8111-111111111111"
    run.mkdir()
    metrics, diagnosis = _files()
    (run / "metrics.json").write_text(metrics.model_dump_json(), encoding="utf-8")
    (run / "diagnosis.json").write_text(diagnosis.model_dump_json(), encoding="utf-8")
    return run


def test_predict_run_writes_forecast_json_and_a_failed_write_leaves_the_old_one(tmp_path: Path) -> None:
    run = _run_dir(tmp_path)
    prediction = predict_run(tmp_path, run.name, recommend_step=_answering, now=NOW)
    written = ForecastContract.model_validate(json.loads((run / "forecast.json").read_text(encoding="utf-8")))
    assert written == prediction.contract
    before = (run / "forecast.json").read_bytes()

    class Refused(Exception):
        pass

    def refuse() -> None:
        raise Refused

    with pytest.raises(Refused):
        predict_run(tmp_path, run.name, recommend_step=SWITCHED_OFF, now=NOW, around_write=refuse)
    assert (run / "forecast.json").read_bytes() == before
