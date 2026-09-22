"""What the 1G doubt-review found (H2, M3, M5, L5): a run is never stranded in
`cleaning`, running out of memory or disk is not a verdict on the data, and an id that
cannot name a run never reaches the database."""

from typing import Any

import pandas as pd
import pytest

from app.models import RunStatus
from app.services.analysis import default_ai_client_factory
from stages.ingest import transforms
from tests.backend.api_support import (
    NO_PRICE_CSV,
    PLAN_FILES,
    MakeApi,
    edited,
    failing_writes,
    make_api_with_plan,
    schema_reply,
)
from tests.stages.ingest.cleaning_fixtures import column_action, make_plan


# --- H2: a run is never stranded in `cleaning` ------------------------------------------


def test_a_lost_cleaned_status_still_answers_and_is_recovered_by_the_next_call(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    refused = failing_writes(monkeypatch, RunStatus.CLEANED, times=2)

    done = api.post(run_id, "execute", plan)

    assert done.status_code == 200  # the files are complete and durable
    assert len(refused) == 2
    assert api.status(run_id) is RunStatus.CLEANING  # the write was lost...
    assert PLAN_FILES <= api.files(run_id)

    again = api.post(run_id, "execute", plan)  # ...and the next visit finds the report

    assert again.status_code == 409
    assert again.json()["error"]["details"]["status"] == "cleaned"
    assert api.status(run_id) is RunStatus.CLEANED


def test_a_release_that_fails_does_not_hide_the_invalid_plan_and_the_run_is_freed_later(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    refused = failing_writes(monkeypatch, RunStatus.PLANNED, times=2)
    bad = edited(plan, "price", action="normalize_case", params={"case": "lower"})

    response = api.post(run_id, "execute", bad)

    assert response.status_code == 422  # the user still hears why, not "database is down"
    assert response.json()["error"]["code"] == "INVALID_PLAN"
    assert len(refused) == 2
    assert api.status(run_id) is RunStatus.CLEANING
    assert api.post(run_id, "execute", plan).status_code == 200  # freed by the next call


def test_a_release_that_fails_once_is_tried_again(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    failing_writes(monkeypatch, RunStatus.PLANNED, times=1)
    bad = edited(plan, "price", action="normalize_case", params={"case": "lower"})

    api.post(run_id, "execute", bad)

    assert api.status(run_id) is RunStatus.PLANNED


def test_a_failed_status_that_is_lost_does_not_hide_cleaning_failed(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api = make_api(schema_reply(dataset_issues=[]))
    run_id = api.upload(NO_PRICE_CSV)
    api.post(run_id, "analyze-schema")
    failing_writes(monkeypatch, RunStatus.FAILED, times=2)
    drops_everything = make_plan([
        column_action("sku"), column_action("name"), column_action("qty"),
        column_action("price", "drop_rows_missing"), column_action("day", "parse_datetime"),
    ]).model_dump(mode="json")

    response = api.post(run_id, "execute", drops_everything)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CLEANING_FAILED"
    assert api.status(run_id) is RunStatus.CLEANING
    # Freed on the next visit: nothing finished, so the run may be tried again.
    assert api.post(run_id, "preview", drops_everything).status_code == 200
    assert api.status(run_id) is RunStatus.PLANNED


@pytest.mark.parametrize("step", ["preview", "execute"])
def test_a_run_a_dead_process_left_in_cleaning_is_usable_again(
    make_api: MakeApi, step: str
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.set_status(run_id, RunStatus.CLEANING)  # nothing in this process is executing it

    response = api.post(run_id, step, plan)

    assert response.status_code == 200


def test_a_run_really_being_executed_is_not_mistaken_for_an_abandoned_one(
    make_api: MakeApi,
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.set_status(run_id, RunStatus.CLEANING)

    with api.app.state.run_work.execution(run_id):  # this process is executing it
        response = api.post(run_id, "preview", plan)

    assert response.status_code == 409
    assert api.status(run_id) is RunStatus.CLEANING


# --- M5: a failure of the machine is not a verdict on the data ------------------------------


@pytest.mark.parametrize("error", [MemoryError("Unable to allocate 1.2 GiB"), OSError("disk full")])
def test_running_out_of_memory_or_disk_does_not_fail_the_run(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch, error: Exception
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = transforms.apply_action

    def broken(action: str, frame: pd.DataFrame, column: str | None, params: Any) -> Any:
        if action == "impute_median":
            raise error
        return real(action, frame, column, params)

    monkeypatch.setattr(transforms, "apply_action", broken)

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 500
    assert "allocate" not in response.text and "disk full" not in response.text
    assert api.status(run_id) is RunStatus.PLANNED  # not `failed`: a retry can work
    monkeypatch.setattr(transforms, "apply_action", real)
    assert api.post(run_id, "execute", plan).status_code == 200


# --- M3: an id that cannot name a run is a 404 on every step --------------------------------


@pytest.mark.parametrize("run_id", ["abc%00def", "%00", "A" * 2000, "..%2F..%2Fetc"])
def test_an_odd_run_id_is_not_found(make_api: MakeApi, run_id: str) -> None:
    api = make_api()

    for step in ("analyze-schema", "plan", "preview", "execute"):
        response = api.client.post(f"/api/runs/{run_id}/{step}", json={})
        assert response.status_code == 404, (step, response.text)
        assert response.json()["error"]["code"] == "NOT_FOUND"


# --- L5: the real client is built once ---------------------------------------------------------


def test_the_default_client_is_built_once_and_shared(make_api: MakeApi) -> None:
    factory = default_ai_client_factory(make_api().settings)

    assert factory() is factory()
