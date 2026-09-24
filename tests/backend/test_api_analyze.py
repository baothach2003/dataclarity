"""POST /api/runs/{id}/analyze: success, the state machine, and the ways
stage 2 cannot compute metrics for a run (2D). No AI is involved in this
stage (docs/adr/0002), so these tests do not need a fake AI reply for the
analyze step itself - only to reach `cleaned` first, same as every other
post-execute test in this file's siblings.
"""

import threading
from typing import Any

import pytest

from app.models import RunStatus
from tests.backend.api_support import (
    UNKNOWN_RUN,
    MakeApi,
    edited,
    make_api_with_plan,
    plan_reply,
    planned,
    schema_reply,
    unmapped_body,
)


def _cleaned_run(make_api: MakeApi) -> tuple[Any, str]:
    api, run_id, plan = make_api_with_plan(make_api)
    response = api.post(run_id, "execute", plan)
    assert response.status_code == 200, response.text
    return api, run_id


# --- analyze: the happy path -----------------------------------------------------------


def test_analyze_computes_metrics_and_moves_the_run_to_analyzed(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)

    response = api.post(run_id, "analyze")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "analyzed"
    assert body["notices"] == []
    metrics = body["metrics"]
    assert metrics["by_dimension"]["country"] == []  # no canonical field carries country data
    assert api.status(run_id) is RunStatus.ANALYZED
    assert api.read_json(run_id, "metrics.json")["schema_version"] == "2.0"  # 2E major bump


def test_analyze_is_allowed_from_an_already_analyzed_run(make_api: MakeApi) -> None:
    api, run_id = _cleaned_run(make_api)
    first = api.post(run_id, "analyze")
    assert first.status_code == 200

    second = api.post(run_id, "analyze")

    assert second.status_code == 200
    assert second.json()["status"] == "analyzed"
    assert api.status(run_id) is RunStatus.ANALYZED


# --- analyze: the state machine --------------------------------------------------------


def test_analyze_out_of_order_is_invalid_state(make_api: MakeApi) -> None:
    api, run_id, _plan = make_api_with_plan(make_api)  # planned, never executed

    response = api.post(run_id, "analyze")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_STATE"
    assert error["details"]["status"] == "planned"
    assert api.status(run_id) is RunStatus.PLANNED


def test_analyze_on_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    api = make_api()

    response = api.post(UNKNOWN_RUN, "analyze")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


# --- analyze: cannot compute metrics for this data --------------------------------------


def test_missing_unit_price_mapping_is_analysis_failed_without_failing_the_run(
    make_api: MakeApi,
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    no_price = edited(plan, "price", canonical_field="ignore", action="flag_only")

    executed = api.post(run_id, "execute", no_price)
    assert executed.status_code == 200, executed.text

    response = api.post(run_id, "analyze")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ANALYSIS_FAILED"
    assert error["details"] == {"canonical_field": "unit_price"}
    # Unlike CLEANING_FAILED, the run is not failed: cleaned.csv is still
    # valid and downloadable, only the optional analysis is unavailable.
    assert api.status(run_id) is RunStatus.CLEANED


def test_not_inventory_run_is_analysis_failed(make_api: MakeApi) -> None:
    api = make_api(schema_reply(domain_confidence=0.2), plan_reply())
    run_id, plan = planned(api)
    executed = api.post(run_id, "execute", unmapped_body(plan))
    assert executed.status_code == 200
    assert [n["code"] for n in executed.json()["notices"]] == ["NOT_INVENTORY"]

    response = api.post(run_id, "analyze")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "ANALYSIS_FAILED"
    assert error["details"]["domain_confidence"] == 0.2
    assert api.status(run_id) is RunStatus.CLEANED


# --- analyze: simultaneous requests for one run (mirrors test_api_races.py) ------------


def test_a_second_analyze_during_the_first_is_refused_not_raced(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id = _cleaned_run(make_api)
    from stages.analyze import assemble

    real = assemble.analyze_run
    inside = threading.Event()
    proceed = threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        inside.set()
        assert proceed.wait(timeout=10), "the test never released the first analyze"
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.metrics.analyze_run", slow)
    first: dict[str, Any] = {}
    worker = threading.Thread(
        target=lambda: first.update(response=api.post(run_id, "analyze")))
    worker.start()
    assert inside.wait(timeout=10)

    second = api.post(run_id, "analyze")
    proceed.set()
    worker.join(timeout=20)

    assert second.status_code == 409
    assert second.json()["error"]["details"]["reason"] == "step_in_progress"
    assert first["response"].status_code == 200
    assert api.status(run_id) is RunStatus.ANALYZED
