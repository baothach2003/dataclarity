"""The single entry point for AI calls (docs/AI_PIPELINE.md section 3).

Infrastructure only, no business rules: render a prompt template, call the
API, parse and validate the JSON answer, retry once on an invalid answer, and
raise AIUnavailable otherwise. Stage-specific checks come in through the
`validate` callback so that they, too, get the one retry.

The API key and model id are passed in by the caller: shared/ may not import
the backend's settings (SPECS SEC-4, tests/test_architecture.py).
"""

import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

import anthropic
from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

DEFAULT_PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
TIMEOUT_SECONDS = 30.0  # AI_PIPELINE section 3

AIFailureReason = Literal[
    "timeout", "network", "auth", "rate_limited", "api_error",
    "invalid_response", "truncated", "refused",
]

_PLACEHOLDER = re.compile(r"\{([a-z_][a-z0-9_]*)\}")
# A fenced block anywhere in the answer, so a sentence around it does not cost
# the run its only retry. Greedy: it ends at the LAST fence, because a value
# from the uploaded file may itself contain backticks.
# Both readings are tried: the first fenced block (a model may append the
# schema "for reference"), and the widest one (a value may contain backticks).
_FENCED_FIRST = re.compile(r"```[A-Za-z]*[ \t]*\r?\n?(.*?)\r?\n?```", re.DOTALL)
_FENCED_WIDEST = re.compile(r"```[A-Za-z]*[ \t]*\r?\n?(.*)\r?\n?```", re.DOTALL)
_MAX_ERROR_CHARS = 4000
_STOP_FAILURES: dict[str, AIFailureReason] = {"max_tokens": "truncated", "refusal": "refused"}


class AIUnavailable(Exception):
    """The AI step produced no accepted answer; callers take the degraded path.

    `reason` is a fixed code for logs and API responses. The raw error text is
    deliberately not kept: it can echo request content.
    """

    def __init__(self, reason: AIFailureReason) -> None:
        super().__init__(f"AI unavailable ({reason})")
        self.reason: AIFailureReason = reason


@dataclass
class RetryBudget:
    """The run's shared retry budget (AI_PIPELINE section 2: 1 per run). The
    caller owns it because it spans every AI step of a run."""

    remaining: int = 1

    def take(self) -> bool:
        if self.remaining <= 0:
            return False
        self.remaining -= 1
        return True


@dataclass(frozen=True)
class StructuredResponse[T: BaseModel]:
    value: T
    model: str  # the model that actually answered, for `model_used`


