"""The three layers of report.json (docs/CONTRACTS.md section 9), split out
of builder.py for file size (session 5A).

Each layer selects and orders fields of an earlier file: no figure is
computed but the one metrics.json carries (`revenue_change_pct`), and an
incomplete previous month is never shown beside the current (CONTRACTS 11).
Notes are worded by their code (`NOTE_TEXTS`): an always-on note once, in
"How to read these figures" (Thach, adjustment 1), the others beside the
figures they name, the forecast and the recommendations.
"""

import calendar
from collections.abc import Sequence
from datetime import date

from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.lines import NOTE_TEXTS, FigureNote
from contracts.metrics import MetricsContract
from contracts.report import (
    Actions,
    Causes,
    ForecastView,
    HypothesisView,
    Kpi,
    MonthRevenue,
    NoteView,
    Numbers,
    RecommendationView,
    ReportPeriod,
    SignalView,
    TrustBadge,
    TrustCheckView,
)
from shared.periods import complete_months, shift_month

# Each KPI: its metrics.json field stem, unit, and the note figure that names it.
_KPIS = (("revenue", "money", "revenue"), ("orders", "count", "orders"),
         ("active_customers", "count", "customers"), ("aov", "money", "aov"),
         ("return_rate", "ratio", "return_rate"))
_LABELS = {"revenue": "Revenue", "orders": "Orders", "active_customers": "Active customers",
           "aov": "Average order value", "return_rate": "Return rate"}
# CONTRACTS 6: a file with no order numbers counts lines.
_LINES_LABELS = {"orders": "Lines", "aov": "Average line value", "return_rate": "Return lines per sale line"}
# The signal series (diagnosis.json) named as the KPIs are (5B review 2 #2).
_SERIES_LABELS = {"revenue": "Revenue", "orders": "Orders", "active_customers": "Active customers",
                  "frequency": "Orders per customer", "aov": "Average order value",
                  "units_per_order": "Units per order", "price_per_unit": "Price per unit",
                  "return_rate": "Return rate"}
_SERIES_LINES_LABELS = {"orders": "Lines", "frequency": "Lines per customer", "aov": "Average line value",
                        "units_per_order": "Units per line", "return_rate": "Return lines per sale line"}
# Stage 2 counts 0 customers when no line names one: a zero read as real
# (CONTRACTS 11 - show the reason, never a zero).
NO_CUSTOMER_COLUMN = "no column is mapped as the customer, so no customer can be counted"
NO_LINE_IN_MONTH = ("no line counted in revenue is dated in it - a closed month or missing data, which the file "
                    "cannot tell apart")
# The AI's own confidence, shown as a word (CLAUDE.md 3.2): the floor of each
# label, highest first; below the last, "low". Display cut points (5A).
CONFIDENCE_LABELS = ((0.7, "high"), (0.4, "medium"))


def view(note: FigureNote) -> NoteView:
    return NoteView(code=note.code, text=NOTE_TEXTS[note.code], figures=list(note.figures),
                    measures=list(note.measures))


def _unique(notes: Sequence[FigureNote]) -> list[FigureNote]:
    seen: set[str] = set()
    return [n for n in notes if not (n.code in seen or seen.add(n.code))]  # type: ignore[func-returns-value]  # set.add


def revenue_notes(metrics: MetricsContract) -> list[str]:
    """metrics.json's notes naming revenue: beside the forecast and the
    revenue it plots (CONTRACTS 11)."""
    return [n.code for n in metrics.core.notes if not n.always_on and "revenue" in n.figures]


def _empty_current(metrics: MetricsContract) -> str | None:
    """Why the current month's figures are withheld when no line counted in
    revenue is dated in it: stage 2 writes 0 there, which cannot tell a
    closed month from missing data (the standing rule; 5A review 2 #1)."""
    period, core = metrics.period, metrics.core
    months = {m.period for m in core.revenue_by_month}
    if period.current in months:
        return None
    if not months and core.undated_lines:
        # Stage 2 then dates the period by the analysis day (review 3 #7).
        return "no line counted in revenue carries a date the file can read"
    if period.current < f"{period.data_start:%Y-%m}":
        return f"the file starts on {period.data_start.isoformat()}, after {period.current}: it holds none of that month"
    if any(u.scope == "current" for u in core.unmeasurable):
        # Its lines are there, unpriced or without a quantity (review 4 #3).
        return f"no line dated in {period.current} can be measured - see the lines in no figure"
    return (f"no line counted in revenue is dated in {period.current} - a closed month or missing data, which the "
            "file cannot tell apart")


