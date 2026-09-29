"""report.json, the data layer of stage 5 (docs/CONTRACTS.md section 9).

Defined in session 5A (in place at 1.0: no report.json had been written).
Stage 5 performs no analysis: every number here is a field of an earlier
contract file, selected and ordered - never computed. The three layers
answer "what happened" (numbers), "why" (causes) and "what next" (actions).
The rows are in `contracts/report_views.py`; the rules held across rows are
here, so a report that breaks what CONTRACTS 11 asks of every consumer is
refused (5A reviews 1 #14 and 2 #7).
"""

from datetime import date
from typing import ClassVar, Literal, Self

from pydantic import NonNegativeInt, model_validator

from contracts._base import ContractFile, ContractModel
from contracts.diagnosis import AiFindings, Headline, NotTestable
from contracts.forecast import DoNotDo, RevenuePoint
from contracts.lines import NoteCode, OutsideRevenueLines, UnmeasurableLines
from contracts.metrics import NonProductLines
from contracts.profile import LineClass
from contracts.report_views import (
    KPI_IDS,
    Chart,
    ChartSeries,
    DataQuality,
    HypothesisView,
    Kpi,
    MonthRevenue,
    NoteView,
    Provenance,
    RecommendationView,
    ReportPeriod,
    SignalView,
    TrustBadge,
    TrustCheckView,
    month_after,
)

__all__ = ["Actions", "Causes", "Chart", "ChartSeries", "DataQuality", "ForecastView", "HypothesisView", "Kpi",
           "MonthRevenue", "NoteView", "Numbers", "Provenance", "RecommendationView", "ReportContract",
           "ReportPeriod", "SignalView", "TrustBadge", "TrustCheckView"]

_ALWAYS_ON_ONCE = "an always-on note is shown once, in how_to_read, and only there"


# --- layer 1: the numbers (metrics.json, and the trust badge of diagnosis.json) ----------------


class Numbers(ContractModel):
    period: ReportPeriod
    trust: TrustBadge
    kpis: list[Kpi]
    # Beside the KPIs when the file starts part-way through the current month:
    # stage 2 takes it as the month (a shop that opened then), which the file
    # cannot tell from an export cut short (the standing rule; review 3 #1).
    current_note: str | None
    revenue_by_month: list[MonthRevenue]
    # Lines in no figure (CONTRACTS 6: never dropped silently), and the money
    # of the classes the user gave that is not product revenue - where it
    # went is in each reason (an adjustment is a reconciling amount).
    undated_lines: NonNegativeInt
    undated_lines_reason: str | None
    unmeasurable: list[UnmeasurableLines]
    non_product: list[NonProductLines]
    outside_revenue: list[OutsideRevenueLines]
    # Always-on notes, ONCE, in "How to read these figures" (Thach,
    # adjustment 1); the file's own notes beside the figures they name.
    how_to_read: list[NoteView]
    notes: list[NoteView]

    @model_validator(mode="after")
    def _as_stage_5_shows_them(self) -> Self:
        """The rules CONTRACTS 11 sets for every consumer, held by the file."""
        period = self.period
        if [kpi.id for kpi in self.kpis] != list(KPI_IDS):
            raise ValueError(f"the KPIs are {', '.join(KPI_IDS)}, once each, in that order")
        for kpi in self.kpis:
            if kpi.change_pct is not None and kpi.id != "revenue":
                raise ValueError(f"{kpi.id} has a change: only revenue's is carried (CONTRACTS 11)")
            if not period.previous_complete and (kpi.previous is not None or kpi.change_pct is not None):
                raise ValueError(f"{kpi.id} is compared with an incomplete previous month (CONTRACTS 11)")
        months = [month.period for month in self.revenue_by_month]
        if months != sorted(set(months)):
            raise ValueError("the months are listed once each, in order")
        for month in self.revenue_by_month:
            if month.complete and month.period > period.current:
                raise ValueError(f"{month.period} is after the current month, so never complete")
            if month.complete and month.period == period.previous and not period.previous_complete:
                raise ValueError(f"{month.period} is drawn whole only when the KPIs compare with it")
        if not all(note.always_on for note in self.how_to_read) or any(note.always_on for note in self.notes):
            raise ValueError(_ALWAYS_ON_ONCE)
        _once_each([note.code for note in self.how_to_read])
        _once_each([note.code for note in self.notes])
        return self


def _once_each(codes: list[str]) -> None:
    if len(codes) != len(set(codes)):
        raise ValueError(f"a note is shown once in a list: {codes}")


# --- layer 2: the causes (diagnosis.json) -------------------------------------------------------


class Causes(ContractModel):
    headline: Headline
    hypotheses: list[HypothesisView]
    not_testable: list[NotTestable]
    signals: list[SignalView] | None
    narration: AiFindings | None  # stage 3's AI narration (3F); null in v1 so far
    narration_status: Literal["shown", "unavailable"]  # AI_PIPELINE 9: a null AI block shows as unavailable
    notes: list[NoteView]
    suggested_classes: dict[str, LineClass]

    @model_validator(mode="after")
    def _narration_as_its_status(self) -> Self:
        if (self.narration is not None) != (self.narration_status == "shown"):
            raise ValueError("narration_status is 'shown' exactly when there is a narration")
        if any(note.always_on for note in self.notes):
            raise ValueError(_ALWAYS_ON_ONCE)
        _once_each([note.code for note in self.notes])
        return self


