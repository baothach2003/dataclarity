"""GET /api/runs/{id}/download/cleaned.csv: not in SPECS section 8's 1G table
(no download endpoint existed), but the Results screen (SPECS section 4.3)
needs it and the report alone (already in `execute`'s response) is not the
cleaned data itself.
"""

import re

from app.models import RunStatus
from tests.backend.api_support import (
    UNKNOWN_RUN,
    MakeApi,
    make_api_with_plan,
    plan_reply,
    schema_reply,
)


def test_download_returns_the_cleaned_file_once_the_run_is_cleaned(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    assert api.post(run_id, "execute", plan).status_code == 200

    response = api.get(run_id, "download/cleaned.csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="cleaned_sales.csv"' in response.headers["content-disposition"]
    assert response.text == api.file(run_id, "cleaned.csv").read_text(encoding="utf-8")


def test_download_sanitizes_a_hostile_filename(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = api.upload(filename='sales"; evil\r\nX-Injected: yes.csv')
    api.post(run_id, "analyze-schema")
    plan = api.post(run_id, "plan").json()["plan"]
    assert api.post(run_id, "execute", plan).status_code == 200

    response = api.get(run_id, "download/cleaned.csv")

    assert response.status_code == 200
    disposition = response.headers["content-disposition"]
    assert "\r" not in disposition
    assert "\n" not in disposition
    assert re.fullmatch(r'attachment; filename="cleaned_[A-Za-z0-9._-]+\.csv"', disposition)


def test_download_before_cleaned_is_invalid_state(make_api: MakeApi) -> None:
    api = make_api(schema_reply())
    run_id = api.upload()

    response = api.get(run_id, "download/cleaned.csv")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"


def test_download_of_an_unknown_run_is_not_found(make_api: MakeApi) -> None:
    api = make_api(schema_reply())

    response = api.get(UNKNOWN_RUN, "download/cleaned.csv")

    assert response.status_code == 404


def test_download_survives_a_run_gone_to_failed(make_api: MakeApi) -> None:
    api, run_id, _plan = make_api_with_plan(make_api)
    api.set_status(run_id, RunStatus.FAILED)

    response = api.get(run_id, "download/cleaned.csv")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVALID_STATE"
