"""POST /api/runs/{id}/execute: success, the state machine, an invalid plan."""

import copy

import pytest

from app.models import RunStatus
from stages.ingest import cleaning
from tests.backend.api_support import (
    MakeApi,
    PLAN_FILES,
    edited,
    make_api_with_plan,
    price_action,
    unusable_reply,
)
from tests.stages.ingest.cleaning_fixtures import make_plan


# --- execute: the happy path ----------------------------------------------------------


def test_execute_cleans_the_file_and_moves_the_run_to_cleaned(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cleaned"
    assert body["notices"] == []
    report = body["report"]
    assert (report["rows_in"], report["rows_out"]) == (5, 4)
    assert report["column_mapping"] == {
        "sku": "sku", "name": "product_name", "qty": "quantity",
        "price": "unit_price", "day": "transaction_date",
    }
    assert api.status(run_id) is RunStatus.CLEANED
    assert PLAN_FILES <= api.files(run_id)
    assert api.read_json(run_id, "cleaning_report.json")["rows_out"] == 4


def test_execute_runs_the_plan_the_user_submitted_not_the_proposal(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert price_action(plan) == "impute_median"
    mine = edited(plan, "price", action="impute_mean")

    report = api.post(run_id, "execute", mine).json()["report"]

    logged = [c["action"] for c in report["changes"] if c["column"] == "price"]
    assert logged == ["impute_mean"]
    final = api.read_json(run_id, "plan_final.json")
    assert price_action(final) == "impute_mean"
    assert price_action(api.read_json(run_id, "plan_proposed.json")) == "impute_median"


@pytest.mark.parametrize(("edit", "source"), [(False, "ai"), (True, "user_edited")])
def test_the_backend_sets_the_source_of_the_plan(
    make_api: MakeApi, edit: bool, source: str
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    body = edited(plan, "price", action="impute_mean") if edit else copy.deepcopy(plan)
    body["source"] = "manual"  # whatever the client claims is ignored

    api.post(run_id, "execute", body)

    assert api.read_json(run_id, "plan_final.json")["source"] == source


def test_a_client_flag_saying_nothing_was_edited_does_not_make_an_edit_look_like_the_ai(
    make_api: MakeApi,
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    body = edited(plan, "price", action="impute_mean")
    for column in body["column_actions"]:
        column["edited_by_user"] = False

    api.post(run_id, "execute", body)

    assert api.read_json(run_id, "plan_final.json")["source"] == "user_edited"


def test_a_plan_built_by_hand_without_a_proposal_is_manual(make_api: MakeApi) -> None:
    api = make_api(unusable_reply(), unusable_reply())  # the AI fails at the schema step
    run_id = api.upload()
    api.post(run_id, "analyze-schema")

    response = api.post(run_id, "execute", make_plan().model_dump(mode="json"))

    assert response.status_code == 200
    assert api.read_json(run_id, "plan_final.json")["source"] == "manual"
    assert api.status(run_id) is RunStatus.CLEANED


def test_execute_forgets_what_the_run_kept_in_memory(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.post(run_id, "preview", plan)
    assert run_id in api.app.state.frame_cache.cached_runs
    assert run_id in api.app.state.retry_budgets.tracked_runs

    api.post(run_id, "execute", plan)

    assert api.app.state.frame_cache.cached_runs == []
    assert api.app.state.retry_budgets.tracked_runs == []


# --- execute: the state machine -------------------------------------------------------


@pytest.mark.parametrize("status", [
    RunStatus.UPLOADED, RunStatus.CLEANED, RunStatus.ANALYZED,
    RunStatus.IMPORTED, RunStatus.FAILED,
])
def test_execute_out_of_order_is_409_and_writes_nothing(
    make_api: MakeApi, status: RunStatus
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.set_status(run_id, status)

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
    assert api.status(run_id) is status
    assert not PLAN_FILES & api.files(run_id)


def test_a_run_cannot_be_executed_twice(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200
    before = {n: api.file(run_id, n).read_bytes() for n in PLAN_FILES}

    again = api.post(run_id, "execute", plan)

    assert again.status_code == 409
    assert again.json()["error"]["details"]["status"] == "cleaned"
    assert {n: api.file(run_id, n).read_bytes() for n in PLAN_FILES} == before


def test_a_cleaned_run_cannot_be_previewed_or_analyzed_again(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.post(run_id, "execute", plan)

    for step in ("preview", "analyze-schema", "plan"):
        assert api.post(run_id, step, plan).status_code == 409, step


# --- execute: a plan that is not valid leaves the run as it was -----------------------


def test_an_illegal_plan_is_refused_and_the_run_can_be_confirmed_again(
    make_api: MakeApi,
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    bad = edited(plan, "price", action="normalize_case", params={"case": "lower"})

    refused = api.post(run_id, "execute", bad)

    assert refused.status_code == 422
    assert refused.json()["error"]["code"] == "INVALID_PLAN"
    assert api.status(run_id) is RunStatus.PLANNED  # released, not stuck in `cleaning`
    assert not PLAN_FILES & api.files(run_id)
    assert api.post(run_id, "execute", plan).status_code == 200


def test_execute_needs_the_required_fields_that_preview_does_not(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    dropped = edited(plan, "qty", action="drop_column", params={})

    response = api.post(run_id, "execute", dropped)

    assert response.status_code == 422
    problems = response.json()["error"]["details"]["problems"]
    assert any("required field quantity" in p for p in problems)
    assert api.status(run_id) is RunStatus.PLANNED


def test_an_action_outside_the_catalog_never_claims_the_run(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)

    response = api.post(run_id, "execute", edited(plan, "price", action="nope"))

    assert response.status_code == 422
    assert api.status(run_id) is RunStatus.PLANNED
