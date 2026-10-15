"""The dashboard's sales breakdowns, stage 1's part (Thach's D4, 2026-10-14;
docs/DASHBOARD_DESIGN.md section 5): the columns code finds eligible, the
AI's choice among them (breakdown_suggestion.json, stored once per run), and
what Review shows. The AI chooses names from a list code builds - it writes
no text and no number; its answer is validated against that list."""

from typing import ClassVar, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from contracts._base import ContractFile, ContractModel
from contracts.metrics import MAX_BREAKDOWNS

SuggestionStatus = Literal["chosen", "none_eligible", "ai_unavailable"]


class BreakdownAnswer(ContractModel):
    """The AI's answer, as it must arrive: at most two column names, and
    nothing else - free text beside them is no answer (it would be stored or
    shown nowhere, but the answer is held to its schema exactly)."""

    model_config = ConfigDict(extra="forbid")

    breakdowns: list[str] = Field(max_length=MAX_BREAKDOWNS)


class BreakdownSuggestion(ContractFile):
    """breakdown_suggestion.json: the one AI answer of the run about which
    columns to split sales by. Stage 1 only; no later stage reads it."""

    filename: ClassVar[str | None] = "breakdown_suggestion.json"
    written_by_stage: ClassVar[int] = 1
    supported_major: ClassVar[int] = 1
    stale_major_hint: ClassVar[str] = ": this file was written by another version of stage 1; re-upload the file"
    # The eligible columns when the AI was asked (the list it chose from).
    eligible: list[str]
    chosen: list[str] = Field(max_length=MAX_BREAKDOWNS)
    # "none_eligible": no column could split sales - the AI was not asked;
    # "ai_unavailable": asked, no valid answer (never a guess: nothing chosen).
    status: SuggestionStatus
    model_used: str | None

    @model_validator(mode="after")
    def _as_its_status(self) -> Self:
        if not set(self.chosen) <= set(self.eligible) or len(set(self.chosen)) != len(self.chosen):
            raise ValueError("the chosen columns are eligible ones, each once")
        if self.status != "chosen" and self.chosen:
            raise ValueError(f"a {self.status} suggestion chooses nothing")
        if (self.status == "none_eligible") != (not self.eligible):
            raise ValueError("no eligible column exactly when none was eligible")
        if (self.model_used is None) == (self.status == "chosen"):
            raise ValueError("a model answered exactly when the columns were chosen")
        return self


class EligibleColumn(ContractModel):
    """A column Review offers: its header as written and its commonest values
    (the profile's, at most 10) - what the user and the AI both see."""

    column: str
    values: list[str]


class WholeOrderQuestion(ContractModel):
    """Thach's Q7 (2026-10-16): a column written on each order's first line
    only - the data cannot tell an order's field from a line's - asked once:
    does it apply to the whole order? Worded by stage 1; `answer` is the
    plan's (null: not answered - the column is not offered)."""

    column: str
    question: str
    answer: bool | None


class BreakdownQuestion(ContractModel):
    """Review's control (POST /breakdowns): the eligible columns, the ones
    suggested (still eligible under the plan as edited), and one line saying
    where the suggestion came from - worded here, so the page words nothing."""

    eligible: list[EligibleColumn]
    suggested: list[str] = Field(max_length=MAX_BREAKDOWNS)
    status: SuggestionStatus
    message: str
    # Q7: the first-line columns Review asks about, in the file's order.
    whole_order: list[WholeOrderQuestion] = Field(default_factory=list)
