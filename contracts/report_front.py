"""report.json's front section (2.9; docs/REPORT_REDESIGN.md sections 1, 6, 7
and 2): the code-written sentences and bars a shop owner reads first - ONE
copy, which report.html prints and the page will (step 5). Every figure in
them is a field of an earlier file, formatted; nothing is computed (CONTRACTS
9 and 11). The technical appendix is the rest of report.json, as before.

Split out of contracts/report.py for file size.
"""

from datetime import date
from typing import Literal, Self

from pydantic import Field, PositiveInt, model_validator

from contracts._base import ContractModel, YearMonth
from contracts.currency import CurrencyCode
from contracts.lines import NoteCode

# Words the front section never uses (design section 3 and Q3): the
# analyst's vocabulary and every adjective verdict on a month or a change.
# One copy: the tests read it over report.html outside its appendix.
FRONT_BANNED = ("hypothesis", "hypotheses", "verdict", "supported", "ruled out", "lens", "lever", "share",
                "contribution", "aov", "yoy", "year-over-year", "limits", "inconclusive", "revenue", "caused",
                "because of", "explains", "launched", "discontinued", "usual", "unusual", "normal", "abnormal",
                "ordinary", "bigger than usual", "median")

Factor = Literal["customers", "frequency", "orders", "aov", "units_per_order", "price_per_unit"]


def _cents(value: float) -> int:
    return round(value * 100)


class FrontBar(ContractModel):
    """One part of the change: its label, its value in each month as shown,
    and what it added or took away (the bridge's shown cents)."""

    factor: Factor
    label: str
    was: str
    now: str
    shown: float
    worth: str


class Waterfall(ContractModel):
    """Section 2: last month's sales, each part, this month's sales - the
    bridge as stage 3 wrote it (tree.lever.bridge), its bars summing to the
    shown change to the cent (Q2)."""

    previous_label: str
    current_label: str
    shown_previous: float
    shown_current: float
    shown_change: float
    previous_text: str
    current_text: str
    change_text: str
    bars: list[FrontBar] = Field(min_length=1)
    caption: str
    # Why the order value is one bar (the split withheld; Q1); null when drawn.
    note: str | None

    @model_validator(mode="after")
    def _the_bars_add_up(self) -> Self:
        if sum(_cents(bar.shown) for bar in self.bars) != _cents(self.shown_change):
            raise ValueError("the bars add up exactly to the shown change")
        if _cents(self.shown_previous) + _cents(self.shown_change) != _cents(self.shown_current):
            raise ValueError("last month plus the change is this month, to the cent")
        return self


class ChecklistGroup(ContractModel):
    """Section 3: one group of the plain checklist."""

    kind: Literal["matches", "moved", "against", "not_reason", "cannot_show"]
    title: str
    note: str | None  # under rule 7: why none of these is called the reason (Q16)
    lines: list[str] = Field(min_length=1)
    # Under the first group: the amounts overlap and do not add up (Q20).
    after: str | None


class FrontAction(ContractModel):
    """Section 4: one suggestion - the figure it rests on and what to watch
    (code), the action and why (the AI, no number)."""

    rests_on: str
    action: str
    why: str
    watch: str


class NextSteps(ContractModel):
    """Section 4 by forecast.json's `actions_status`: the list, or one
    sentence saying why there is none - "unavailable" where the file holds
    no answer this report can show (a forecast before 2.1 with the AI step
    on; actions listed where no cause is named: Thach, Q36)."""

    status: Literal["off", "suppressed", "list", "unavailable"]
    sentence: str | None
    items: list[FrontAction]

    @model_validator(mode="after")
    def _a_list_or_why_not(self) -> Self:
        if self.items and self.status != "list":
            raise ValueError("suggestions are listed only when the status is 'list'")
        if (self.sentence is None) != bool(self.items):
            raise ValueError("the sentence says why there is no suggestion, exactly when there is none")
        return self


class FrontNotes(ContractModel):
    """The notes beside each section's figures (Thach, Q35; CLAUDE.md 3.3a): a
    note's link wherever a figure it names is shown - the sales (summary),
    the parts of the change, the checks, next month's estimate."""

    summary: list[NoteCode]
    change: list[NoteCode]
    checked: list[NoteCode]
    next_month: list[NoteCode]
    # Section 4 reprints its claims' figures (step 4's review; 3.3a).
    next_steps: list[NoteCode] = Field(default_factory=list)


