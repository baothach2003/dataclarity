"""POST /api/runs/{id}/analyze-schema (SPECS section 8), AI mocked."""

import shutil

import anthropic
import httpx2
import pytest

from app.models import RunStatus
from app.services.analysis import NOT_INVENTORY_BELOW
from tests.backend.api_support import MakeApi, UNKNOWN_RUN, codes, schema_reply, unusable_reply


# --- analyze-schema: the happy path ---------------------------------------------------


def test_analyze_schema_profiles_infers_and_leaves_the_run_profiled(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["status"] == "profiled"
    assert body["notices"] == []
    assert [c["source_name"] for c in body["schema_inference"]["columns"]] == [
        "sku", "name", "qty", "price", "day"]
    assert api.status(run_id) is RunStatus.PROFILED
    assert {"raw.csv", "profile.json", "schema_inference.json"} <= api.files(run_id)
    assert api.ai_requests == 1


def test_the_schema_step_asks_the_reasoning_model_named_in_the_settings(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()

    api.post(run_id, "analyze-schema")

    assert api.messages.calls[0]["model"] == api.settings.model_reasoning


def test_an_answer_already_given_is_final_and_the_ai_is_not_asked_again(
    make_api: MakeApi,
) -> None:
    # SPECS section 11: one AI call per step. Asking again would also let a caller keep
    # asking until the AI called the file "not inventory" (which waives a rule).
    api = make_api(schema_reply(), schema_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")
    schema_before = api.file(run_id, "schema_inference.json").read_bytes()

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_STATE"
    assert error["details"]["existing"] == "schema_inference.json"
    assert api.ai_requests == 1
    assert api.file(run_id, "schema_inference.json").read_bytes() == schema_before


# --- analyze-schema: the state machine ------------------------------------------------


@pytest.mark.parametrize("status", [
    RunStatus.PLANNED, RunStatus.CLEANED, RunStatus.ANALYZED,
    RunStatus.IMPORTED, RunStatus.FAILED,
])
def test_analyze_schema_out_of_order_is_409_and_asks_nothing(
    make_api: MakeApi, status: RunStatus
) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    api.set_status(run_id, status)

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_STATE"
    assert error["details"]["status"] == status.value
    assert error["details"]["allowed"] == ["uploaded", "profiled"]
    assert api.ai_requests == 0
    assert api.status(run_id) is status


@pytest.mark.parametrize("run_id", [UNKNOWN_RUN, "not-a-uuid"])
def test_a_run_that_does_not_exist_is_404_on_every_step(make_api: MakeApi, run_id: str) -> None:
    api = make_api()

    for step in ("analyze-schema", "plan", "preview", "execute"):
        response = api.post(run_id, step, {})
        assert response.status_code == 404, step
        assert response.json()["error"]["code"] == "NOT_FOUND", step


def test_an_expired_run_is_410_on_every_step(make_api: MakeApi) -> None:
    api = make_api()
    run_id = api.upload()
    api.set_status(run_id, RunStatus.EXPIRED)

    for step in ("analyze-schema", "plan", "preview", "execute"):
        response = api.post(run_id, step, {})
        assert response.status_code == 410, step
        assert response.json()["error"]["code"] == "EXPIRED", step


def test_a_run_whose_files_are_gone_is_410(make_api: MakeApi) -> None:
    # The retention cleanup removes the directory; the row may outlive it briefly.
    api = make_api(schema_reply())
    run_id = api.upload()
    shutil.rmtree(api.runs_root / run_id)

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "EXPIRED"
    assert api.ai_requests == 0


# --- analyze-schema: errors from profiling --------------------------------------------


def test_a_header_only_file_is_empty_file_and_fails_the_run(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload(b"sku,qty\n")

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "EMPTY_FILE"
    assert api.status(run_id) is RunStatus.FAILED
    assert api.error_code(run_id) == "EMPTY_FILE"
    assert api.ai_requests == 0


def test_a_file_that_cannot_be_parsed_is_parse_failed_and_fails_the_run(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply())
    run_id = api.upload(b"sku,qty\nA1,3\nB2,4,extra,fields\n")

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PARSE_FAILED"
    assert api.status(run_id) is RunStatus.FAILED
    assert api.error_code(run_id) == "PARSE_FAILED"


def test_a_failed_run_says_why_when_it_is_called_again(make_api: MakeApi) -> None:
    api = make_api()
    run_id = api.upload(b"sku,qty\n")
    api.post(run_id, "analyze-schema")

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["error_code"] == "EMPTY_FILE"


# --- analyze-schema: the AI is unavailable or the data is not inventory ---------------


def test_an_ai_that_answers_badly_twice_is_a_200_with_an_ai_unavailable_notice(
    make_api: MakeApi,
) -> None:
    api = make_api(unusable_reply(), unusable_reply())
    run_id = api.upload()

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 200
    body = response.json()
    assert body["schema_inference"] is None
    assert body["status"] == "profiled"
    assert body["notices"] == [{
        "code": "AI_UNAVAILABLE",
        "message": body["notices"][0]["message"],
        "details": {"reason": "invalid_response"},
    }]
    assert "schema_inference.json" not in api.files(run_id)
    assert api.status(run_id) is RunStatus.PROFILED  # profiling is done; a retry is possible


@pytest.mark.parametrize(("failure", "reason"), [
    (anthropic.APITimeoutError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")), "timeout"),
    (anthropic.APIConnectionError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages")), "network"),
])
def test_the_reason_the_ai_failed_reaches_the_notice(
    make_api: MakeApi, failure: Exception, reason: str
) -> None:
    api = make_api(failure)
    run_id = api.upload()

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 200
    assert response.json()["notices"][0]["details"] == {"reason": reason}


def test_a_transient_failure_can_be_retried_and_then_succeeds(make_api: MakeApi) -> None:
    api = make_api(unusable_reply(), unusable_reply(), schema_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 200
    assert response.json()["notices"] == []
    assert response.json()["schema_inference"] is not None


@pytest.mark.parametrize(("confidence", "flagged"), [
    (0.0, True), (0.3, True), (0.49, True), (0.5, False), (0.93, False),
])
def test_not_inventory_is_flagged_below_the_threshold_only(
    make_api: MakeApi, confidence: float, flagged: bool
) -> None:
    assert NOT_INVENTORY_BELOW == 0.5  # SPECS section 10
    api = make_api(schema_reply(domain_confidence=confidence))
    run_id = api.upload()

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 200
    body = response.json()
    assert codes(body) == (["NOT_INVENTORY"] if flagged else [])
    assert body["schema_inference"] is not None  # the user sees what the AI made of the file
    assert api.status(run_id) is RunStatus.PROFILED  # not pushed forward


def test_the_not_inventory_notice_carries_the_confidence_and_the_reasoning(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply(domain_confidence=0.2))
    run_id = api.upload()

    notice = api.post(run_id, "analyze-schema").json()["notices"][0]

    assert notice["details"]["domain_confidence"] == 0.2
    assert notice["details"]["domain_reasoning"] == "columns resemble product / quantity / price"
    assert "inventory" in notice["message"].lower()
