"""The dashboard's step 4 through HTTP: POST /api/runs/{id}/breakdowns - Review's
sales breakdowns (Thach's D4). The AI is FAKED; it is asked once per run, the
answer reused; execute records what the user kept."""

import threading
import time
from typing import Any

from app.models import RunStatus
from tests.ai_fakes import FakeResponse
from tests.backend.api_support import SCHEMA_COLUMNS, MakeApi, on_ai_call, plan_reply, schema_reply
from tests.stages.ingest.cleaning_fixtures import RAW_CSV
from tests.stages.ingest.plan_answers import action, dataset_action, plan_answer
from tests.stages.ingest.schema_answers import answer, column

# The API fixture's own rows (the fake schema answer's issue counts read them), with a store column.
STORES = ["North", "South", "North", "East", "South"]
CSV = "\n".join([f"{line},{store}" for line, store in zip(RAW_CSV.decode().splitlines()[1:], STORES)]).encode()
CSV = b"sku,name,qty,price,day,store\n" + CSV + b"\n"


def _schema() -> FakeResponse:
    return answer([*SCHEMA_COLUMNS, column("store", semantic_type="categorical_nominal")], domain_confidence=0.93)


def _plan() -> FakeResponse:
    return plan_answer([action("sku", "trim_whitespace"), action("name", "trim_whitespace"),
                        action("qty", "fix_negative", params={"strategy": "flag"}), action("price", "impute_median"),
                        action("day", "parse_datetime"), action("store", "trim_whitespace")],
                       [dataset_action("remove_exact_duplicates")])


def _planned(make_api: MakeApi, *replies: FakeResponse) -> tuple[Any, str, dict[str, Any]]:
    api = make_api(_schema(), _plan(), *replies)
    run_id = api.upload(CSV)
    schema = api.post(run_id, "analyze-schema")
    assert schema.status_code == 200 and schema.json()["schema_inference"] is not None, schema.text
    response = api.post(run_id, "plan")
    assert response.status_code == 200, response.text
    return api, run_id, response.json()["plan"]


def test_review_gets_the_eligible_columns_and_the_ais_choice(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))

    response = api.post(run_id, "breakdowns", plan)

    assert response.status_code == 200, response.text
    question = response.json()["question"]
    assert [c["column"] for c in question["eligible"]] == ["store"]
    assert sorted(question["eligible"][0]["values"]) == ["East", "North", "South"]
    assert (question["suggested"], question["status"]) == (["store"], "chosen")
    assert api.ai_requests == 3  # schema, plan, the breakdowns - once


def test_the_ai_is_asked_once_per_run(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))
    first = api.post(run_id, "breakdowns", plan).json()
    second = api.post(run_id, "breakdowns", plan).json()
    assert first == second and api.ai_requests == 3
    assert api.read_json(run_id, "breakdown_suggestion.json")["chosen"] == ["store"]


def test_a_failed_answer_is_stored_and_never_asked_again(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse("not json"), FakeResponse('{"breakdowns": ["store"]}'))
    first = api.post(run_id, "breakdowns", plan).json()["question"]
    second = api.post(run_id, "breakdowns", plan).json()["question"]
    assert (first["status"], first["suggested"]) == ("ai_unavailable", [])
    assert second == first and api.ai_requests == 3  # the queued good answer is never asked for


def test_a_column_mapped_since_is_no_longer_offered_or_suggested(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))
    api.post(run_id, "breakdowns", plan)
    remapped = {**plan, "column_actions": [{**a, "canonical_field": "category"} if a["source_name"] == "store"
                                           else a for a in plan["column_actions"]]}
    question = api.post(run_id, "breakdowns", remapped).json()["question"]
    assert (question["eligible"], question["suggested"], question["status"]) == ([], [], "none_eligible")


def test_a_file_with_nothing_eligible_asks_no_ai(make_api: MakeApi) -> None:
    api = make_api(schema_reply(), plan_reply())
    run_id = api.upload()
    api.post(run_id, "analyze-schema")
    plan = api.post(run_id, "plan").json()["plan"]
    question = api.post(run_id, "breakdowns", plan).json()["question"]
    assert (question["eligible"], question["status"]) == ([], "none_eligible")
    assert api.ai_requests == 2


def test_outside_review_it_is_refused(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))
    api.set_status(run_id, RunStatus.CLEANED)
    assert api.post(run_id, "breakdowns", plan).status_code == 409


def test_execute_records_the_columns_the_user_kept(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))
    response = api.post(run_id, "execute", {**plan, "breakdowns": ["store"]})
    assert response.status_code == 200, response.text
    assert api.read_json(run_id, "cleaning_report.json")["breakdowns"] == ["store"]


def test_execute_refuses_a_column_that_cannot_split_sales(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api)
    refused = api.post(run_id, "execute", {**plan, "breakdowns": ["price"]})
    assert refused.status_code == 422
    assert refused.json()["error"]["details"]["problems"] == [
        'column "price" cannot split sales: the plan already uses it as a field']
    assert api.status(run_id) is RunStatus.PLANNED


# --- the step 4 review: the ask is never in the user's path, and never twice (#2, #5) ------------------------------


def test_confirm_while_the_ai_answers_is_not_refused(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))
    seen: dict[str, int] = {}

    def confirm_now() -> None:
        seen["execute"] = api.post(run_id, "execute", plan).status_code

    on_ai_call(api, confirm_now)
    response = api.post(run_id, "breakdowns", plan)
    assert seen == {"execute": 200} and response.status_code in (200, 409)


def test_a_second_ask_while_the_ai_answers_waits_for_that_answer(make_api: MakeApi) -> None:
    api, run_id, plan = _planned(make_api, FakeResponse('{"breakdowns": ["store"]}'))
    # Another tab's ask about other columns (a type changed), on its own thread as a real request is.
    edited = {**plan, "column_actions": [{**a, "semantic_type": "text"} if a["source_name"] == "store" else a
                                         for a in plan["column_actions"]]}
    seen: dict[str, Any] = {}
    second = threading.Thread(target=lambda: seen.update(second=api.post(run_id, "breakdowns", edited)))

    def ask_again() -> None:
        second.start()
        time.sleep(0.2)  # the second ask is waiting before the AI answers the first

    on_ai_call(api, ask_again)
    first = api.post(run_id, "breakdowns", plan)
    second.join(timeout=10)
    assert first.status_code == 200 and seen["second"].status_code == 200
    assert seen["second"].json()["question"]["suggested"] == ["store"]
    assert api.ai_requests == 3  # schema, plan, the breakdowns - once
