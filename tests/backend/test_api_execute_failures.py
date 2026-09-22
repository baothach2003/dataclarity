"""POST /api/runs/{id}/execute when it fails, and for non-inventory data."""

from typing import Any

import pandas as pd
import pytest

from app.models import RunStatus
from stages.ingest import cleaning, transforms
from tests.backend.api_support import (
    MakeApi,
    PLAN_FILES,
    NO_PRICE_CSV,
    edited,
    make_api_with_plan,
    plan_reply,
    planned,
    schema_reply,
    unmapped_body,
)
from tests.stages.ingest.cleaning_fixtures import column_action, make_plan


# --- execute: a valid plan that fails on this data ------------------------------------


def test_a_plan_that_leaves_no_row_fails_the_run_with_cleaning_failed(make_api: MakeApi) -> None:
    api = make_api(schema_reply(dataset_issues=[]))
    run_id = api.upload(NO_PRICE_CSV)
    api.post(run_id, "analyze-schema")
    every_row_dropped = make_plan([
        column_action("sku"), column_action("name"), column_action("qty"),
        column_action("price", "drop_rows_missing"), column_action("day", "parse_datetime"),
    ])
    api.post(run_id, "preview", every_row_dropped.model_dump(mode="json"))  # fills the cache

    response = api.post(run_id, "execute", every_row_dropped.model_dump(mode="json"))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "CLEANING_FAILED"
    assert "every row" in error["message"]
    assert "details" not in error  # no single action to name: the plan as a whole left nothing
    assert api.status(run_id) is RunStatus.FAILED
    assert api.error_code(run_id) == "CLEANING_FAILED"
    assert not PLAN_FILES & api.files(run_id)
    assert api.app.state.frame_cache.cached_runs == []
    assert api.app.state.retry_budgets.tracked_runs == []


def test_an_action_that_raises_names_itself_and_fails_the_run(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = transforms.apply_action

    def failing(action: str, frame: pd.DataFrame, column: str | None, params: Any) -> Any:
        if action == "impute_median":
            raise ArithmeticError("no median")
        return real(action, frame, column, params)

    monkeypatch.setattr(transforms, "apply_action", failing)

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "CLEANING_FAILED"
    assert error["details"] == {"action": "impute_median", "column": "price"}
    assert "impute_median" in error["message"] and "price" in error["message"]
    assert api.status(run_id) is RunStatus.FAILED
    assert not PLAN_FILES & api.files(run_id)


def test_a_failed_run_stays_failed_and_says_why(make_api: MakeApi) -> None:
    api = make_api(schema_reply(dataset_issues=[]))
    run_id = api.upload(NO_PRICE_CSV)
    api.post(run_id, "analyze-schema")
    body = make_plan([
        column_action("sku"), column_action("name"), column_action("qty"),
        column_action("price", "drop_rows_missing"), column_action("day", "parse_datetime"),
    ]).model_dump(mode="json")
    api.post(run_id, "execute", body)

    again = api.post(run_id, "execute", make_plan().model_dump(mode="json"))

    assert again.status_code == 409
    assert again.json()["error"]["details"]["error_code"] == "CLEANING_FAILED"


# --- execute: what goes wrong that is not the plan's fault ----------------------------


def test_an_unexpected_error_returns_the_run_so_the_user_can_try_again(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = cleaning.execute_run

    def full_disk(*args: Any, **kwargs: Any) -> Any:
        raise OSError("No space left on device: /secret/path")

    monkeypatch.setattr("app.services.plan_execution.execute_run", full_disk)

    failed = api.post(run_id, "execute", plan)

    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret" not in failed.text
    assert api.status(run_id) is RunStatus.PLANNED  # not stuck in `cleaning`
    monkeypatch.setattr("app.services.plan_execution.execute_run", real)
    assert api.post(run_id, "execute", plan).status_code == 200


def test_a_raw_file_that_disappeared_is_410_and_the_run_is_released(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.file(run_id, "raw.csv").unlink()

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "EXPIRED"
    assert api.status(run_id) is RunStatus.PLANNED


def test_a_raw_file_that_disappeared_is_410_for_a_preview_too(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.file(run_id, "raw.csv").unlink()

    response = api.post(run_id, "preview", plan)

    assert response.status_code == 410


# --- a file that is not inventory data ------------------------------------------------


def test_a_not_inventory_run_can_be_cleaned_without_the_required_fields(
    make_api: MakeApi,
) -> None:
    api = make_api(schema_reply(domain_confidence=0.2), plan_reply())
    run_id, plan = planned(api)

    response = api.post(run_id, "execute", unmapped_body(plan))

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cleaned"
    assert [n["code"] for n in body["notices"]] == ["NOT_INVENTORY"]
    assert body["report"]["column_mapping"] == {}
    assert PLAN_FILES <= api.files(run_id)


def test_the_waiver_is_only_for_a_run_the_ai_called_not_inventory(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)  # confidence 0.93

    response = api.post(run_id, "execute", unmapped_body(plan))

    assert response.status_code == 422
    problems = response.json()["error"]["details"]["problems"]
    assert any("required field product_name is not mapped" in p for p in problems)
    assert api.status(run_id) is RunStatus.PLANNED


def test_a_not_inventory_run_still_obeys_every_other_plan_rule(make_api: MakeApi) -> None:
    api = make_api(schema_reply(domain_confidence=0.2), plan_reply())
    run_id, plan = planned(api)
    bad = edited(unmapped_body(plan), "price", action="normalize_case", params={"case": "lower"})

    response = api.post(run_id, "execute", bad)

    assert response.status_code == 422
    assert api.status(run_id) is RunStatus.PLANNED