def _current_note(metrics: MetricsContract) -> str | None:
    """Stage 2 takes a month the file starts inside as a fair current month
    (a shop that opened mid-month: `shared/periods.complete_months`); the
    file cannot tell that from an export cut short, so its figures stand
    with this note beside them (the standing rule; 5A review 3 #1). None
    when the figures are withheld: their reason says it (review 4 #1, #4)."""
    period = metrics.period
    if period.month_grain or f"{period.data_start:%Y-%m}" != period.current or period.data_start.day == 1 \
            or _empty_current(metrics):
        return None
    return (f"The file starts on {period.data_start.isoformat()}, part-way through {period.current}: the current "
            "month's figures cover it from that day - a shop that opened then, or an export cut short, which the file "
            "cannot tell apart.")


def _unnamed(metrics: MetricsContract, scope: str, has_customers: bool) -> str | None:
    """Why active customers are withheld in a month none of whose lines
    names a customer: stage 2 counts 0 there. A month with no line at all is
    withheld whole (`_empty_current`), and a compared month always has a
    sale, so a 0 here is never a count of real buyers (5A reviews 1 #9, 2
    #5, 3 #3)."""
    if getattr(metrics.core, f"active_customers_{scope}"):
        return None
    month = metrics.period.current if scope == "current" else metrics.period.previous
    return NO_CUSTOMER_COLUMN if not has_customers else f"no line in {month} names a customer"


def _kpis(metrics: MetricsContract, beside: Sequence[FigureNote], has_customers: bool) -> list[Kpi]:
    core, period = metrics.core, metrics.period
    comparable, empty = period.previous_complete, _empty_current(metrics)
    labels = _LABELS | (_LINES_LABELS if core.orders_basis == "lines" else {})
    if not comparable:
        change, change_reason = None, period.previous_incomplete_reason
    elif empty:
        change, change_reason = None, empty
    else:
        change, change_reason = core.revenue_change_pct, core.revenue_change_pct_reason
    found = []
    for kpi_id, unit, figure in _KPIS:
        customers = kpi_id == "active_customers"
        withheld = empty or (_unnamed(metrics, "current", has_customers) if customers else None)
        withheld_previous = _unnamed(metrics, "previous", has_customers) if customers else None
        if not comparable:
            previous, previous_reason = None, period.previous_incomplete_reason
        else:
            previous = None if withheld_previous else getattr(core, f"{kpi_id}_previous")
            previous_reason = withheld_previous or getattr(core, f"{kpi_id}_previous_reason", None)
        found.append(Kpi(
            id=kpi_id, label=labels[kpi_id], unit=unit,
            current=None if withheld else getattr(core, f"{kpi_id}_current"),
            current_reason=withheld or getattr(core, f"{kpi_id}_current_reason", None),
            previous=previous, previous_reason=previous_reason,
            change_pct=change if kpi_id == "revenue" else None,
            change_reason=change_reason if kpi_id == "revenue" else None,
            notes=[n.code for n in beside if figure in n.figures]))
    return found


def _months(metrics: MetricsContract) -> list[MonthRevenue]:
    """Every month from the file's first with revenue to its last - one
    inside with no line at all included, its revenue null with its reason.
    Complete by `shared/periods.complete_months` (stage 3's and the
    forecast's history), never past the current, and the compared month only
    when the KPIs compare with it too (`previous_complete`): never drawn
    whole when either definition says otherwise (5A reviews 1 #1, 2 #3)."""
    period = metrics.period
    covered = set(complete_months(period.data_start, period.data_end, month_grain=period.month_grain))
    revenue = {m.period: m.revenue for m in metrics.core.revenue_by_month}
    months: list[MonthRevenue] = []
    month = min(revenue, default=None)
    while month is not None and month <= max(revenue):
        complete = month in covered and month <= period.current and (
            month != period.previous or period.previous_complete)
        months.append(MonthRevenue(period=month, revenue=revenue.get(month),
                                   revenue_reason=None if month in revenue else NO_LINE_IN_MONTH, complete=complete))
        month = shift_month(month, 1)
    return months


