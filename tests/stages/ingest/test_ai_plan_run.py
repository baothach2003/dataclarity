"""Stage 1, AI step B end to end, with the API mocked
(stages/ingest/ai_plan.propose_plan_run)."""

import json
from pathlib import Path

import anthropic
import httpx2
import pytest

from contracts import CleaningPlanContract
from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from shared.run_registry import create_run
from stages.ingest.ai_plan import propose_plan_run
from stages.ingest.contract_files import StaleInputError
from tests.ai_fakes import FakeMessages, FakeResponse
from tests.stages.ingest.plan_answers import (
    SCHEMA_COLUMNS,
    action,
    good_actions,
    good_plan,
    make_schema,
    plan_answer,
    planned_run,
    run_plan,
    schema_column,
    written,
)
from tests.stages.ingest.schema_answers import CSV, NOW


def replacing(name: str, **overrides: object) -> list[dict[str, object]]:
    return [{**a, **overrides} if a["source_name"] == name else a for a in good_actions()]


# --- happy path -------------------------------------------------------------


def test_writes_a_valid_contract_with_our_header_fields(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)

    returned = run_plan(tmp_path, run_id, FakeMessages(good_plan()))

    on_disk = CleaningPlanContract.model_validate_json(
        written(tmp_path, run_id).read_text(encoding="utf-8"))
    assert on_disk == returned
    # 2.0 in 2E-e (order_id widened the enum: major); 2.1 since 2E-e2 (confirmations: minor).
    assert (returned.schema_version, returned.generated_at, returned.source) == ("2.1", NOW, "ai")
    assert not any(a.edited_by_user for a in returned.column_actions)
    assert not any(a.edited_by_user for a in returned.dataset_actions)


def test_the_ais_actions_params_and_alternatives_are_carried_over(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)

    returned = run_plan(tmp_path, run_id, FakeMessages(good_plan()))

    by_name = {a.source_name: a for a in returned.column_actions}
    assert (by_name["qty"].action, by_name["qty"].params) == ("fix_negative", {"strategy": "flag"})
    assert by_name["price"].alternatives == ["impute_mean", "drop_rows_missing"]
    assert by_name["price"].rationale == "25.0% missing"
    assert [a.action for a in returned.dataset_actions] == ["remove_exact_duplicates"]


def test_the_type_and_mapping_come_from_the_schema_result_not_from_the_ai(
    tmp_path: Path,
) -> None:
    run_id = planned_run(tmp_path)
    lying = [{**a, "semantic_type": "boolean", "canonical_field": "note"}
             for a in good_actions()]

    returned = run_plan(tmp_path, run_id, FakeMessages(plan_answer(lying)))

    qty = next(a for a in returned.column_actions if a.source_name == "qty")
    assert (qty.semantic_type, qty.canonical_field) == ("numeric_discrete", "quantity")


def test_columns_follow_the_file_order_whatever_order_the_ai_used(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)

    returned = run_plan(tmp_path, run_id, FakeMessages(plan_answer(good_actions()[::-1])))

    assert [a.source_name for a in returned.column_actions] == ["sku", "name", "qty", "price"]


def test_a_name_the_ai_tidied_is_stored_under_the_files_exact_name(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)

    tidied = plan_answer(replacing("qty", source_name=" QTY "))

    returned = run_plan(tmp_path, run_id, FakeMessages(tidied))

    assert [a.source_name for a in returned.column_actions] == ["sku", "name", "qty", "price"]


