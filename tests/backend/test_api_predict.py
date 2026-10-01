"""POST /api/runs/{id}/predict (session 4C) - written before the code,
widened by its review. Stage 4 writes forecast.json: the computed forecast
always; the AI's recommendations only when the step is on
(`STRATEGY_AI_ENABLED`, off by default in v1: 4B stopped at its review
bound), the AI faked here. Allowed from `analyzed` once diagnosis.json
exists; the run stays `analyzed`. The run's one AI retry is shared with
stage 1 (SPECS 11); an accepted answer is final; the AI is asked at most
three times a run, and never at the forecast's expense.
"""

import json
from contextlib import contextmanager
from typing import Any

from app.models import RunStatus
from contracts import ForecastContract
from tests.ai_fakes import FakeResponse
from tests.backend.api_support import UNKNOWN_RUN, MakeApi, codes, make_api_with_plan, unusable_reply
from tests.backend.test_api_diagnose import _monthly_analyzed_run

# A sound answer on the monthly fixture (two products, Mug and Cup): every
# figure cited by path, the impact a formula.
TOP = "metrics.products.top_products"
REC = {"insight": "Revenue was £{metrics.core.revenue_current} in {metrics.period.current}.",
       "cause": "{" + TOP + "[0].product} took £{" + TOP + "[0].revenue}.",
       "action": "Bundle {" + TOP + "[1].product} with it for {window:30 days}.",
       "expected_impact": "£{" + TOP + "[0].revenue} x {assume:10%}",
       "how_to_measure": "Its revenue over {window:30 days}.", "confidence": 0.5}
ANSWER = {"recommendations": [REC | {"priority": i} for i in (1, 2, 3)],
          "do_not_do": [{"tempting_action": "A {offer:20%} discount to everyone",
                         "why_wrong_here": "Revenue was £{metrics.core.revenue_current}."}]}


def _diagnosed(make_api: MakeApi, *answers: Any, **settings: Any) -> tuple[Any, str]:
    api, run_id = _monthly_analyzed_run(make_api, **settings)
    api.messages.outcomes.extend(answers)
    assert api.post(run_id, "diagnose").status_code == 200
    return api, run_id


def _reason(body: dict[str, Any]) -> str:
    return body["notices"][0]["details"]["reason"]


# --- the step off (v1's default) --------------------------------------------------------------


def test_predict_writes_the_forecast_with_the_ai_step_off_by_default(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)
    calls = api.ai_requests

    response = api.post(run_id, "predict")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["run_id"], body["status"], codes(body), _reason(body)) == (
        run_id, "analyzed", ["AI_NOT_ASKED"], "switched_off")
    assert "The forecast is written" in body["notices"][0]["message"]
    forecast = ForecastContract.model_validate(body["forecast"])
    assert forecast == ForecastContract.model_validate(api.read_json(run_id, "forecast.json"))
    assert (forecast.schema_version, forecast.model_used, forecast.recommendations) == ("2.0", None, None)
    assert forecast.forecast.insufficient_history is False
    assert api.ai_requests == calls  # the AI was never called
    assert api.status(run_id) is RunStatus.ANALYZED


# --- the step on -------------------------------------------------------------------------------


def test_the_step_switched_on_asks_the_ai_and_renders_its_answer(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api, FakeResponse(json.dumps(ANSWER)), strategy_ai_enabled=True)

    response = api.post(run_id, "predict")

    assert response.status_code == 200, response.text
    body = response.json()
    assert codes(body) == []
    forecast = ForecastContract.model_validate(body["forecast"])
    assert forecast.model_used == "served-model" and len(forecast.recommendations) == 3
    assert "{" not in forecast.recommendations[0].insight  # rendered by code, never the AI's placeholders
    # 0.10 x the top product's revenue, computed by code and appended.
    assert " = " in forecast.recommendations[0].expected_impact
    assert api.messages.calls[-1]["model"] == "test-model-reasoning"  # the reasoning model (ADR-0003)