# --- layer 3: the actions (forecast.json) -------------------------------------------------------


class ForecastView(ContractModel):
    method: str
    months_used: NonNegativeInt
    insufficient_history: bool
    points: list[RevenuePoint]
    history_note: str | None
    season_note: str | None
    notes: list[NoteCode]  # metrics.json's notes naming revenue, beside the forecast (CONTRACTS 11)
    # The first forecast month is one the file holds lines of, so its revenue
    # so far is never compared with the point. A day-grain file says the day
    # it ends; a month-grain file's month-to-date line has no such day.
    first_month_in_file: bool
    partial_first_month_until: date | None

    @model_validator(mode="after")
    def _a_day_only_in_the_first_forecast_month(self) -> Self:
        if self.first_month_in_file and not self.points:
            raise ValueError("first_month_in_file needs a forecast month")
        until = self.partial_first_month_until
        if until is not None and not (self.first_month_in_file and f"{until:%Y-%m}" == self.points[0].period):
            raise ValueError("partial_first_month_until is the day the file ends in the first forecast month")
        return self


class Actions(ContractModel):
    forecast: ForecastView
    recommendations: list[RecommendationView] | None
    do_not_do: list[DoNotDo] | None
    # "switched_off": stage 4's AI step is off (v1's default, 4B), whatever
    # the file holds; "unavailable": no accepted answer (AI_PIPELINE 9).
    recommendations_status: Literal["shown", "switched_off", "unavailable"]
    notes: list[NoteCode]  # beside the recommendations: every note that is not always-on (CONTRACTS 11)

    @model_validator(mode="after")
    def _recommendations_as_their_status(self) -> Self:
        shown = self.recommendations is not None and self.do_not_do is not None
        if shown != (self.recommendations_status == "shown") or (self.recommendations is None) != (
                self.do_not_do is None):
            raise ValueError("recommendations and do_not_do are shown together, exactly when the status says so")
        return self


class ReportContract(ContractFile):
    filename: ClassVar[str | None] = "report.json"
    written_by_stage: ClassVar[int] = 5
    stale_major_hint: ClassVar[str] = ": this file was written by an earlier stage 5; build the report again"
    run_id: str
    source_file: str
    data_quality: DataQuality
    layer_1_numbers: Numbers
    layer_2_causes: Causes
    layer_3_actions: Actions
    charts: list[Chart]
    provenance: Provenance

    @model_validator(mode="after")
    def _figures_and_notes_agree(self) -> Self:
        """A note named beside a figure is one the report shows beside
        figures (so never an always-on one); a chart plots the report's own
        figures."""
        numbers, actions = self.layer_1_numbers, self.layer_3_actions
        shown = {note.code for note in [*numbers.notes, *self.layer_2_causes.notes]}
        lists = [*(kpi.notes for kpi in numbers.kpis), actions.notes, actions.forecast.notes,
                 *(chart.notes for chart in self.charts)]
        named = {code for codes in lists for code in codes}
        if not named <= shown:
            raise ValueError(f"notes named beside a figure but not shown: {sorted(named - shown)}; {_ALWAYS_ON_ONCE}")
        for codes in lists:
            _once_each(codes)
        if len({chart.id for chart in self.charts}) != len(self.charts):
            raise ValueError("each chart is drawn once")
        self._forecast_of_these_months()
        months = {month.period: month for month in numbers.revenue_by_month}
        points = {point.period: point for point in actions.forecast.points}
        for chart in self.charts:
            for series in chart.series:
                if chart.id == "revenue_trend" and any(
                        later != month_after(earlier) for earlier, later in zip(series.x, series.x[1:])):
                    raise ValueError("the revenue chart's months follow each other: a gap is a null, never a join")
                if chart.id == "forecast" and series.name not in ("point", "low", "high"):
                    raise ValueError(f"the forecast chart plots its point, low and high, not {series.name!r}")
                for x, y in zip(series.x, series.y):
                    if chart.id == "revenue_trend":
                        month = months.get(x)
                        drawn = None if month is None or not month.complete else month.revenue
                        if month is None or y != drawn:
                            raise ValueError(f"the revenue chart plots {x} as revenue_by_month has it, whole or not")
                    elif chart.id == "forecast" and (x not in points or y != getattr(points[x], series.name, None)):
                        raise ValueError(f"the forecast chart plots the forecast's own {series.name} for {x}")
        return self

    def _forecast_of_these_months(self) -> None:
        """The forecast starts the month after the current one, and it says
        whether the file holds lines of that month - which stops its revenue
        so far being compared with the point (review 3 #9)."""
        period, forecast = self.layer_1_numbers.period, self.layer_3_actions.forecast
        points = forecast.points
        if points and points[0].period != month_after(period.current):
            raise ValueError(f"the forecast starts at {points[0].period}, not the month after {period.current}")
        if forecast.first_month_in_file != (bool(points) and points[0].period == f"{period.data_end:%Y-%m}"):
            raise ValueError("first_month_in_file says whether the file ends inside the first forecast month")
        if forecast.partial_first_month_until not in (None, period.data_end):
            raise ValueError("partial_first_month_until is the day the file ends")