def test_the_real_template_is_rendered_completely(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messages = FakeMessages(good_plan())

    run_plan(tmp_path, run_id, messages)

    prompt = messages.calls[0]["messages"][0]["content"]
    assert "{profile_json}" not in prompt and "{schema_inference_json}" not in prompt
    assert '"name": "qty"' in prompt        # the profile
    assert '"legal_actions"' in prompt      # the whitelist, given per column
    assert '"source_name": "price"' in prompt
    assert messages.calls[0]["max_tokens"] == 3000
    assert len(messages.calls) == 1


def test_the_plan_step_does_not_read_the_raw_file(tmp_path: Path) -> None:
    # Its input is the profile and the schema result (AI_PIPELINE section 2).
    run_id = planned_run(tmp_path)
    (tmp_path / run_id / "raw.csv").unlink()

    run_plan(tmp_path, run_id, FakeMessages(good_plan()))


# --- columns beyond the AI's 25 -----------------------------------------------


def test_columns_beyond_25_get_a_hand_off_action_without_the_ai(tmp_path: Path) -> None:
    names = [f"c{i}" for i in range(26)]
    raw = f"{','.join(names)}\n{','.join('1' for _ in names)}\n".encode()
    schema = make_schema([schema_column(n, "text") for n in names])
    run_id = planned_run(tmp_path, raw, schema)
    first_25 = plan_answer([action(n) for n in names[:25]], dataset_actions=[])

    returned = run_plan(tmp_path, run_id, FakeMessages(first_25))

    last = returned.column_actions[25]
    assert len(returned.column_actions) == 26
    assert (last.source_name, last.action, last.edited_by_user) == ("c25", "flag_only", False)
    assert last.canonical_field == "ignore"
    assert "first 25" in last.rationale


# --- an answer that fails a check uses the one retry ---------------------------


def test_an_illegal_action_is_retried_with_the_action_named(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messages = FakeMessages(
        plan_answer(replacing("name", action="impute_median")), good_plan())

    returned = run_plan(tmp_path, run_id, messages)

    retry_prompt = messages.calls[1]["messages"][0]["content"]
    assert "impute_median is not legal for a text column" in retry_prompt
    assert "column 'name'" in retry_prompt
    assert {a.source_name: a.action for a in returned.column_actions}["name"] == "trim_whitespace"


def test_an_action_outside_the_catalog_is_retried_with_the_action_named(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messages = FakeMessages(
        plan_answer(replacing("price", action="impute_magic")), good_plan())

    run_plan(tmp_path, run_id, messages)

    retry_prompt = messages.calls[1]["messages"][0]["content"]
    assert "impute_magic is not in the transform catalog" in retry_prompt


def test_imputing_a_required_field_is_retried_with_the_rule(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messages = FakeMessages(
        plan_answer(replacing("qty", action="impute_median")), good_plan())

    run_plan(tmp_path, run_id, messages)

    retry_prompt = messages.calls[1]["messages"][0]["content"]
    assert "quantity, a required field: use drop_rows_missing or flag_only" in retry_prompt


def test_every_problem_reaches_the_single_retry(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    bad = [a for a in replacing("name", action="impute_median") if a["source_name"] != "price"]
    messages = FakeMessages(plan_answer(bad), good_plan())

    run_plan(tmp_path, run_id, messages)

    retry_prompt = messages.calls[1]["messages"][0]["content"]
    assert "columns missing: ['price']" in retry_prompt
    assert "impute_median is not legal" in retry_prompt


def test_the_retry_spends_the_runs_budget(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    budget = RetryBudget()

    run_plan(tmp_path, run_id,
             FakeMessages(plan_answer(replacing("name", action="impute_median")), good_plan()),
             budget)

    assert budget.remaining == 0


def test_a_retry_is_not_available_when_the_schema_step_already_used_it(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messages = FakeMessages(plan_answer(replacing("name", action="impute_median")), good_plan())

    with pytest.raises(AIUnavailable) as caught:
        run_plan(tmp_path, run_id, messages, RetryBudget(remaining=0))

    assert caught.value.reason == "invalid_response"
    assert len(messages.calls) == 1


# --- degraded mode: nothing is written -------------------------------------------


def test_twice_invalid_raises_and_writes_nothing(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messages = FakeMessages(FakeResponse("sorry"), plan_answer([action("sku")]))

    with pytest.raises(AIUnavailable) as caught:
        run_plan(tmp_path, run_id, messages)

    assert caught.value.reason == "invalid_response"
    assert not written(tmp_path, run_id).exists()


def test_a_degraded_run_removes_an_earlier_proposal_but_not_the_users_final_plan(
    tmp_path: Path,
) -> None:
    run_id = planned_run(tmp_path)
    run_plan(tmp_path, run_id, FakeMessages(good_plan()))
    final = tmp_path / run_id / "plan_final.json"
    final.write_text('{"source": "user_edited"}', encoding="utf-8")

    with pytest.raises(AIUnavailable):
        run_plan(tmp_path, run_id, FakeMessages(FakeResponse("no"), FakeResponse("no")))

    assert not written(tmp_path, run_id).exists()
    assert final.read_text(encoding="utf-8") == '{"source": "user_edited"}'


def test_timeout_raises_writes_nothing_and_keeps_the_retry(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    budget = RetryBudget()
    timeout = anthropic.APITimeoutError(
        request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))

    with pytest.raises(AIUnavailable) as caught:
        run_plan(tmp_path, run_id, FakeMessages(timeout), budget)

    assert caught.value.reason == "timeout"
    assert budget.remaining == 1
    assert not written(tmp_path, run_id).exists()


def test_a_degraded_run_leaves_the_schema_result_alone(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    schema_file = tmp_path / run_id / "schema_inference.json"
    before = schema_file.read_bytes()

    with pytest.raises(AIUnavailable):
        run_plan(tmp_path, run_id, FakeMessages(FakeResponse("no"), FakeResponse("no")))

    assert schema_file.read_bytes() == before


# --- inputs ---------------------------------------------------------------------


@pytest.mark.parametrize("missing", ["profile.json", "schema_inference.json"])
def test_a_missing_input_is_a_clear_error_before_any_ai_call(tmp_path: Path, missing: str) -> None:
    run_id = planned_run(tmp_path)
    (tmp_path / run_id / missing).unlink()
    messages = FakeMessages()

    with pytest.raises(FileNotFoundError, match=missing):
        propose_plan_run(tmp_path, run_id, AIClient(messages), model="m",
                         retry_budget=RetryBudget(), now=NOW)

    assert messages.calls == []


def test_a_schema_result_for_other_columns_is_refused_before_any_ai_call(tmp_path: Path) -> None:
    # A stale schema_inference.json (the file was re-profiled since).
    stale = make_schema([schema_column("sku", "identifier", "sku"), *SCHEMA_COLUMNS[2:]])
    run_id = planned_run(tmp_path, CSV, stale)
    messages = FakeMessages()

    with pytest.raises(ValueError, match="does not match profile.json"):
        propose_plan_run(tmp_path, run_id, AIClient(messages), model="m",
                         retry_budget=RetryBudget(), now=NOW)

    assert messages.calls == []


def test_a_run_with_no_files_at_all_fails_fast(tmp_path: Path) -> None:
    run = create_run(tmp_path)

    with pytest.raises(FileNotFoundError):
        propose_plan_run(tmp_path, run.run_id, AIClient(FakeMessages()), model="m",
                         retry_budget=RetryBudget(), now=NOW)


def test_the_contract_written_is_plain_json_a_later_stage_can_read(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    run_plan(tmp_path, run_id, FakeMessages(good_plan()))

    data = json.loads(written(tmp_path, run_id).read_text(encoding="utf-8"))

    assert set(data) == {"schema_version", "generated_at", "source", "dataset_actions",
                         "column_actions", "confirmations"}  # 2E-e2: always written, None unanswered


# --- cycle-2 review ---------------------------------------------------------------


def test_a_lone_surrogate_is_a_retry_not_a_crash(tmp_path: Path) -> None:
    # Valid JSON that no HTTP layer can encode: echoing it raw made the retry
    # request raise UnicodeEncodeError instead of degrading.
    run_id = planned_run(tmp_path)
    messages = FakeMessages(plan_answer(replacing("name", action="\ud800x")), good_plan())

    returned = run_plan(tmp_path, run_id, messages)

    messages.calls[1]["messages"][0]["content"].encode("utf-8")  # must not raise
    assert {a.source_name: a.action for a in returned.column_actions}["name"] == "trim_whitespace"


def test_a_column_with_no_params_or_alternatives_needs_no_retry(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    slim = [{"source_name": a["source_name"], "action": a["action"], "rationale": a["rationale"],
             **({"params": a["params"]} if a["params"] else {})} for a in good_actions()]
    messages = FakeMessages(plan_answer(slim))

    returned = run_plan(tmp_path, run_id, messages)

    assert len(messages.calls) == 1
    assert next(a for a in returned.column_actions if a.source_name == "sku").alternatives == []


def test_repeated_and_restated_alternatives_are_tidied_in_the_written_plan(tmp_path: Path) -> None:
    run_id = planned_run(tmp_path)
    messy = replacing("price", alternatives=["impute_mean", "impute_mean", "impute_median",
                                            "drop_rows_missing"])

    returned = run_plan(tmp_path, run_id, FakeMessages(plan_answer(messy)))

    price = next(a for a in returned.column_actions if a.source_name == "price")
    assert price.alternatives == ["impute_mean", "drop_rows_missing"]


def test_a_stale_schema_is_the_named_stale_input_error(tmp_path: Path) -> None:
    # The backend answers 409 for this and must not confuse it with the other
    # ValueErrors (a pydantic ValidationError is one too).
    stale = make_schema([schema_column("sku", "identifier", "sku"), *SCHEMA_COLUMNS[2:]])
    run_id = planned_run(tmp_path, CSV, stale)

    with pytest.raises(StaleInputError):
        propose_plan_run(tmp_path, run_id, AIClient(FakeMessages()), model="m",
                         retry_budget=RetryBudget(), now=NOW)
