"""Simultaneous requests for one run, and the whole flow driven end to end."""

import threading
from typing import Any

import pytest

from app.models import RunStatus
from stages.ingest import cleaning
from tests.backend.api_support import (
    MakeApi,
    edited,
    make_api_with_plan,
    plan_reply,
    price_action,
    schema_reply,
)
from tests.stages.ingest.cleaning_fixtures import RAW_CSV, make_plan


# --- simultaneous requests (1F review, finding 6) -------------------------------------


def test_a_second_execute_during_the_first_is_refused_not_raced(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = cleaning.execute_run
    inside = threading.Event()
    proceed = threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        inside.set()
        assert proceed.wait(timeout=10), "the test never released the first execute"
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.plan_execution.execute_run", slow)
    first: dict[str, Any] = {}
    worker = threading.Thread(
        target=lambda: first.update(response=api.post(run_id, "execute", plan)))
    worker.start()
    assert inside.wait(timeout=10)

    second = api.post(run_id, "execute", plan)
    during = api.status(run_id)
    proceed.set()
    worker.join(timeout=20)

    assert second.status_code == 409
    assert second.json()["error"]["details"]["status"] == "cleaning"
    assert during is RunStatus.CLEANING
    assert first["response"].status_code == 200
    assert api.status(run_id) is RunStatus.CLEANED


def test_a_preview_during_an_execute_is_refused(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = cleaning.execute_run
    inside, proceed = threading.Event(), threading.Event()

    def slow(*args: Any, **kwargs: Any) -> Any:
        inside.set()
        assert proceed.wait(timeout=10)
        return real(*args, **kwargs)

    monkeypatch.setattr("app.services.plan_execution.execute_run", slow)
    worker = threading.Thread(target=lambda: api.post(run_id, "execute", plan))
    worker.start()
    assert inside.wait(timeout=10)

    response = api.post(run_id, "preview", plan)
    proceed.set()
    worker.join(timeout=20)

    assert response.status_code == 409


def test_executes_racing_with_different_plans_leave_one_consistent_result(
    make_api: MakeApi,
) -> None:
    # 1F's review saw the plan of one execute next to the report of another. The
    # claim lets exactly one through, so the three files always agree.
    api, run_id, plan = make_api_with_plan(make_api)
    median, mean = plan, edited(plan, "price", action="impute_mean")
    start = threading.Barrier(6)
    statuses: list[int] = []
    lock = threading.Lock()

    def confirm(body: dict[str, Any]) -> None:
        start.wait()
        code = api.post(run_id, "execute", body).status_code
        with lock:
            statuses.append(code)

    workers = [threading.Thread(target=confirm, args=(median if i % 2 else mean,))
               for i in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=60)

    assert sorted(statuses) == [200, 409, 409, 409, 409, 409]
    final = api.read_json(run_id, "plan_final.json")
    report = api.read_json(run_id, "cleaning_report.json")
    logged = [c["action"] for c in report["changes"] if c["column"] == "price"]
    assert logged == [price_action(final)]
    assert api.status(run_id) is RunStatus.CLEANED


# --- the whole flow, the way the client drives it -------------------------------------


def test_the_whole_flow_from_upload_to_cleaned_with_the_ai_mocked(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    trail: list[RunStatus] = []

    run_id = api.upload()
    trail.append(api.status(run_id))
    assert api.post(run_id, "plan").status_code == 409  # not profiled yet
    assert api.post(run_id, "execute", make_plan().model_dump(mode="json")).status_code == 409

    schema = api.post(run_id, "analyze-schema")
    trail.append(api.status(run_id))
    assert schema.status_code == 200

    plan = api.post(run_id, "plan")
    trail.append(api.status(run_id))
    assert plan.status_code == 200

    preview = api.post(run_id, "preview", plan.json()["plan"])
    trail.append(api.status(run_id))
    assert preview.status_code == 200

    done = api.post(run_id, "execute", plan.json()["plan"])
    trail.append(api.status(run_id))
    assert done.status_code == 200

    assert trail == [
        RunStatus.UPLOADED, RunStatus.PROFILED, RunStatus.PLANNED, RunStatus.PLANNED,
        RunStatus.CLEANED,
    ]
    assert api.ai_requests == 2  # one call per AI step, no retry needed
    assert api.file(run_id, "raw.csv").read_bytes() == RAW_CSV  # the upload is never touched
    for step in ("analyze-schema", "plan", "preview", "execute"):
        assert api.post(run_id, step, plan.json()["plan"]).status_code == 409, step
