"""forecast.json's suggested actions (docs/CONTRACTS.md section 8; the
report redesign, D4 and section 4): code selects at most three claims and
writes every sentence - each one's fact, action, why and what to watch
(Thach's option (d), 2026-10-06: no AI writes a recommendation in v1). Split
out of contracts/forecast.py for file size.

`actions_status` says which of three states a report shows (Thach):
- "list": the claims code selected, each with its catalog sentences - or
  none (headline rules 1-4 and 7, a blocked run, an incomplete previous
  month: no claim, `actions` empty);
- "suppressed": checks a claim may rest on exist, but none has an action for
  the way its figure moved - nothing to act on;
- "off": only for a run where stage 4 did not produce actions (stage 4
  writes it no more).
`actions_model` is null: code writes the actions (Q53).
"""

import re
import unicodedata
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from contracts._base import ContractModel
from contracts.report_front import FRONT_BANNED

ActionsStatus = Literal["off", "suppressed", "list"]
# At most three claims (Thach, Q11), named K1, K2, K3 in their rank order.
MAX_ACTIONS = 3
CLAIM_IDS = ("K1", "K2", "K3")
# One sentence each, at most this many words (design 4.4, check 5).
MAX_WORDS = 30


def ai_text_problems(text: str) -> list[str]:
    """What an AI sentence may never hold, held by the contract whoever wrote
    the file (design 4.4, checks 2 and 5): a digit in any script, a percent
    sign, a currency sign, more than MAX_WORDS words, nothing at all. Stage
    4's own checks are fuller (number words, certainty words, names)."""
    found = []
    if not text.strip():
        found.append("it is empty")
    if any(char.isdigit() for char in text):
        found.append("it holds a digit")
    if "%" in text or any(unicodedata.category(char) == "Sc" for char in text):
        found.append("it holds a percent or currency sign")
    if len(text.split()) > MAX_WORDS:
        found.append(f"it is over {MAX_WORDS} words")
    return found


# What a named product stands for inside the action while the rest of it is
# held to no number (Thach, Q65).
_NAMED = '"the product"'


def named_action_problems(action: str, name: str | None) -> list[str]:
    """Thach, Q65: an action may quote ONE product name copied verbatim from
    stage 3's field (diagnosis.json hypotheses[].member), and that name may
    hold digits - it is data, not an invented number. Everything else is
    held as ever: the rest of the sentence to no digit and no sign, the name
    to no sign (digits only were allowed), quoted once, no quote mark in it."""
    if name is None:
        return ai_text_problems(action)
    if not name.strip() or '"' in name:
        return ["the named product is no name"]
    quoted = f'"{name}"'
    if action.count(quoted) != 1:
        return ["the named product stands once, in quotes, in the action"]
    in_name = [problem for problem in ai_text_problems(name) if problem != "it holds a digit"]
    return [f"the named product: {problem}" for problem in in_name] + ai_text_problems(action.replace(quoted, _NAMED))


def front_word_problems(text: str) -> list[str]:
    """The front section's banned words in an AI sentence. Stage 4's checks
    refuse and retry on them (Thach, Q43); the contract does not, so a file
    holding one still loads and the report is still built."""
    lowered = f" {text.lower()} "
    banned = [w for w in FRONT_BANNED if re.search(rf"(?<![a-z]){re.escape(w)}(?:s|es)?(?![a-z])", lowered)]
    return [f"it uses {', '.join(banned)}"] if banned else []


class SuggestedAction(ContractModel):
    """One claim and what to do about it."""

    claim: Literal["K1", "K2", "K3"]
    hypothesis_id: str = Field(min_length=1)  # the hypothesis the claim rests on (diagnosis.json)
    fact: str = Field(min_length=1)  # the figure it rests on, the checklist's own sentence
    action: str  # the catalog's, by kind and direction (stages/predict/catalog.py)
    why: str  # the catalog's
    watch: str = Field(min_length=1)  # what to check next month
    # 2.2 (Thach, Q65): the product name R1's action quotes, copied verbatim
    # from diagnosis.json hypotheses[].member - its digits are data. Null for
    # every other action, and when R1's action points to its row instead.
    name: str | None = None

    @field_validator("why")
    @classmethod
    def _no_number_from_the_ai(cls, value: str) -> str:
        problems = ai_text_problems(value)
        if problems:
            raise ValueError(f"the AI's sentence is refused: {'; '.join(problems)}")
        return value

    @model_validator(mode="after")
    def _no_number_but_the_named_product(self) -> Self:
        if self.name is not None and self.hypothesis_id != "R1":
            raise ValueError("only R1's action names a product (actions[].name)")
        problems = named_action_problems(self.action, self.name)
        if problems:
            raise ValueError(f"the action is refused: {'; '.join(problems)}")
        return self


def check_actions(actions: list[SuggestedAction] | None, status: ActionsStatus | None, model: str | None,
                  version: tuple[int, int]) -> None:
    """The three states as forecast.json holds them (2.1). Raises ValueError."""
    if version < (2, 1):
        if actions is not None or status is not None or model is not None:
            raise ValueError("actions exist from forecast.json 2.1")
        return
    if status is None:
        raise ValueError("a 2.1 forecast says its actions' state (actions_status)")
    if model is not None:
        # Thach, Q50 (d), Q53: no AI writes an action in v1.
        raise ValueError("code writes the actions: actions_model is null")
    if (status == "list") != (actions is not None):
        raise ValueError("actions are listed exactly when actions_status is 'list' - an empty list when no claim "
                         "is selected; null when off or suppressed")
    if actions is None:
        return
    if len(actions) > MAX_ACTIONS:
        raise ValueError(f"at most {MAX_ACTIONS} actions")
    if [a.claim for a in actions] != list(CLAIM_IDS[:len(actions)]):
        raise ValueError("the claims are K1, K2, K3 in their rank order, each once")
    if len({a.hypothesis_id for a in actions}) != len(actions):
        raise ValueError("each claim rests on a different hypothesis")
    if version < (2, 2) and any(a.name is not None for a in actions):
        raise ValueError("actions[].name exists from forecast.json 2.2")
