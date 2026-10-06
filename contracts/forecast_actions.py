"""forecast.json's structured actions (docs/CONTRACTS.md section 8; the
report redesign, D4 and section 4; Thach, 2026-10-05): code selects at most
three claims and writes each one's fact and what to watch; the AI writes only
the action and why - no number, no choice of claims. Split out of
contracts/forecast.py for file size.

`actions_status` says which of three states a report shows (Thach):
- "list": the claims code selected, each with the AI's two sentences - or
  none selected (headline rules 1-4 and 7, a blocked run, an incomplete
  previous month: no claim, the AI not asked, `actions` empty);
- "off": claims were selected but the AI step is switched off
  (STRATEGY_AI_ENABLED false);
- "suppressed": the AI's answer failed the checks twice, or the call failed
  - the whole list is withheld, never a part of it.
"""

import re
import unicodedata
from typing import Literal

from pydantic import Field, field_validator

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
    fact: str = Field(min_length=1)  # code: the figure it rests on, the checklist's own sentence
    action: str  # the AI
    why: str  # the AI
    watch: str = Field(min_length=1)  # code: what to check next month

    @field_validator("action", "why")
    @classmethod
    def _no_number_from_the_ai(cls, value: str) -> str:
        problems = ai_text_problems(value)
        if problems:
            raise ValueError(f"the AI's sentence is refused: {'; '.join(problems)}")
        return value


def check_actions(actions: list[SuggestedAction] | None, status: ActionsStatus | None, model: str | None,
                  version: tuple[int, int]) -> None:
    """The three states as forecast.json holds them (2.1). Raises ValueError."""
    if version < (2, 1):
        if actions is not None or status is not None or model is not None:
            raise ValueError("actions exist from forecast.json 2.1")
        return
    if status is None:
        raise ValueError("a 2.1 forecast says its actions' state (actions_status)")
    if (status == "list") != (actions is not None):
        raise ValueError("actions are listed exactly when actions_status is 'list' - an empty list when no claim "
                         "is selected; null when switched off or suppressed")
    if actions is None:
        if model is not None:
            raise ValueError("no action is listed, so no model wrote one")
        return
    if len(actions) > MAX_ACTIONS:
        raise ValueError(f"at most {MAX_ACTIONS} actions")
    if [a.claim for a in actions] != list(CLAIM_IDS[:len(actions)]):
        raise ValueError("the claims are K1, K2, K3 in their rank order, each once")
    if len({a.hypothesis_id for a in actions}) != len(actions):
        raise ValueError("each claim rests on a different hypothesis")
    if bool(actions) != (model is not None):
        raise ValueError("listed actions name the model that wrote them (actions_model), and only then")