class MessagesAPI(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class _InvalidAnswer(Exception):
    """An answer that can be retried: bad JSON, schema or stage check."""


class AIClient:
    def __init__(
        self,
        messages: MessagesAPI,
        prompts_dir: Path = DEFAULT_PROMPTS_DIR,
        timeout_seconds: float = TIMEOUT_SECONDS,
    ) -> None:
        self._messages = messages
        self._prompts_dir = prompts_dir
        self._timeout = timeout_seconds
        self.sdk_max_retries: int | None = None

    @classmethod
    def from_api_key(cls, api_key: str, prompts_dir: Path = DEFAULT_PROMPTS_DIR) -> "AIClient":
        key = api_key.strip()  # a quoted .env value or a trailing newline -> 401
        if not key:
            # The SDK would crash while building the request (a TypeError that
            # no degraded path catches), so refuse it here.
            raise ValueError("The Anthropic API key is empty.")
        # max_retries=0: the SDK would otherwise retry up to twice on its own,
        # exceeding the per-run call budget and tripling the 30 s timeout.
        # The key stays inside the SDK client: keeping a copy on an attribute
        # would undo the SecretStr care in the backend's settings.
        sdk = anthropic.Anthropic(api_key=key, max_retries=0, timeout=TIMEOUT_SECONDS)
        client = cls(sdk.messages, prompts_dir=prompts_dir)
        client.sdk_max_retries = sdk.max_retries
        return client

    def call_structured[T: BaseModel](
        self,
        prompt_name: str,
        variables: Mapping[str, str],
        response_model: type[T],
        model: str,
        max_tokens: int,
        retry_budget: RetryBudget,
        validate: Callable[[T], None] | None = None,
    ) -> StructuredResponse[T]:
        prompt = self._render(prompt_name, variables)
        attempt = 1
        while True:
            text, served_model = self._send(prompt_name, prompt, model, max_tokens, attempt)
            try:
                value = self._parse(text, response_model, validate)
            except _InvalidAnswer as invalid:
                _log(prompt_name, served_model, attempt, "invalid_response")
                if attempt > 1 or not retry_budget.take():
                    raise AIUnavailable("invalid_response") from None
                prompt = _with_rejection(prompt, str(invalid))
                attempt += 1
                continue
            _log(prompt_name, served_model, attempt, "ok")
            return StructuredResponse(value=value, model=served_model)

    def _render(self, prompt_name: str, variables: Mapping[str, str]) -> str:
        template = (self._prompts_dir / f"{prompt_name}.md").read_text(encoding="utf-8")
        wanted = set(_PLACEHOLDER.findall(template))
        if wanted != set(variables):
            raise ValueError(
                f"placeholder mismatch for {prompt_name}: template has {sorted(wanted)}, "
                f"got {sorted(variables)}"
            )
        # One pass, so a value that contains "{name}" is never substituted
        # again, and literal JSON braces in the template are left alone.
        return _PLACEHOLDER.sub(lambda m: variables[m.group(1)], template)

    def _send(
        self, prompt_name: str, prompt: str, model: str, max_tokens: int, attempt: int
    ) -> tuple[str, str]:
        started = time.perf_counter()
        try:
            response = self._messages.create(
                model=model,
                max_tokens=max_tokens,
                # AI_PIPELINE section 2: no sampling parameters (claude-sonnet-5
                # rejects temperature) and no thinking, so the 3000-token
                # budget and the 30 s timeout hold for the JSON answer itself.
                thinking={"type": "disabled"},
                messages=[{"role": "user", "content": prompt}],
                timeout=self._timeout,
            )
        except anthropic.APIError as error:
            reason = _failure_reason(error)
            _log(prompt_name, model, attempt, reason, started=started,
                 error=type(error).__name__)
            raise AIUnavailable(reason) from None
        usage = getattr(response, "usage", None)
        outcome = _STOP_FAILURES.get(response.stop_reason)
        _log(prompt_name, response.model, attempt, outcome or "received", started=started,
             input_tokens=getattr(usage, "input_tokens", None),
             output_tokens=getattr(usage, "output_tokens", None))
        if outcome is not None:
            # The same input would be cut off or refused again: no retry.
            raise AIUnavailable(outcome)
        text = "".join(block.text for block in response.content if block.type == "text")
        return text, str(response.model)

    @staticmethod
    def _parse[T: BaseModel](
        text: str, response_model: type[T], validate: Callable[[T], None] | None
    ) -> T:
        body = text.strip()
        candidates = [body]
        for pattern in (_FENCED_FIRST, _FENCED_WIDEST):
            fenced = pattern.search(body)
            if fenced and (candidate := fenced.group(1).strip()) not in candidates:
                candidates.append(candidate)
        for candidate in candidates:
            try:
                data = json.loads(candidate)
                break
            # ValueError also covers integers over 4300 digits and
            # RecursionError absurdly deep nesting: invalid answers, not crashes.
            except (ValueError, RecursionError) as error:
                failure = error
        else:
            raise _InvalidAnswer(f"The answer is not valid JSON: {failure}") from None
        try:
            # Strict: an AI answer gets no coercion help (true is not 1.0, "0.9"
            # is not a number); an int is still accepted where a float is due.
            value = response_model.model_validate(data, strict=True)
        except ValidationError as error:
            raise _InvalidAnswer(f"The JSON does not match the schema:\n{error}") from None
        if validate is not None:
            try:
                validate(value)
            except ValueError as error:
                raise _InvalidAnswer(f"The answer failed a consistency check:\n{error}") from None
        return value


def _with_rejection(prompt: str, errors: str) -> str:
    return (
        f"{prompt}\n\nYour previous response was rejected for these reasons:\n"
        f"{errors[:_MAX_ERROR_CHARS]}\n"
        "Respond again with JSON only, matching the schema exactly."
    )


def _failure_reason(error: anthropic.APIError) -> AIFailureReason:
    # Most specific first: APITimeoutError is a subclass of APIConnectionError.
    if isinstance(error, anthropic.APITimeoutError):
        return "timeout"
    if isinstance(error, anthropic.APIConnectionError):
        return "network"
    if isinstance(error, (anthropic.AuthenticationError, anthropic.PermissionDeniedError)):
        return "auth"
    if isinstance(error, anthropic.RateLimitError):
        return "rate_limited"
    return "api_error"


def _log(prompt_name: str, model: str, attempt: int, outcome: str,
         started: float | None = None, **fields: object) -> None:
    # Only metadata: never the prompt, the answer or an error message, which
    # can all contain rows from the uploaded file (AI_PIPELINE section 3).
    parts = [f"prompt={prompt_name}", f"model={model}", f"attempt={attempt}",
             f"outcome={outcome}"]
    if started is not None:
        parts.append(f"latency_ms={round((time.perf_counter() - started) * 1000)}")
    parts += [f"{key}={value}" for key, value in fields.items() if value is not None]
    logger.info("ai_call %s", " ".join(parts))