def numbers(metrics: MetricsContract, diagnosis: DiagnosisContract, has_customers: bool) -> Numbers:
    period, core, trust = metrics.period, metrics.core, diagnosis.trust
    beside = [n for n in core.notes if not n.always_on]
    return Numbers(
        period=ReportPeriod(current=period.current, previous=period.previous, data_start=period.data_start,
                            data_end=period.data_end, previous_complete=period.previous_complete,
                            previous_incomplete_reason=period.previous_incomplete_reason),
        trust=TrustBadge(verdict=trust.verdict, limitations=list(trust.limitations), checks=[
            TrustCheckView(id=c.id, status=c.status, message=c.message) for c in trust.checks]),
        kpis=_kpis(metrics, beside, has_customers), revenue_by_month=_months(metrics),
        current_note=_current_note(metrics),
        undated_lines=core.undated_lines, undated_lines_reason=core.undated_lines_reason,
        unmeasurable=list(core.unmeasurable), non_product=list(core.non_product),
        outside_revenue=list(core.outside_revenue),
        how_to_read=[view(n) for n in _unique([*core.notes, *diagnosis.notes]) if n.always_on],
        notes=[view(n) for n in beside])


def causes(diagnosis: DiagnosisContract, orders_basis: str) -> Causes:
    labels = _SERIES_LABELS | (_SERIES_LINES_LABELS if orders_basis == "lines" else {})
    return Causes(
        headline=diagnosis.headline,
        hypotheses=[HypothesisView(id=h.id, statement=h.statement, verdict=h.verdict, contribution=h.contribution,
                                   share=h.share, rule=h.rule, evidence=dict(h.evidence))
                    for h in diagnosis.hypotheses],
        not_testable=list(diagnosis.not_testable),
        signals=None if diagnosis.signals is None else [
            SignalView(series=s.series, label=labels[s.series], mode=s.mode, signal=s.signal, value_cur=s.value_cur,
                       center=s.center, lower=s.lower, upper=s.upper, rule=s.rule, mode_fallback=s.mode_fallback,
                       insufficient_reason=s.insufficient_reason, limits_method=s.limits_method)
            for s in diagnosis.signals],
        narration=diagnosis.ai_findings, narration_status="unavailable" if diagnosis.ai_findings is None else "shown",
        notes=[view(n) for n in diagnosis.notes if not n.always_on],
        suggested_classes=dict(diagnosis.suggested_classes))


def confidence_label(confidence: float) -> str:
    return next((label for floor, label in CONFIDENCE_LABELS if confidence >= floor), "low")


def _first_month(metrics: MetricsContract, forecast: ForecastContract) -> tuple[bool, date | None]:
    """Whether the first forecast month is one the file holds lines of (a
    day-grain file ending part-way through it; a month-grain file's
    month-to-date line: 2E-o), and the day a day-grain file ends."""
    points, period, end = forecast.forecast.revenue, metrics.period, metrics.period.data_end
    in_file = bool(points) and points[0].period == f"{end:%Y-%m}"
    part_way = not period.month_grain and end.day < calendar.monthrange(end.year, end.month)[1]
    return in_file, end if in_file and part_way else None


def actions(metrics: MetricsContract, diagnosis: DiagnosisContract, forecast: ForecastContract,
            include_recommendations: bool) -> Actions:
    block = forecast.forecast
    not_always_on = [n for n in _unique([*metrics.core.notes, *diagnosis.notes]) if not n.always_on]
    shown = include_recommendations and forecast.recommendations is not None and forecast.do_not_do is not None
    in_file, until = _first_month(metrics, forecast)
    return Actions(
        forecast=ForecastView(
            method=block.method, months_used=block.months_used, insufficient_history=block.insufficient_history,
            points=list(block.revenue), history_note=block.history_note, season_years=block.season_years,
            season_note=block.season_note,
            notes=revenue_notes(metrics), first_month_in_file=in_file, partial_first_month_until=until),
        recommendations=[RecommendationView(
            priority=r.priority, insight=r.insight, cause=r.cause, action=r.action, expected_impact=r.expected_impact,
            how_to_measure=r.how_to_measure, confidence_label=confidence_label(r.confidence))
            for r in forecast.recommendations or []] if shown else None,
        do_not_do=forecast.do_not_do if shown else None,
        recommendations_status="shown" if shown else "unavailable" if include_recommendations else "switched_off",
        notes=[n.code for n in not_always_on])