def test_an_accepted_answer_is_final_a_second_predict_asks_nothing(make_api: MakeApi) -> None:
    # 4C review #2 (SPECS 11, 4 calls a run): as stage 1's answers are final.
    api, run_id = _diagnosed(make_api, FakeResponse(json.dumps(ANSWER)), strategy_ai_enabled=True)
    first = api.post(run_id, "predict").json()["forecast"]
    calls = api.ai_requests

    second = api.post(run_id, "predict")

    assert second.status_code == 200 and api.ai_requests == calls
    assert second.json()["forecast"]["recommendations"] == first["recommendations"]


def test_the_runs_one_retry_is_shared_with_stage_1(make_api: MakeApi) -> None:
    # 4C's C5 (SPECS 11: "max 4 calls per run plus 1 shared retry"): the
    # fixture's stage 1 spent the retry on two unusable schema answers, so a
    # refused strategy answer is not retried - one call, then unavailable.
    wrong = json.loads(json.dumps(ANSWER))
    wrong["do_not_do"] = []
    api, run_id = _diagnosed(make_api, FakeResponse(json.dumps(wrong)), FakeResponse(json.dumps(ANSWER)),
                             strategy_ai_enabled=True)
    calls = api.ai_requests

    response = api.post(run_id, "predict")

    assert response.status_code == 200, response.text
    assert (codes(response.json()), _reason(response.json())) == (["AI_UNAVAILABLE"], "invalid_response")
    assert api.ai_requests == calls + 1
    assert response.json()["forecast"]["recommendations"] is None


def test_the_ai_is_asked_at_most_three_times_and_the_forecast_is_never_locked_out(make_api: MakeApi) -> None:
    # 4C review #1: the fourth predict was a 429 and a re-analysis left the
    # run with no forecast for good. Now the AI is asked three times at most;
    # a fourth predict writes the forecast without asking.
    api, run_id = _diagnosed(make_api, unusable_reply(), unusable_reply(), unusable_reply(),
                             strategy_ai_enabled=True)
    for _ in range(3):
        assert codes(api.post(run_id, "predict").json()) == ["AI_UNAVAILABLE"]
    calls = api.ai_requests

    fourth = api.post(run_id, "predict")

    assert fourth.status_code == 200 and api.ai_requests == calls
    assert (codes(fourth.json()), _reason(fourth.json())) == (["AI_NOT_ASKED"], "attempts_used")
    assert "forecast.json" in api.files(run_id)


def test_an_unexpected_error_on_the_ai_path_keeps_the_forecast(make_api: MakeApi) -> None:
    # 4C review #7: a TypeError of the AI's path threw the computed forecast away.
    api, run_id = _diagnosed(make_api, TypeError("a client that cannot build a request"), strategy_ai_enabled=True)

    response = api.post(run_id, "predict")

    assert response.status_code == 200, response.text
    assert (codes(response.json()), _reason(response.json())) == (["AI_UNAVAILABLE"], "internal_error")
    assert response.json()["forecast"]["forecast"] is not None


# --- the order of the steps and the run's files -------------------------------------------------


def test_predict_before_the_diagnosis_is_invalid_state(make_api: MakeApi) -> None:
    # PROJECT_PLAN 4C: never diagnosed (or its diagnosis removed by a
    # re-analysis) - "run the diagnosis first", never EXPIRED.
    api, run_id = _monthly_analyzed_run(make_api)

    response = api.post(run_id, "predict")

    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["details"]["missing"]) == ("INVALID_STATE", "diagnosis.json")
    assert "Run the diagnosis first" in error["message"]
    assert "forecast.json" not in api.files(run_id)