class CannotKnow(ContractModel):
    """Section 6: one thing this report cannot know, in plain words."""

    title: str
    text: str


class Front(ContractModel):
    # "compared": this month against the last; "not_compared": the previous
    # month is incomplete or this month's figures are withheld - this month
    # alone, no change, no bar (CONTRACTS 11); "blocked": the data cannot
    # support conclusions - sections 1-4 replaced by one sentence.
    state: Literal["compared", "not_compared", "blocked"]
    # A caution opens section 1: each cautioning check's line, by its id,
    # status and month (the general opener left the front: Thach's safety
    # valve, 2026-10-06).
    caution: list[str]
    summary: list[str] = Field(min_length=1)
    sales_note: str  # D5's sentence (and "Amounts are in your file's currency." when not stated)
    chart_title: str
    chart_note: list[str]  # D7: the part-months, by their dates only (Q13)
    waterfall: Waterfall | None
    waterfall_note: str | None  # why no chart of the change is drawn
    checklist: list[ChecklistGroup]
    # D1-D3 (Thach, 2026-10-06): one line when no check cautions or blocks,
    # else each caution's line (as in `caution`); every check's detail lives in
    # the appendix. Empty only when blocked (the summary is the check).
    data_checks: list[str]
    next_steps: NextSteps | None
    next_month: list[str]
    cannot_know: list[CannotKnow]
    # The notes beside each section's figures (Q35; CONTRACTS 11: a note
    # stands beside the figures it names), linked to their sentence in the
    # appendix.
    notes: FrontNotes

    @model_validator(mode="after")
    def _as_its_state(self) -> Self:
        if self.state != "compared" and (self.waterfall is not None or self.checklist or self.waterfall_note):
            raise ValueError("no change is split or checked unless this month is compared with the last")
        if self.state == "blocked" and (self.next_steps is not None or self.caution or self.data_checks):
            raise ValueError("a blocked report shows one sentence for sections 1 to 4")
        if self.state != "blocked" and not self.data_checks:
            raise ValueError("the data checks are said: one line, or each caution's")
        if self.state == "compared" and self.next_steps is None:
            raise ValueError("a compared report says what to do next, or why nothing is suggested")
        if self.waterfall is not None and self.waterfall_note is not None:
            raise ValueError("a chart of the change is drawn, or why not is said - never both")
        return self


class LeverTerm(ContractModel):
    """One factor of a level of the change's split, exact (the appendix:
    design 1.7 - the withheld split stays visible to an analyst)."""

    name: Factor
    value_prev: float
    value_cur: float
    contribution: float


class LeverLevelView(ContractModel):
    """diagnosis.json's tree.lever level 1, level 2, or the orders x average
    order value pair, as it stands."""

    level: Literal["level1", "level2", "pair"]
    formula: str
    factors: list[LeverTerm]


class ReportCurrency(ContractModel):
    """The currency the amounts are in (cleaning_report.json `currency`; D6,
    Q8): its ISO code on every amount, or none and the one sentence."""

    code: CurrencyCode | None
    sentence: str | None

    @model_validator(mode="after")
    def _a_code_or_the_sentence(self) -> Self:
        if (self.code is None) != (self.sentence is not None):
            raise ValueError("amounts carry the code, or the sentence says they are in the file's currency")
        return self


class RowsLeftOut(ContractModel):
    """A cleaning step that left rows out (cleaning_report.json `changes[]`
    with rows_affected > 0, by its action): the one copy the page reads."""

    action: str
    column: str | None
    rows: PositiveInt
    sentence: str


class PartialMonth(ContractModel):
    """A month the file covers only part of (D7): first or last, by its
    dates - its figure stays in the appendix's monthly table (Q13)."""

    period: YearMonth
    covers_from: date
    covers_to: date
    position: Literal["first", "last"]

    @model_validator(mode="after")
    def _inside_its_month(self) -> Self:
        if not (f"{self.covers_from:%Y-%m}" == f"{self.covers_to:%Y-%m}" == self.period) \
                or self.covers_from > self.covers_to:
            raise ValueError("a part-month's dates lie inside it, in order")
        return self
