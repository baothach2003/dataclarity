"""POST /api/runs/{id}/preview and the frame cache behind it, AI mocked."""

from typing import Any

import pandas as pd
import pytest

from app.models import RunStatus
from stages.ingest import transforms
from app.services.run_memory import FrameCache
from stages.ingest.profiling import read_csv_text
from tests.backend.api_support import MakeApi, edited, make_api_with_plan, planned, schema_reply
from tests.stages.ingest.cleaning_fixtures import make_plan


# --- preview --------------------------------------------------------------------------


def test_preview_returns_the_sample_and_changes_nothing(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    files_before = api.files(run_id)

    response = api.post(run_id, "preview", plan)

    assert response.status_code == 200
    preview = response.json()["preview"]
    assert response.json()["run_id"] == run_id
    assert preview["rows_in_file"] == 5
    assert preview["sample_rows"] == 5
    assert preview["sampled"] is False
    assert preview["rows_after"] == 4  # rows 1 and 3 are the same row: one is dropped
    assert {d["column"] for d in preview["deltas"]} >= {"price", "qty"}
    assert api.status(run_id) is RunStatus.PLANNED
    assert api.files(run_id) == files_before  # no cleaned.csv, no plan_final.json


def test_preview_is_allowed_from_profiled_for_a_plan_built_by_hand(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")  # profiled, and it stays so: no AI plan was asked

    response = api.post(run_id, "preview", make_plan().model_dump(mode="json"))

    assert response.status_code == 200
    assert api.status(run_id) is RunStatus.PROFILED


def test_preview_allows_required_fields_that_are_not_mapped_yet(make_api: MakeApi) -> None:
    # The screen previews while the user is still mapping (SPECS section 10).
    api, run_id, plan = make_api_with_plan(make_api)
    unmapped = edited(plan, "qty", canonical_field="ignore", semantic_type="numeric_discrete")

    assert api.post(run_id, "preview", unmapped).status_code == 200


@pytest.mark.parametrize("status", [
    RunStatus.UPLOADED, RunStatus.CLEANED, RunStatus.ANALYZED,
    RunStatus.IMPORTED, RunStatus.FAILED,
])
def test_preview_out_of_order_is_409(make_api: MakeApi, status: RunStatus) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.set_status(run_id, status)

    response = api.post(run_id, "preview", plan)

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_STATE"
    assert error["details"] == {
        "status": status.value, "allowed": ["profiled", "planned"],
        **({"error_code": api.error_code(run_id)} if api.error_code(run_id) else {}),
    }


def test_preview_refuses_an_illegal_plan_with_every_problem(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    bad = edited(plan, "price", action="normalize_case", params={"case": "lower"})

    response = api.post(run_id, "preview", bad)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_PLAN"
    assert any("normalize_case is not legal" in p for p in error["details"]["problems"])
    assert api.status(run_id) is RunStatus.PLANNED  # the user is still editing


def test_an_action_outside_the_catalog_is_invalid_plan_and_is_not_echoed(
    make_api: MakeApi,
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    bad = edited(plan, "price", action="DROP-TABLE-runs")

    response = api.post(run_id, "preview", bad)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "INVALID_PLAN"
    assert any(p.startswith("column_actions.3.action") for p in error["details"]["problems"])
    assert "DROP-TABLE-runs" not in response.text


@pytest.mark.parametrize("body", [[1, 2], "a plan", 7])
def test_a_body_that_is_not_an_object_is_a_malformed_request(
    make_api: MakeApi, body: Any
) -> None:
    api, run_id, _ = make_api_with_plan(make_api)

    response = api.post(run_id, "preview", body)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_a_missing_body_is_a_malformed_request(make_api: MakeApi) -> None:
    api, run_id, _ = make_api_with_plan(make_api)

    response = api.post(run_id, "preview")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_a_plan_that_is_an_empty_object_is_invalid_plan(make_api: MakeApi) -> None:
    api, run_id, _ = make_api_with_plan(make_api)

    response = api.post(run_id, "preview", {})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PLAN"


def test_an_action_that_fails_on_the_data_fails_the_preview_not_the_run(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = transforms.apply_action

    def failing(action: str, frame: pd.DataFrame, column: str | None, params: Any) -> Any:
        if action == "impute_median":
            raise ArithmeticError("no median")
        return real(action, frame, column, params)

    monkeypatch.setattr(transforms, "apply_action", failing)

    response = api.post(run_id, "preview", plan)

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "CLEANING_FAILED"
    assert error["details"] == {"action": "impute_median", "column": "price"}
    assert api.status(run_id) is RunStatus.PLANNED  # the user can pick another action


# --- the frame cache behind the preview -----------------------------------------------


def count_reads(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    reads: list[int] = []

    def counting(raw: bytes) -> Any:
        reads.append(len(raw))
        return read_csv_text(raw)

    monkeypatch.setattr("app.services.plan_execution.read_csv_text", counting)
    return reads


def test_repeated_previews_read_the_file_once(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    reads = count_reads(monkeypatch)

    for action in ("impute_median", "impute_mean", "impute_median", "impute_mean"):
        assert api.post(run_id, "preview", edited(plan, "price", action=action)).status_code == 200

    assert len(reads) == 1


def test_a_cached_preview_equals_an_uncached_one(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    cold = api.post(run_id, "preview", plan).json()

    warm = api.post(run_id, "preview", plan).json()

    assert warm == cold


def test_a_preview_never_changes_the_frame_the_next_one_uses(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.post(run_id, "preview", plan)
    cached = api.app.state.frame_cache.get_or_load(run_id, lambda: pytest.fail("not cached"))
    snapshot = cached.copy(deep=True)

    for action in ("impute_median", "impute_mean"):
        api.post(run_id, "preview", edited(plan, "price", action=action))
    api.post(run_id, "preview", edited(plan, "name", action="drop_rows_missing", params={}))

    pd.testing.assert_frame_equal(cached, snapshot)


def test_a_file_too_big_for_the_cache_is_still_previewed_every_time(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.app.state.frame_cache = FrameCache(max_bytes=10, ttl_seconds=900)  # smaller than any file
    reads = count_reads(monkeypatch)

    first = api.post(run_id, "preview", plan)
    second = api.post(run_id, "preview", plan)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert len(reads) == 2
    assert api.app.state.frame_cache.cached_bytes == 0


def test_the_cache_is_configured_from_the_settings(make_api: MakeApi) -> None:
    api = make_api(preview_cache_max_mb=123, preview_cache_ttl_seconds=45)

    cache = api.app.state.frame_cache

    assert cache.max_bytes == 123 * 1_048_576
    assert cache.ttl_seconds == 45
