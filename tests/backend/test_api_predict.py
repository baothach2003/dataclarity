"""POST /api/runs/{id}/predict (session 4C) - written before the code,
widened by its review, and rewritten for the report redesign's step 4 as
Thach's option (d). Stage 4 writes forecast.json 2.1: the computed forecast
and the code-written suggested actions - it asks no AI (Q50 (d), Q53).
Allowed from `analyzed` once diagnosis.json exists; the run stays
`analyzed`.
"""

from contextlib import contextmanager
from typing import Any

import pandas as pd

from app.models import RunStatus
from contracts import ForecastContract
from tests.backend.api_support import UNKNOWN_RUN, MakeApi, codes, make_api_with_plan
from tests.backend.test_api_diagnose import _monthly_analyzed_run


def _price_rise_csv() -> bytes:
    """The monthly fixture with the Mug's price up from February 2024:
    stage 3 names the price change (rule 6, P1), so one claim is selected."""
    days = pd.date_range("2023-01-01", "2024-03-10", freq="D")
    lines = ["sku,name,qty,price,day"]
    for day in days:
        price = "14" if day >= pd.Timestamp("2024-02-01") else "10"
        lines.append(f"A1,Mug,{2 + day.day % 3},{price},{day.date()}")
        lines.append(f"B2,Cup,1,4.50,{day.date()}")
    return ("\n".join(lines) + "\n").encode()


def _diagnosed(make_api: MakeApi, *, named: bool = True, **settings: Any) -> tuple[Any, str]:
    api, run_id = _monthly_analyzed_run(make_api, _price_rise_csv() if named else None, **settings)
    assert api.post(run_id, "diagnose").status_code == 200
    return api, run_id


# --- the forecast and the code-written actions ----------------------------------------------------------------


def test_predict_writes_the_forecast_and_the_code_written_actions(make_api: MakeApi) -> None:
    api, run_id = _diagnosed(make_api)
    calls = api.ai_requests

    response = api.post(run_id, "predict")

    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["run_id"], body["status"], codes(body)) == (run_id, "analyzed", [])
    forecast = ForecastContract.model_validate(body["forecast"])
    assert forecast == ForecastContract.model_validate(api.read_json(run_id, "forecast.json"))
    assert (forecast.schema_version, forecast.model_used, forecast.recommendations) == ("2.1", None, None)
    assert (forecast.actions_status, forecast.actions_model) == ("list", None)
    (action,) = forecast.actions
    assert (action.claim, action.hypothesis_id) == ("K1", "P1")
    assert action.action == "Watch whether customers keep buying at the new prices."  # the catalog's
    assert action.fact.startswith("Inside the chart's average price per item")
    assert forecast.forecast.insufficient_history is False
    assert api.ai_requests == calls  # stage 4 asks no AI
    assert api.status(run_id) is RunStatus.ANALYZED


def test_no_claim_selected_lists_no_action(make_api: MakeApi) -> None:
    # Design 4.1: the unchanged fixture names no cause the shop acts on.
    api, run_id = _diagnosed(make_api, named=False)

    response = api.post(run_id, "predict")

    assert response.status_code == 200, response.text
    forecast = response.json()["forecast"]
    assert (forecast["actions_status"], forecast["actions"], codes(response.json())) == ("list", [], [])


def test_predict_never_asks_the_ai_however_often_it_runs(make_api: MakeApi) -> None:
    # 4C's attempt count and shared retry are gone with the AI step (Q53):
    # a predict run again writes the same actions, and nothing is asked.
    api, run_id = _diagnosed(make_api)
    calls = api.ai_requests
    first = api.post(run_id, "predict").json()["forecast"]

    for _ in range(3):
        again = api.post(run_id, "predict")
        assert again.status_code == 200 and again.json()["forecast"]["actions"] == first["actions"]
    assert api.ai_requests == calls


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