def test_a_diagnosis_removed_as_predict_starts_is_invalid_state_not_a_500(make_api: MakeApi, monkeypatch: Any) -> None:
    # 4C review #3: checked outside the exclusive block, read inside it - a
    # re-analysis finishing between them removed diagnosis.json: a 500.
    api, run_id = _diagnosed(make_api)
    work = api.app.state.run_work
    real = work.execution

    @contextmanager
    def removing(run: str):  # type: ignore[no-untyped-def]  # the patched method's own shape
        api.file(run_id, "diagnosis.json").unlink()
        with real(run):
            yield

    monkeypatch.setattr(work, "execution", removing)
    response = api.post(run_id, "predict")
    assert (response.status_code, response.json()["error"]["details"]["missing"]) == (409, "diagnosis.json")


def test_one_predict_at_a_time(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)
    with api.app.state.run_work.execution(run_id):
        response = api.post(run_id, "predict")
    assert (response.status_code, response.json()["error"]["details"]["reason"]) == (409, "step_in_progress")


def test_predict_before_the_analysis_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200

    response = api.post(run_id, "predict")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "cleaned"


def test_predict_on_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    response = make_api().post(UNKNOWN_RUN, "predict")
    assert (response.status_code, response.json()["error"]["code"]) == (404, "NOT_FOUND")


def test_predict_when_the_metrics_are_gone_is_expired(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)
    api.file(run_id, "metrics.json").unlink()
    assert api.post(run_id, "predict").json()["error"]["code"] == "EXPIRED"


def test_a_diagnosis_of_other_months_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)
    diagnosis = api.read_json(run_id, "diagnosis.json")
    diagnosis["frame"]["current"], diagnosis["frame"]["previous"] = "2023-12", "2023-11"
    api.write_json(run_id, "diagnosis.json", diagnosis)

    response = api.post(run_id, "predict")

    assert response.status_code == 409
    error = response.json()["error"]
    assert (error["code"], error["details"]["reason"]) == ("INVALID_STATE", "diagnosis_mismatch")


def test_a_diagnosis_another_version_wrote_is_run_that_stage_again(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)
    diagnosis = api.read_json(run_id, "diagnosis.json")
    diagnosis["schema_version"] = "16.0"
    api.write_json(run_id, "diagnosis.json", diagnosis)

    response = api.post(run_id, "predict")

    assert (response.status_code, response.json()["error"]["code"]) == (409, "INVALID_STATE")
    assert "diagnosis" in response.json()["error"]["message"]


def test_amounts_the_forecast_carries_past_a_float_are_analysis_failed(make_api: MakeApi) -> None:
    # Three months of both signs near the largest float: no band a float
    # carries (4A review 3 #6), refused as too large - never a 500.
    api, run_id = _diagnosed(make_api)
    metrics = api.read_json(run_id, "metrics.json")
    for month, value in zip(metrics["core"]["revenue_by_month"][-4:-1], (1.7e308, -1.7e308, 1.7e308), strict=True):
        month["revenue"] = value
    api.write_json(run_id, "metrics.json", metrics)

    response = api.post(run_id, "predict")

    assert response.status_code == 422, response.text
    error = response.json()["error"]
    assert (error["code"], error["details"]["reason"]) == ("ANALYSIS_FAILED", "amounts_too_large")
    assert "its forecast" in error["message"]


def test_predict_again_replaces_the_forecast_and_sets_the_report_aside(make_api: MakeApi) -> None:
    # CONTRACTS 1: a stage run again removes the later stages' outputs.
    api, run_id = _diagnosed(make_api)
    assert api.post(run_id, "predict").status_code == 200
    api.file(run_id, "report.json").write_text("{}", encoding="utf-8")
    api.file(run_id, "report.html").write_text("<p>", encoding="utf-8")
    diagnosis = api.file(run_id, "diagnosis.json").read_bytes()

    assert api.post(run_id, "predict").status_code == 200

    assert not {"report.json", "report.html"} & api.files(run_id)
    assert api.file(run_id, "diagnosis.json").read_bytes() == diagnosis
