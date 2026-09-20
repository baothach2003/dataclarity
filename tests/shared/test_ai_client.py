import logging
from pathlib import Path
from typing import Any

import anthropic
import httpx2
import pytest
from pydantic import BaseModel, Field

from shared.ai_client import AIClient, AIUnavailable, RetryBudget
from tests.ai_fakes import FakeMessages, FakeResponse

SECRET_SAMPLE = "SAMPLE-ROW-7f3a"  # stands in for customer data; must never reach logs


class Answer(BaseModel):
    value: int = Field(ge=0)


REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def status_error(cls: type[anthropic.APIStatusError], code: int) -> anthropic.APIStatusError:
    return cls("error", response=httpx2.Response(code, request=REQUEST), body=None)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    # Literal JSON braces next to real placeholders, like the real templates.
    (tmp_path / "answer.md").write_text(
        'Row: {sample}\nReply as {"value": <int>} for {question}.\n', encoding="utf-8"
    )
    return tmp_path


def call(messages: FakeMessages, prompts_dir: Path, budget: RetryBudget | None = None,
         **kwargs: Any) -> Any:
    client = AIClient(messages, prompts_dir=prompts_dir)
    return client.call_structured(
        "answer",
        {"sample": SECRET_SAMPLE, "question": "the count"},
        Answer,
        model="test-model",
        max_tokens=3000,
        retry_budget=budget or RetryBudget(),
        **kwargs,
    )


# --- prompt rendering ------------------------------------------------------------


def test_placeholders_are_replaced_and_literal_braces_kept(prompts_dir: Path) -> None:
    messages = FakeMessages(FakeResponse('{"value": 3}'))

    call(messages, prompts_dir)

    prompt = messages.calls[0]["messages"][0]["content"]
    assert prompt == f'Row: {SECRET_SAMPLE}\nReply as {{"value": <int>}} for the count.\n'


def test_a_value_that_looks_like_a_placeholder_is_not_substituted_again(
    prompts_dir: Path,
) -> None:
    messages = FakeMessages(FakeResponse('{"value": 3}'))
    client = AIClient(messages, prompts_dir=prompts_dir)

    client.call_structured("answer", {"sample": "{question}", "question": "q"}, Answer,
                           model="m", max_tokens=10, retry_budget=RetryBudget())

    assert messages.calls[0]["messages"][0]["content"].startswith("Row: {question}\n")


@pytest.mark.parametrize(
    "variables", [{"sample": "x"}, {"sample": "x", "question": "q", "extra": "y"}]
)
def test_missing_or_unknown_variables_are_a_programming_error(
    prompts_dir: Path, variables: dict[str, str]
) -> None:
    client = AIClient(FakeMessages(), prompts_dir=prompts_dir)

    with pytest.raises(ValueError, match="placeholder"):
        client.call_structured("answer", variables, Answer, model="m", max_tokens=10,
                               retry_budget=RetryBudget())


# --- the request -----------------------------------------------------------------


def test_request_follows_the_call_policy(prompts_dir: Path) -> None:
    messages = FakeMessages(FakeResponse('{"value": 3}'))

    call(messages, prompts_dir)

    sent = messages.calls[0]
    assert sent["model"] == "test-model"
    assert sent["max_tokens"] == 3000
    assert sent["thinking"] == {"type": "disabled"}
    assert sent["timeout"] == 30.0
    assert "temperature" not in sent  # rejected by claude-sonnet-5 (400)


def test_valid_response_is_parsed_and_the_served_model_reported(prompts_dir: Path) -> None:
    result = call(FakeMessages(FakeResponse('{"value": 3}', model="claude-x")), prompts_dir)

    assert result.value == Answer(value=3)
    assert result.model == "claude-x"


def test_markdown_fences_are_stripped(prompts_dir: Path) -> None:
    result = call(FakeMessages(FakeResponse('```json\n{"value": 4}\n```')), prompts_dir)

    assert result.value.value == 4


def test_real_client_is_built_without_sdk_retries() -> None:
    client = AIClient.from_api_key("test-key-not-real")

    # Retries are ours, counted against the run's budget (AI_PIPELINE 2).
    assert client.sdk_max_retries == 0


# --- retry once, then degrade ------------------------------------------------------


def test_invalid_json_then_valid_retries_once_with_the_errors(prompts_dir: Path) -> None:
    budget = RetryBudget()
    messages = FakeMessages(FakeResponse("not json"), FakeResponse('{"value": 5}'))

    result = call(messages, prompts_dir, budget)

    assert result.value.value == 5
    assert len(messages.calls) == 2
    retry_prompt = messages.calls[1]["messages"][0]["content"]
    assert retry_prompt.startswith(messages.calls[0]["messages"][0]["content"])
    assert "was rejected" in retry_prompt and "not valid JSON" in retry_prompt
    assert budget.remaining == 0


