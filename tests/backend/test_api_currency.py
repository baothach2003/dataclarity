"""The report redesign's step 2 through HTTP (Thach, Q7 = A): a file with
amounts in more than one currency (on the plan's money column, Q26) is
refused at execute - 422 INVALID_PLAN,
the sentence as written and `reason` "currency" for Review (step 5) - and the
run is released, nothing written. One currency runs and is recorded."""

from typing import Any

from app.models import RunStatus
from tests.backend.api_support import PLAN_FILES, MakeApi, plan_reply, planned, schema_reply

# The API fixture's own rows (the fake AI's issue counts read them), its prices in pounds and one in euros.
MIXED = "\n".join(["sku,name,qty,price,day",
                   "A1, Mug ,3,£9.99,2024-01-05",
                   "B2,Cup,-1,,15/01/2024",
                   "A1, Mug ,3,£9.99,2024-01-05",
                   "C3,,5,€12.50,2024-01-07",
                   "D4,Plate,4,£7.00,not a date", ""]).encode()


def _planned(make_api: MakeApi, content: bytes) -> tuple[Any, str, dict[str, Any]]:
    api = make_api(schema_reply(), plan_reply())
    run_id = api.upload(content)
    assert api.post(run_id, "analyze-schema").status_code == 200
    response = api.post(run_id, "plan")
    assert response.status_code == 200, response.text
    return api, run_id, response.json()["plan"]


def test_a_mixed_file_is_refused_at_execute_and_released(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, MIXED)

    refused = api.post(run_id, "execute", plan)

    assert refused.status_code == 422
    error = refused.json()["error"]
    assert (error["code"], error["details"]["reason"]) == ("INVALID_PLAN", "currency")
    assert error["details"]["problems"] == [
        "Your file has amounts in more than one currency (GBP: 3 lines, EUR: 1 line). DataClarity cannot add "
        "different currencies together. Split the file by currency and upload each part."]
    assert api.status(run_id) is RunStatus.PLANNED
    assert not PLAN_FILES & api.files(run_id)


def test_the_profile_carries_no_currency(make_api: MakeApi) -> None:
    # Thach, Q26: read at execute, on the plan's money column - the profile is written before any mapping.
    api, run_id, _ = _planned(make_api, MIXED)

    profile = api.read_json(run_id, "profile.json")

    assert "currency" not in profile and profile["schema_version"] == "1.2"


def test_one_currency_runs_and_is_recorded(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id, plan = planned(api)

    response = api.post(run_id, "execute", {**plan, "confirmations": {"currency": "GBP"}})

    assert response.status_code == 200, response.text
    assert api.read_json(run_id, "cleaning_report.json")["currency"] == {
        "code": "GBP", "source": "user", "evidence": None}
