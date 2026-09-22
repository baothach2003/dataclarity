"""GET /api/runs/{id}/profile (SPECS section 8): profile.json, read-only.

Needed by the Review screen's dataset summary strip (SPECS section 4.2 A), which
shows rows/columns/duplicate rows/missing % before schema_inference.json exists
(it is shown already in the Analyzing state) and does not fit in
schema_inference.json (capped at 25 columns, no dataset totals).
"""

from app.models import RunStatus
from tests.backend.api_support import UNKNOWN_RUN, MakeApi, analyzed_run, schema_reply


def test_profile_is_available_once_the_run_is_profiled(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = analyzed_run(api)

    response = api.get(run_id, "profile")

    assert response.status_code == 200
    body = response.json()
    assert body["dataset"]["rows"] == 5
    assert body["dataset"]["columns"] == 5
    assert body["dataset"]["duplicate_rows"] == 1
    assert [c["name"] for c in body["columns"]] == ["sku", "name", "qty", "price", "day"]


def test_profile_before_profiling_is_invalid_state(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()

    response = api.get(run_id, "profile")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_profile_of_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    api = make_api(schema_reply())

    response = api.get(UNKNOWN_RUN, "profile")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_profile_survives_a_run_gone_to_failed(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = analyzed_run(api)
    api.set_status(run_id, RunStatus.FAILED)

    response = api.get(run_id, "profile")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
