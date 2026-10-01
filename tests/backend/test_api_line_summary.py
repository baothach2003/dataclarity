"""POST /api/runs/{id}/line-summary (session 2E-t3): Review's whole-file view
of the line taxonomy, for the plan and the answers as they stand. The
preview's rules - read only, the planning states, a plan that does not work
is an error the user fixes - on the whole file. AI mocked."""

from typing import Any

import pandas as pd
import pytest

from app.models import RunStatus
from contracts import CleaningPlanContract
from stages.ingest import transforms
from stages.ingest.line_summary import NOT_CLASSED, line_summary
from stages.ingest.profiling import read_csv_text
from tests.backend.api_support import MakeApi, edited, make_api_with_plan, schema_reply
from tests.stages.ingest.cleaning_fixtures import RAW_CSV, make_plan


def test_the_whole_files_summary_is_the_stages_and_changes_nothing(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    files_before = api.files(run_id)

    response = api.post(run_id, "line-summary", plan)

    assert response.status_code == 200, response.text
    body = response.json()
    expected = line_summary(read_csv_text(RAW_CSV).frame, CleaningPlanContract.model_validate(plan))
    assert body["summary"] == expected.summary.model_dump(mode="json")  # type: ignore[union-attr]  # classed: a summary
    assert (body["run_id"], body["reserved_renames"], body["summary_unavailable_reason"]) == (run_id, [], None)
    assert body["summary"]["lines"] == 5  # the copy stays, as execute keeps it: the AI's removal is stripped (2E-u4)
    assert api.status(run_id) is RunStatus.PLANNED
    assert api.files(run_id) == files_before


def test_the_answers_as_they_stand_are_read(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    answered: dict[str, Any] = {**plan, "confirmations": {
        **plan["confirmations"], "line_classes": [{"value": "C3", "field": "sku", "line_class": "cost"}]}}

    before = api.post(run_id, "line-summary", plan).json()["summary"]
    after = api.post(run_id, "line-summary", answered).json()["summary"]

    # C3's 5 @ 12.50 leaves revenue as a cost.
    assert after["identity"]["net_revenue"] == pytest.approx(before["identity"]["net_revenue"] - 62.5)
    assert [(r["line_class"], r["lines"], r["amount"]) for r in after["outside_revenue"]] == [("cost", 1, 62.5)]


def test_without_a_quantity_mapped_the_summary_waits(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    unmapped = edited(plan, "qty", canonical_field="ignore", semantic_type="numeric_discrete")

    response = api.post(run_id, "line-summary", unmapped)

    assert response.status_code == 200
    body = response.json()
    assert (body["summary"], body["summary_unavailable_reason"], body["reserved_renames"]) == (None, NOT_CLASSED, [])


def test_is_allowed_from_profiled(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")

    response = api.post(run_id, "line-summary", make_plan().model_dump(mode="json"))

    assert response.status_code == 200
    assert api.status(run_id) is RunStatus.PROFILED


@pytest.mark.parametrize("status", [RunStatus.UPLOADED, RunStatus.CLEANED, RunStatus.ANALYZED,
                                    RunStatus.IMPORTED, RunStatus.FAILED])
def test_out_of_order_is_409(make_api: MakeApi, status: RunStatus) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.set_status(run_id, status)

    response = api.post(run_id, "line-summary", plan)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_an_illegal_plan_is_422_and_the_run_is_untouched(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    illegal = edited(plan, "qty", action="parse_datetime")

    response = api.post(run_id, "line-summary", illegal)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_PLAN"
    assert api.status(run_id) is RunStatus.PLANNED


def test_an_action_that_fails_on_the_data_is_422_not_a_failed_run(
    make_api: MakeApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    real = transforms.apply_action

    def failing(action: str, frame: pd.DataFrame, column: str | None, params: Any) -> Any:
        if action == "impute_median":
            raise ArithmeticError("no median")
        return real(action, frame, column, params)

    monkeypatch.setattr(transforms, "apply_action", failing)

    response = api.post(run_id, "line-summary", plan)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CLEANING_FAILED"
    assert api.status(run_id) is RunStatus.PLANNED


# --- review 1 (2E-t3): the cases SPECS section 10 asks a test of, the rename through the endpoint, one at a time


def test_an_unknown_run_is_404(make_api: MakeApi) -> None:
    from tests.backend.api_support import UNKNOWN_RUN

    response = make_api().post(UNKNOWN_RUN, "line-summary", make_plan().model_dump(mode="json"))

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_a_raw_file_that_disappeared_is_410(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    api.file(run_id, "raw.csv").unlink()

    response = api.post(run_id, "line-summary", plan)

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "EXPIRED"


@pytest.mark.parametrize("body", [[1, 2], "a plan", None])
def test_a_body_that_is_not_a_plan_is_a_malformed_request(make_api: MakeApi, body: Any) -> None:
    api, run_id, _ = make_api_with_plan(make_api)

    response = api.post(run_id, "line-summary", body) if body is not None else api.post(run_id, "line-summary")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_the_rename_is_said_through_the_endpoint(make_api: MakeApi) -> None:
    from tests.stages.ingest.schema_answers import answer, column
    from tests.backend.api_support import SCHEMA_COLUMNS

    api = make_api(answer([*SCHEMA_COLUMNS, column("line_class")], dataset_issues=[]))
    csv = b"sku,name,qty,price,day,line_class\nA1,Mug,3,9.99,2024-01-05,mine\nC3,Cup,5,12.50,2024-01-07,mine\n"
    run_id = api.upload(csv)
    assert api.post(run_id, "analyze-schema").status_code == 200
    plan = make_plan().model_dump(mode="json")
    plan["column_actions"].append({"source_name": "line_class", "semantic_type": "text", "canonical_field": "ignore",
                                   "action": "flag_only", "params": {}, "rationale": "", "alternatives": [],
                                   "edited_by_user": False})

    body = api.post(run_id, "line-summary", plan).json()

    assert body["reserved_renames"] == [{"source": "line_class", "written_as": "line_class_source",
                                         "holds": "each line's class"}]
    assert body["summary"]["lines"] == 2


def test_one_summary_at_a_time_per_run(make_api: MakeApi, monkeypatch: pytest.MonkeyPatch) -> None:
    # A second summary while one runs would only pile the work up (review 1 #1).
    import threading

    api, run_id, plan = make_api_with_plan(make_api)
    started, release = threading.Event(), threading.Event()
    real = line_summary

    def slow(frame: pd.DataFrame, submitted: CleaningPlanContract) -> Any:
        started.set()
        release.wait(5)
        return real(frame, submitted)

    monkeypatch.setattr("app.services.plan_execution.line_summary", slow)
    first: dict[str, Any] = {}
    worker = threading.Thread(target=lambda: first.update(response=api.post(run_id, "line-summary", plan)))
    worker.start()
    assert started.wait(5)

    second = api.post(run_id, "line-summary", plan)
    preview = api.post(run_id, "preview", plan)
    executed = api.post(run_id, "execute", plan)  # Confirm is never kept waiting either
    release.set()
    worker.join(10)

    assert second.status_code == 409
    assert second.json()["error"]["details"] == {"reason": "summary_in_progress"}
    assert preview.status_code == 200
    assert executed.status_code == 200, executed.text
    assert first["response"].status_code == 200
    # The run is cleaned now: a summary is a Review step, no longer allowed.
    assert api.post(run_id, "line-summary", plan).status_code == 409


def test_a_failed_summary_frees_the_run_for_the_next(make_api: MakeApi) -> None:
    # 2E-t3 review 3 #5: the per-run lock is released when a summary fails.
    api, run_id, plan = make_api_with_plan(make_api)

    assert api.post(run_id, "line-summary", edited(plan, "qty", action="parse_datetime")).status_code == 422
    assert api.post(run_id, "line-summary", plan).status_code == 200