def test_schema_violation_then_valid_retries_once(prompts_dir: Path) -> None:
    messages = FakeMessages(FakeResponse('{"value": -1}'), FakeResponse('{"value": 1}'))

    result = call(messages, prompts_dir)

    assert result.value.value == 1
    assert "greater than or equal to 0" in messages.calls[1]["messages"][0]["content"]


def test_stage_validation_failure_also_uses_the_retry(prompts_dir: Path) -> None:
    def odd_only(answer: Answer) -> None:
        if answer.value % 2 == 0:
            raise ValueError("value must be odd")

    messages = FakeMessages(FakeResponse('{"value": 2}'), FakeResponse('{"value": 3}'))

    result = call(messages, prompts_dir, validate=odd_only)

    assert result.value.value == 3
    assert "value must be odd" in messages.calls[1]["messages"][0]["content"]


def test_twice_invalid_raises_ai_unavailable(prompts_dir: Path) -> None:
    messages = FakeMessages(FakeResponse("nope"), FakeResponse('{"value": "x"}'))

    with pytest.raises(AIUnavailable) as caught:
        call(messages, prompts_dir)

    assert caught.value.reason == "invalid_response"
    assert len(messages.calls) == 2


def test_no_retry_when_the_run_budget_is_already_spent(prompts_dir: Path) -> None:
    messages = FakeMessages(FakeResponse("nope"))

    with pytest.raises(AIUnavailable) as caught:
        call(messages, prompts_dir, RetryBudget(remaining=0))

    assert caught.value.reason == "invalid_response"
    assert len(messages.calls) == 1


# --- failures that are not retried -------------------------------------------------


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (anthropic.APITimeoutError(request=REQUEST), "timeout"),
        (anthropic.APIConnectionError(request=REQUEST), "network"),
        (status_error(anthropic.AuthenticationError, 401), "auth"),
        (status_error(anthropic.PermissionDeniedError, 403), "auth"),
        (status_error(anthropic.RateLimitError, 429), "rate_limited"),
        (status_error(anthropic.InternalServerError, 500), "api_error"),
        (status_error(anthropic.BadRequestError, 400), "api_error"),
    ],
)
def test_api_failures_degrade_without_spending_the_retry(
    prompts_dir: Path, error: Exception, reason: str
) -> None:
    budget = RetryBudget()
    messages = FakeMessages(error)

    with pytest.raises(AIUnavailable) as caught:
        call(messages, prompts_dir, budget)

    assert caught.value.reason == reason
    assert len(messages.calls) == 1
    assert budget.remaining == 1  # AI_PIPELINE 9.3: the run can try again later


@pytest.mark.parametrize(("stop_reason", "reason"), [("max_tokens", "truncated"),
                                                     ("refusal", "refused")])
def test_truncated_or_refused_responses_are_not_retried(
    prompts_dir: Path, stop_reason: str, reason: str
) -> None:
    budget = RetryBudget()
    messages = FakeMessages(FakeResponse('{"value":', stop_reason=stop_reason))

    with pytest.raises(AIUnavailable) as caught:
        call(messages, prompts_dir, budget)

    # The same input would be cut off or refused again: retrying wastes budget.
    assert caught.value.reason == reason
    assert len(messages.calls) == 1
    assert budget.remaining == 1


# --- logging ------------------------------------------------------------------------


def test_logs_model_tokens_and_outcome_but_never_the_data(
    prompts_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="shared.ai_client")
    messages = FakeMessages(
        FakeResponse(f"{SECRET_SAMPLE} is not json"),
        FakeResponse('{"value": 3}', model="claude-x"),
    )

    call(messages, prompts_dir)

    text = caplog.text
    assert "prompt=answer" in text and "model=claude-x" in text
    assert "input_tokens=120" in text and "output_tokens=30" in text
    assert "outcome=invalid_response" in text and "outcome=ok" in text
    assert SECRET_SAMPLE not in text


def test_failure_logs_the_reason_but_not_the_error_message(
    prompts_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="shared.ai_client")
    error = anthropic.APIConnectionError(message=f"failed near {SECRET_SAMPLE}", request=REQUEST)

    with pytest.raises(AIUnavailable):
        call(FakeMessages(error), prompts_dir)

    assert "outcome=network" in caplog.text and "APIConnectionError" in caplog.text
    assert SECRET_SAMPLE not in caplog.text
