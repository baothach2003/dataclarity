"""What the 1G doubt-review found (H1, H3, H4): a bad deployment is not a
run-state error, the AI is asked once at a time and a bounded number of times, and an
answer never claims a state the run no longer has."""

import threading
from pathlib import Path
from typing import Any

import pytest

from app.models import RunStatus
from shared.ai_client import AIClient
from tests.backend.api_support import (
    MakeApi,
    on_ai_call,
    plan_reply,
    schema_reply,
    unusable_reply,
)
from tests.stages.ingest.cleaning_fixtures import make_plan


# --- H1: a file-not-found that is not the run's is not a run-state error --------------


def test_a_missing_prompt_template_is_a_500_that_shows_no_server_path(
    make_api: MakeApi, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    api = make_api(schema_reply())
    api.app.state.ai_client_factory = lambda: AIClient(api.messages, prompts_dir=tmp_path / "none")
    run_id = api.upload()

    with caplog.at_level("ERROR"):
        response = api.post(run_id, "analyze-schema")

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}}
    assert str(tmp_path) not in response.text
    assert api.ai_requests == 0
    # Pins the real cause: a NameError in this test's own setup would also surface as
    # a 500 and could pass unnoticed (Python 3.14 defers annotation evaluation, so a
    # missing import here is not caught until this lambda actually runs).
    assert "FileNotFoundError" in caplog.text


def test_a_missing_upload_is_410_for_the_schema_step_like_for_the_others(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    api.file(run_id, "raw.csv").unlink()

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "EXPIRED"
    assert api.ai_requests == 0


# --- H3: the AI is asked once at a time and a bounded number of times -----------------


def test_a_second_analyze_during_the_first_is_refused_and_asks_nothing(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    inside, proceed = threading.Event(), threading.Event()

    def hold() -> None:
        inside.set()
        assert proceed.wait(timeout=10)

    on_ai_call(api, hold)
    first: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: first.update(r=api.post(run_id, "analyze-schema")))
    worker.start()
    assert inside.wait(timeout=10)

    second = api.post(run_id, "analyze-schema")
    proceed.set()
    worker.join(timeout=20)

    assert second.status_code == 409
    assert second.json()["error"]["details"] == {"reason": "step_in_progress"}
    assert first["r"].status_code == 200
    assert api.ai_requests == 1


def test_an_execute_during_an_ai_step_is_refused(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    inside, proceed = threading.Event(), threading.Event()

    def hold() -> None:
        inside.set()
        assert proceed.wait(timeout=10)

    on_ai_call(api, hold)
    worker = threading.Thread(target=lambda: api.post(run_id, "analyze-schema"))
    worker.start()
    assert inside.wait(timeout=10)

    response = api.post(run_id, "execute", make_plan().model_dump(mode="json"))
    proceed.set()
    worker.join(timeout=20)

    assert response.status_code == 409
    assert response.json()["error"]["details"] == {"reason": "step_in_progress"}
    assert api.status(run_id) is RunStatus.PROFILED  # never claimed


def test_a_step_that_keeps_failing_is_rate_limited_after_three_attempts(
    make_api: MakeApi,
) -> None:
    # Attempt 1 is bad twice (the shared retry), attempts 2 and 3 once each.
    api = make_api(*[unusable_reply()] * 4, schema_reply())
    run_id = api.upload()
    for _ in range(3):
        assert api.post(run_id, "analyze-schema").json()["notices"][0]["code"] == "AI_UNAVAILABLE"

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "RATE_LIMITED"
    assert error["details"] == {"step": "analyze the schema", "attempts": 3}
    assert api.ai_requests == 4  # the fifth reply, a good one, was never asked for


def test_the_two_steps_have_their_own_attempts(make_api: MakeApi) -> None:
    api = make_api(*[unusable_reply()] * 4, schema_reply())
    run_id = api.upload()
    for _ in range(3):
        api.post(run_id, "analyze-schema")

    # The schema step is used up; the run is `profiled` without a schema, so the plan
    # step is refused for that reason, not for the attempts.
    assert api.post(run_id, "plan").json()["error"]["details"]["missing"] == "schema_inference.json"


# --- H4: an answer must not claim a state the run no longer has -----------------------


def test_a_schema_answer_for_a_run_executed_meanwhile_is_409_not_profiled(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    on_ai_call(api, lambda: api.set_status(run_id, RunStatus.CLEANED))

    response = api.post(run_id, "analyze-schema")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "cleaned"
    assert api.status(run_id) is RunStatus.CLEANED
    assert api.app.state.retry_budgets.tracked_runs == []  # not re-created for a finished run


def test_a_plan_for_a_run_executed_meanwhile_is_409_and_never_marks_it_planned(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")
    on_ai_call(api, lambda: api.set_status(run_id, RunStatus.CLEANED))

    response = api.post(run_id, "plan")

    assert response.status_code == 409
    assert response.json()["error"]["details"]["status"] == "cleaned"
    assert api.status(run_id) is RunStatus.CLEANED


def test_an_unavailable_ai_for_a_run_that_moved_on_is_also_409(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), unusable_reply(), unusable_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")
    on_ai_call(api, lambda: api.set_status(run_id, RunStatus.FAILED))

    assert api.post(run_id, "plan").status_code == 409
