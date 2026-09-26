"""Session 2E-e2 (Thach), through the API: the answers the Review screen
puts in the plan are executed with it and recorded in cleaning_report.json,
and a plan with no answers records none (unconfirmed means untrusted)."""

from tests.backend.api_support import MakeApi, make_api_with_plan


def test_the_answers_in_the_plan_reach_the_cleaning_report(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    answers = {"order_id_is_receipt": True, "customer_on_first_line_only": False,
               "customer_placeholders": [], "line_classes": []}  # 2E-k, 2E-d2

    response = api.post(run_id, "execute", {**plan, "confirmations": answers})

    assert response.status_code == 200, response.text
    assert response.json()["report"]["confirmations"] == answers
    assert api.read_json(run_id, "cleaning_report.json")["confirmations"] == answers


def test_a_plan_without_answers_records_none(make_api: MakeApi) -> None:
    api, run_id, plan = make_api_with_plan(make_api)
    plan.pop("confirmations", None)

    response = api.post(run_id, "execute", plan)

    assert response.status_code == 200, response.text
    assert api.read_json(run_id, "cleaning_report.json")["confirmations"] == {
        "order_id_is_receipt": None, "customer_on_first_line_only": None,
        "customer_placeholders": [], "line_classes": []}  # 2E-k, 2E-d2


def test_a_plan_changed_only_by_the_users_answers_is_the_users(make_api: MakeApi) -> None:
    """2E-e2 doubt-review cycle 2 F10: plan_final.json's `source` says who
    decided, and an answer is always the user's."""
    api, run_id, plan = make_api_with_plan(make_api)

    api.post(run_id, "execute", {**plan, "confirmations": {"order_id_is_receipt": False,
                                                           "customer_on_first_line_only": None}})

    assert api.read_json(run_id, "plan_final.json")["source"] == "user_edited"
