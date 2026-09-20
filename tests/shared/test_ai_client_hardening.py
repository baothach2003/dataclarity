"""Fixes from the 1C doubt review: parser limits, strict types, fences, empty key."""

from pathlib import Path
from typing import Any

import anthropic
import pytest
from pydantic import BaseModel, Field

from shared.ai_client import AIClient, RetryBudget
from tests.ai_fakes import FakeMessages, FakeResponse


class Answer(BaseModel):
    value: int = Field(ge=0)


@pytest.fixture
def prompts_dir(tmp_path: Path) -> Path:
    (tmp_path / "answer.md").write_text(
        'Reply as {"value": <int>} for {question}.\n', encoding="utf-8"
    )
    return tmp_path


def call(messages: FakeMessages, prompts_dir: Path) -> Any:
    return AIClient(messages, prompts_dir=prompts_dir).call_structured(
        "answer", {"question": "the count"}, Answer, model="m", max_tokens=3000,
        retry_budget=RetryBudget())


# --- doubt review fixes (1C) ---------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    ['{"value": 1' + "1" * 5000 + "}", "[" * 100_000],
    ids=["integer-over-4300-digits", "nesting-too-deep"],
)
def test_json_the_parser_refuses_is_an_invalid_answer_not_a_crash(
    prompts_dir: Path, bad: str
) -> None:
    messages = FakeMessages(FakeResponse(bad), FakeResponse('{"value": 1}'))

    result = call(messages, prompts_dir)

    assert result.value.value == 1
    assert "not valid JSON" in messages.calls[1]["messages"][0]["content"]


@pytest.mark.parametrize("value", ["true", '"3"', "3.5"], ids=["bool", "string", "fraction"])
def test_answers_are_validated_strictly(prompts_dir: Path, value: str) -> None:
    # Lax mode would turn true into 1 and "3" into 3; an AI answer gets no such help.
    messages = FakeMessages(FakeResponse(f'{{"value": {value}}}'), FakeResponse('{"value": 2}'))

    result = call(messages, prompts_dir)

    assert result.value.value == 2
    assert len(messages.calls) == 2


def test_a_fenced_block_with_text_around_it_is_still_found(prompts_dir: Path) -> None:
    text = 'Here is the JSON:\n```json\n{"value": 4}\n```\nLet me know.'

    result = call(FakeMessages(FakeResponse(text)), prompts_dir)

    assert result.value.value == 4


@pytest.mark.parametrize("key", ["", "   "])
def test_an_empty_api_key_is_refused_before_any_call(key: str) -> None:
    with pytest.raises(ValueError, match="API key"):
        AIClient.from_api_key(key)


def test_a_fence_around_json_that_itself_contains_backticks(prompts_dir: Path) -> None:
    # A value from the file may contain ```; the fence ends at the last one.
    text = '```json\n{"value": 7, "note": "a```b"}\n```'

    result = call(FakeMessages(FakeResponse(text)), prompts_dir)

    assert result.value.value == 7


def test_a_fence_with_windows_line_endings(prompts_dir: Path) -> None:
    result = call(FakeMessages(FakeResponse('```json\r\n{"value": 8}\r\n```')), prompts_dir)

    assert result.value.value == 8


def test_a_key_with_stray_whitespace_is_used_trimmed(monkeypatch: pytest.MonkeyPatch) -> None:
    # A quoted .env value or a trailing newline would otherwise cause a 401
    # that gets logged as "auth" instead of being fixed here.
    captured: dict[str, Any] = {}
    real_client = anthropic.Anthropic

    def capture(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return real_client(**{**kwargs, "api_key": "test-key-not-real"})

    monkeypatch.setattr(anthropic, "Anthropic", capture)

    AIClient.from_api_key("  test-key-not-real\n")

    assert captured["api_key"] == "test-key-not-real"


def test_two_fenced_blocks_use_the_first_one(prompts_dir: Path) -> None:
    # A model may append the schema "for reference" after its answer.
    text = '```json\n{"value": 5}\n```\nFor reference:\n```json\n{"value": "<int>"}\n```'

    result = call(FakeMessages(FakeResponse(text)), prompts_dir)

    assert result.value.value == 5


def test_a_single_line_fence(prompts_dir: Path) -> None:
    result = call(FakeMessages(FakeResponse('```{"value": 6}```')), prompts_dir)

    assert result.value.value == 6
