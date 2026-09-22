"""POST /api/runs/{id}/plan and the retry budget both AI steps share, AI mocked."""

import pytest

from app.models import RunStatus
from app.services.analysis import default_ai_client_factory
from shared.ai_client import AIClient
from tests.backend.api_support import (
    MakeApi,
    analyzed_run,
    codes,
    plan_reply,
    planned,
    schema_reply,
    unusable_reply,
)


# --- plan: the happy path and the state machine ---------------------------------------


def test_plan_proposes_and_moves_the_run_to_planned(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = analyzed_run(api)

    response = api.post(run_id, "plan")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "planned"
    assert body["notices"] == []
    assert body["plan"]["source"] == "ai"
    assert [a["source_name"] for a in body["plan"]["column_actions"]] == [
        "sku", "name", "qty", "price", "day"]
    assert api.status(run_id) is RunStatus.PLANNED
    assert "plan_proposed.json" in api.files(run_id)
    assert api.messages.calls[1]["model"] == api.settings.model_reasoning


def test_plan_before_the_schema_is_409_and_asks_nothing(make_api: MakeApi) -> None:
    api = make_api(unusable_reply(), unusable_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")  # the AI fails: no schema_inference.json exists
    assert api.ai_requests == 2

    response = api.post(run_id, "plan")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_STATE"
    assert error["details"]["missing"] == "schema_inference.json"
    assert api.status(run_id) is RunStatus.PROFILED
    assert api.ai_requests == 2  # the plan step asked nothing


def test_plan_on_a_run_that_was_never_profiled_is_409(make_api: MakeApi) -> None:
    api = make_api()
    run_id = api.upload()

    response = api.post(run_id, "plan")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "uploaded"
    assert api.ai_requests == 0


@pytest.mark.parametrize("status", [
    RunStatus.PLANNED, RunStatus.CLEANED, RunStatus.FAILED,
])
def test_plan_out_of_order_is_409(make_api: MakeApi, status: RunStatus) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = analyzed_run(api)
    api.set_status(run_id, status)

    response = api.post(run_id, "plan")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["allowed"] == ["profiled"]
    assert api.ai_requests == 1  # only the schema step asked


def test_analyze_schema_after_the_plan_is_409_because_it_would_orphan_the_plan(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = analyzed_run(api)
    api.post(run_id, "plan")

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 409
    assert api.ai_requests == 2


def test_a_schema_that_no_longer_matches_the_profile_is_409(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = analyzed_run(api)
    schema = api.read_json(run_id, "schema_inference.json")
    schema["columns"][0]["source_name"] = "renamed"
    api.write_json(run_id, "schema_inference.json", schema)

    response = api.post(run_id, "plan")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert api.ai_requests == 1
    assert api.status(run_id) is RunStatus.PROFILED


# --- plan: the AI is unavailable, or the file is not inventory data -------------------


def test_plan_with_the_ai_unavailable_is_a_200_and_the_run_stays_profiled(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply(), unusable_reply(), unusable_reply())
    run_id = analyzed_run(api)

    response = api.post(run_id, "plan")

    assert response.status_code == 200
    body = response.json()
    assert body["plan"] is None
    assert body["status"] == "profiled"
    assert codes(body) == ["AI_UNAVAILABLE"]
    assert "plan_proposed.json" not in api.files(run_id)
    assert api.status(run_id) is RunStatus.PROFILED


def test_plan_on_a_not_inventory_run_still_proposes_and_repeats_the_notice(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply(domain_confidence=0.2), plan_reply())
    run_id = analyzed_run(api)

    body = api.post(run_id, "plan").json()

    assert body["plan"] is not None
    assert codes(body) == ["NOT_INVENTORY"]
    assert body["status"] == "planned"


# --- the retry budget is one per run, across both steps -------------------------------


def test_a_retry_spent_on_the_schema_is_not_available_to_the_plan(make_api: MakeApi) -> None:
    api = make_api(unusable_reply(), schema_reply(), unusable_reply())
    run_id = api.upload()
    schema = api.post(run_id, "analyze-schema")  # bad, retry (spent), good
    assert schema.json()["notices"] == []
    assert api.ai_requests == 2

    plan = api.post(run_id, "plan")  # bad, and no retry is left: one request only

    assert plan.status_code == 200
    assert codes(plan.json()) == ["AI_UNAVAILABLE"]
    assert plan.json()["notices"][0]["details"] == {"reason": "invalid_response"}
    assert api.ai_requests == 3


def test_a_retry_not_spent_on_the_schema_is_available_to_the_plan(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), unusable_reply(), plan_reply())
    run_id = analyzed_run(api)
    assert api.ai_requests == 1

    plan = api.post(run_id, "plan")  # bad, retry, good

    assert plan.json()["notices"] == []
    assert plan.json()["plan"] is not None
    assert api.ai_requests == 3


def test_the_budget_is_per_run(make_api: MakeApi) -> None:
    api = make_api(unusable_reply(), schema_reply(), unusable_reply(), schema_reply())
    first, second = api.upload(), api.upload()
    api.post(first, "analyze-schema")  # spends the first run's retry

    result = api.post(second, "analyze-schema")  # the second run still has its own

    assert result.json()["notices"] == []
    assert api.ai_requests == 4


# --- the client the app builds for itself ---------------------------------------------


def test_the_default_client_is_the_real_one_built_from_the_settings_key(
    make_api: MakeApi,
) -> None:
    # Built, never used: the F4 guard fails any test that sends a request.
    factory = default_ai_client_factory(make_api().settings)

    client = factory()

    assert isinstance(client, AIClient)
    assert client.sdk_max_retries == 0  # every retry is ours, counted (AI_PIPELINE section 2)
