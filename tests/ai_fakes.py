"""A fake Anthropic messages API for tests: no HTTP at all."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUsage:
    input_tokens: int = 120
    output_tokens: int = 30


@dataclass
class FakeBlock:
    text: str
    type: str = "text"


@dataclass
class FakeResponse:
    text: str
    stop_reason: str = "end_turn"
    model: str = "served-model"
    usage: FakeUsage = field(default_factory=FakeUsage)

    @property
    def content(self) -> list[FakeBlock]:
        return [FakeBlock(self.text)]


class FakeMessages:
    def __init__(self, *outcomes: FakeResponse | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> FakeResponse:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


