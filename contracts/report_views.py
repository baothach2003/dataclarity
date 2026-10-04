"""report.json's leaf views (docs/CONTRACTS.md section 9), split out of
contracts/report.py for file size (session 5A): each row as the report
shows it, with the rules a single row can hold by itself."""

from datetime import date
from typing import Any, Literal, Self

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from contracts._base import ContractModel, YearMonth
from contracts.lines import (
    NOTE_TEXTS,
    OUTSIDE_REVENUE_TEXTS,
    FigureNote,
    NoteCode,
    NoteFigure,
    NoteMeasure,
    OutsideRevenueLines,
)


KPI_IDS = ("revenue", "orders", "active_customers", "aov", "return_rate")


def month_after(year_month: str) -> str:
    """"2011-12" after "2011-11" - the calendar, as contracts/forecast.py
    checks its own months (not a period definition: shared/periods)."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    return f"{year + month // 12:04d}-{month % 12 + 1:02d}"


class DataQuality(ContractModel):
    rows_in: NonNegativeInt
    rows_out: NonNegativeInt
    # The plan's changes that did something: changed a cell, or dropped or
    # marked a row (an action that changed nothing is still logged - 1D).
    issues_fixed: NonNegativeInt
    warnings: NonNegativeInt


class ChartSeries(ContractModel):
    name: str
    x: list[str]
    y: list[float | None]  # null: a month not drawn - a gap, never a zero or a join

    @model_validator(mode="after")
    def _points_pair_up(self) -> Self:
        if len(self.x) != len(self.y):
            raise ValueError(
                f"x and y must have the same length, got {len(self.x)} and {len(self.y)}"
            )
        return self


class Chart(ContractModel):
    id: Literal["revenue_trend", "forecast"]
    type: str
    title: str
    series: list[ChartSeries]
    notes: list[NoteCode]  # the notes beside the figure it plots, by code (the standing rule)
    note: str | None  # why the line has a gap, or the forecast's own notes
    # The trust checks that caution or block the compared months - a
    # cut-short month is plotted as it stands, so the caution stands beside it.
    cautions: list[str]

    @model_validator(mode="after")
    def _its_own_series(self) -> Self:
        """The revenue line is one series, "revenue"; the forecast its point,
        low and high - what report.html draws, and nothing it cannot (5B
        review 1 #6)."""
        names = [series.name for series in self.series]
        expected = ["revenue"] if self.id == "revenue_trend" else ["point", "low", "high"]
        if names != expected:
            raise ValueError(f"chart {self.id!r} plots {expected}, got {names}")
        if len({tuple(series.x) for series in self.series}) > 1:
            raise ValueError(f"chart {self.id!r}: its series share their months")
        return self


class Provenance(ContractModel):
    stages_run: list[str]
    # The AI answers the run's files hold - a schema inference, an AI-proposed
    # plan, a narration, recommendations - not the calls made (retries and
    # failures are in the server's logs).
    ai_calls: NonNegativeInt
    models_used: list[str]


class NoteView(ContractModel):
    """A note as the report shows it: worded from `contracts.lines.NOTE_TEXTS`
    by its code, never the file's sentence (CONTRACTS 11)."""

    code: NoteCode
    text: str
    figures: list[NoteFigure]
    measures: list[NoteMeasure]

    @model_validator(mode="after")
    def _worded_by_its_code(self) -> Self:
        if self.text != NOTE_TEXTS[self.code]:
            raise ValueError(f"note {self.code!r} is worded by its code, from NOTE_TEXTS")
        return self

    @property
    def always_on(self) -> bool:
        return FigureNote(code=self.code, figures=self.figures, text=self.text, measures=self.measures).always_on


class ReportPeriod(ContractModel):
    current: YearMonth
    previous: YearMonth
    data_start: date
    data_end: date
    previous_complete: bool
    previous_incomplete_reason: str | None

    @model_validator(mode="after")
    def _incomplete_with_its_reason(self) -> Self:
        if month_after(self.previous) != self.current or self.data_start > self.data_end:
            raise ValueError("the previous month is the one before the current, and the data starts before it ends")
        if self.previous_complete != (self.previous_incomplete_reason is None):
            raise ValueError("previous_incomplete_reason says why exactly when the previous month is incomplete")
        return self


class TrustCheckView(ContractModel):
    id: Literal["D1", "D2", "D3"]
    status: Literal["ok", "caution", "blocked", "inconclusive", "not_applicable"]
    message: str  # the reason a caution is shown - a cut-short month, a gap (CONTRACTS 6)


class TrustBadge(ContractModel):
    """Shown beside the period-over-period KPIs (CONTRACTS 6): it covers what
    stage 2 cannot see."""

    verdict: Literal["trusted", "caution", "blocked"]
    checks: list[TrustCheckView]
    limitations: list[str]


class Kpi(ContractModel):
    id: Literal["revenue", "orders", "active_customers", "aov", "return_rate"]
    label: str  # "Lines", "Average line value", "Return lines per sale line" with no order numbers (CONTRACTS 6)
    # "ratio": returns per sale, from 0 up with no ceiling - not a share of a whole.
    unit: Literal["money", "count", "ratio"]
    current: int | float | None  # a count stays whole
    # Null whenever the previous month is not complete: it is never compared
    # (CONTRACTS 11); `previous_reason` then says why.
    previous: int | float | None
    change_pct: float | None  # revenue's alone: no other change is computed (CONTRACTS 11)
    change_reason: str | None  # why revenue's change is null
    current_reason: str | None
    previous_reason: str | None
    notes: list[NoteCode]  # the notes beside this figure, by code

    @model_validator(mode="after")
    def _a_null_carries_its_reason(self) -> Self:
        """CONTRACTS 11: a null figure is a value - show the reason."""
        if (self.current is None and not self.current_reason) or (self.previous is None and not self.previous_reason):
            raise ValueError(f"{self.id}: a null figure carries its reason")
        if self.id == "revenue" and self.change_pct is None and not self.change_reason:
            raise ValueError("revenue's change is null only with its reason")
        return self


class MonthRevenue(ContractModel):
    period: YearMonth
    # Null for a month inside the file's span with no line at all: a closed
    # month or missing data, which the file cannot tell apart - never a zero.
    revenue: float | None
    revenue_reason: str | None
    # Covered from its first day to its last (shared/periods.complete_months),
    # never after the current month, and the compared month only when the
    # KPIs compare with it too (`previous_complete`).
    complete: bool

    @model_validator(mode="after")
    def _null_with_its_reason(self) -> Self:
        if (self.revenue is None) != (self.revenue_reason is not None):
            raise ValueError("a month's revenue is null exactly when its reason says why")
        return self


AGAINST = "moved against the change"


def against_label(contribution: float) -> str:
    """The verdict label of a hypothesis ruled out for moving against the
    change: its contribution, signed, to the cent - the one copy stage 5
    writes and this contract checks (Thach, 2026-10-04, (vii))."""
    return f"{AGAINST} ({'+' if contribution > 0 else '-'}{abs(contribution):,.2f})"


def prints_as_zero(value: float) -> bool:
    return f"{abs(value):,.2f}" == "0.00"


class HypothesisView(ContractModel):
    id: str
    statement: str
    verdict: Literal["supported", "partial", "ruled_out", "inconclusive", "not_testable"]
    contribution: float | None
    share: float | None
    # Why a figure is null ("not evaluated: blocked run"), and the test of a
    # directional hypothesis - shown as written, key by key (CONTRACTS 11).
    rule: str
    evidence: dict[str, Any]
    # 2.5 (Thach, 2026-10-04, decisions (vii) and (viii)): one copy of what
    # report.html and the page print. Ruled out for moving AGAINST the change
    # it claims to explain (stage 3's statement, diagnosis.json
    # `against_the_change`, shown only beside a compared month the report
    # shows); the verdict as shown - `against_label` or the code's words; the
    # evidence as report.html words it, key by key. Absent from a 2.4 report.
    moved_against: bool = False
    verdict_label: str | None = None
    evidence_text: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_label(self) -> Self:
        if self.moved_against:
            if (self.verdict != "ruled_out" or self.contribution is None or self.share is None
                    or prints_as_zero(self.contribution)):
                raise ValueError("only a ruled_out share hypothesis whose contribution prints moved against the change")
            if self.verdict_label != against_label(self.contribution):
                raise ValueError(f"moved against the change is labelled {against_label(self.contribution)!r}, "
                                 f"not {self.verdict_label!r}")
        elif self.verdict_label is not None and self.verdict_label != self.verdict.replace("_", " "):
            raise ValueError(f"the label {self.verdict_label!r} is not its code's ({self.verdict.replace('_', ' ')!r})")
        if (self.verdict_label is not None or self.evidence_text) and (
                len(self.evidence_text) != len(self.evidence)
                or any(not line.startswith(f"{key}: ") for line, key in zip(self.evidence_text, self.evidence))):
            # A 2.5 row (a label, or any text) words its evidence key by key, in order. The value's
            # wording is stage 5's (html_parts.evidence_value) and not re-checked here.
            raise ValueError("the evidence text is the evidence, key by key, in order")
        return self


class OutsideRevenueView(OutsideRevenueLines):
    """A line outside revenue as the report shows it: with why, worded by its
    class code (Thach, 2026-10-04, decision (ix); 2.5, absent from a 2.4
    report)."""

    reason: str | None = None

    @model_validator(mode="after")
    def _worded_by_its_class_code(self) -> Self:
        if self.reason is not None and self.reason != OUTSIDE_REVENUE_TEXTS.get(self.line_class):
            raise ValueError(f"lines of {self.line_class!r} are worded by their class code, from OUTSIDE_REVENUE_TEXTS")
        return self


class SignalView(ContractModel):
    """A signal row as the file has it: a description, never a verdict
    (ADR-0006, ADR-0007)."""

    series: str
    # The series as the KPIs name it - lines, not orders, on a file with no
    # order numbers (CONTRACTS 6; 5B review 2 #2).
    label: str
    mode: Literal["level", "yoy"]
    signal: Literal["above", "below", "within", "insufficient_history"]
    value_cur: float | None
    center: float | None
    lower: float | None
    upper: float | None
    rule: Literal[1, 2] | None
    mode_fallback: Literal["no_year_ago_value", "unusable_year_ago_base"] | None
    insufficient_reason: Literal["too_few_points", "no_current_value", "no_measurable_spread"] | None
    # "minimum_spread": no variation was measured and a floor drew the limits
    # - a reader must be able to tell that from a measured chart (CONTRACTS 7;
    # 5B review 2 #1).
    limits_method: Literal["median_moving_range", "mean_moving_range", "minimum_spread"]


class RecommendationView(ContractModel):
    """forecast.json's recommendation, its confidence shown as a label, never
    as a figure (CLAUDE.md 3.2: the AI's own number is not a computed one)."""

    priority: PositiveInt
    insight: str
    cause: str
    action: str
    expected_impact: str
    how_to_measure: str
    confidence_label: Literal["low", "medium", "high"]
