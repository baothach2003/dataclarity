"""report.json's front section (2.9; the report redesign, step 3): the one
copy of the wording a shop owner reads first, which report.html prints and
the page will (docs/REPORT_REDESIGN.md section 1). Built from the layers
already chosen (layers.py) and the earlier files; nothing is computed.

The states (the standing rules): a blocked diagnosis replaces sections 1-4
with one sentence, the check worded by its id and status (Q37); an
incomplete previous month, or this month's figures withheld, shows this month
alone - no change, no bar, no checklist; a caution opens section 1. A note
stands beside every section showing a figure it names (Q35)."""

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.lines import NoteFigure
from contracts.metrics import MetricsContract
from contracts.report import Actions, Causes, Chart, NoteView, Numbers
from contracts.report_front import Front, FrontNotes, PartialMonth, RowsLeftOut
from shared.claim_lines import Context
from shared.wording import amount, month_name
from stages.report.front_checklist import checklist
from stages.report.front_rest import cannot_know, chart_note, next_month, next_steps
from stages.report.front_summary import (BRIDGE_WITHHELD, NOT_DRAWN, NOT_PROFIT, check_lines, data_checks, sentence_a,
                                         sentence_b, sentence_c, waterfall)

CHART_TITLE = "Sales by month (before any costs)"
# The figures a check's line prints, by the notes' vocabulary (contracts/lines):
# a section naming the check shows them, and so their notes (Q35; the review:
# the summary's sentence C printed orders without their note).
_PRINTS: dict[str, set[NoteFigure]] = {
    "B1": {"orders", "customers"}, "B2": {"units", "orders"}, "C1": {"customers"}, "C2": {"customers"},
    "C3": {"customers"}, "P3": {"returns"}, "P4": {"discounts", "other_deductions"}, "R1": {"products"},
    "R2": {"products"}, "R3": {"products"}}


def _shows(front_ids: list[str], rule: int | None) -> dict[str, set[NoteFigure]]:
    """The figures each section shows. Sentences B and C, and every checklist
    line, read the diagnosis."""
    printed: set[NoteFigure] = set().union(*(_PRINTS.get(i, set()) for i in front_ids))
    return {"summary": {"revenue", "diagnosis"} | printed | ({"orders", "aov"} if rule == 4 else set()),
            "change": {"revenue", "orders", "customers", "aov", "units"},
            "checked": {"diagnosis"} | printed}


def _notes(views: list[NoteView], forecast_notes: list[str], shows: dict[str, set[NoteFigure]]) -> FrontNotes:
    """Each note beside every section showing a figure it names; next month
    reads the forecast's own list (revenue's notes: CONTRACTS 11)."""
    def beside(section: str) -> list[str]:
        # Once each: metrics.json and diagnosis.json carry the same codes.
        return list(dict.fromkeys(view.code for view in views if shows.get(section, set()) & set(view.figures)))
    return FrontNotes(summary=beside("summary"), change=beside("change"), checked=beside("checked"),
                      next_month=list(forecast_notes), next_steps=beside("next_steps"))


def _gaps(trend: Chart | None, numbers: Numbers) -> list[str]:
    """Why the line breaks inside the chart, by each month's own field: no
    sales in the file (a closed month or missing data - CLAUDE.md 3.3a), or a
    month the file does not cover whole."""
    if trend is None or not trend.series or not trend.series[0].x:
        return []
    revenue = {m.period: m.revenue for m in numbers.revenue_by_month}
    found: list[str] = []
    run: list[str] = []
    for month, value in [*zip(trend.series[0].x, trend.series[0].y), (None, 0.0)]:
        if month is not None and value is None and revenue.get(month) is None:
            run.append(month)
            continue
        if run:
            span = month_name(run[0]) if len(run) == 1 else f"{month_name(run[0])} to {month_name(run[-1])}"
            verb = "has" if len(run) == 1 else "have"
            found.append(f"{span} {verb} no sales in the file - a closed month or missing data, which the file cannot "
                         "tell apart - so the line breaks there.")
            run = []
        if month is not None and value is None and revenue.get(month) is not None:
            found.append(f"{month_name(month)} is not drawn: the file does not cover it whole.")
    return found


def _not_compared(numbers: Numbers, code: str | None) -> list[str]:
    """This month alone, and why there is no comparison, in plain words (the
    reasons as stage 2 and stage 5 write them stay in the appendix)."""
    period, revenue = numbers.period, numbers.kpis[0]
    current, previous = month_name(period.current), month_name(period.previous)
    if revenue.current is None:
        return [f"Sales in {current} cannot be shown: no sale dated in {current} can be counted - the technical "
                "details say why."]
    if not period.previous_complete:
        why = f"the file does not cover {previous} whole"
    else:
        why = f"no sale dated in {previous} can be counted - the technical details say why"
    return [f"Sales in {current} were {amount(revenue.current, code)}.",
            f"They are not compared with {previous}: {why}."]


def build_front(*, metrics: MetricsContract, diagnosis: DiagnosisContract, forecast: ForecastContract,
                cleaning: CleaningReportContract, numbers: Numbers, causes: Causes, actions: Actions,
                charts: list[Chart], partial: list[PartialMonth], left_out: list[RowsLeftOut], code: str | None,
                ) -> Front:
    tree = diagnosis.tree
    bridge = tree.lever.bridge if tree is not None else None
    ctx = Context(metrics=metrics, tree=tree, bridge=bridge, year_ago=diagnosis.year_ago, code=code)
    sales_note = NOT_PROFIT if code else f"{NOT_PROFIT} Amounts are in your file's currency."
    trend = next((c for c in charts if c.id == "revenue_trend"), None)
    drawn = any(month.complete and month.revenue is not None for month in numbers.revenue_by_month)
    period = metrics.period
    views = [*numbers.notes, *causes.notes]
    common = {"sales_note": sales_note, "chart_title": CHART_TITLE,
              "next_month": next_month(actions.forecast, partial, code),
              "cannot_know": cannot_know(diagnosis.not_testable, cleaning, numbers, left_out)}
    trust = diagnosis.trust
    if trust.verdict == "blocked":
        blocked = " ".join(check_lines(trust.checks, "blocked", period)) or "the data checks did not pass."
        # No chart either: sections 1-4 are one sentence (the review).
        return Front(state="blocked", caution=[], summary=[f"The data cannot support conclusions: {blocked}"],
                     chart_note=[], waterfall=None, waterfall_note=None, checklist=[], data_checks=[],
                     next_steps=None, notes=_notes(views, actions.forecast.notes, _shows([], None)), **common)
    checks = data_checks(trust.checks, period)
    # Each caution's own line only. The opener "Some of this month's data may
    # be missing or wrong" left the front (Thach's safety valve, 2026-10-06:
    # it said "this month" beside a caution on the previous month); the
    # appendix keeps the trust verdict and every check's message.
    caution = check_lines(trust.checks, "caution", period) if trust.verdict == "caution" else []
    chart_lines = [*chart_note(partial), *_gaps(trend, numbers)] if drawn else []
    revenue = numbers.kpis[0]
    if not numbers.period.previous_complete or revenue.current is None or revenue.previous is None:
        shows = _shows([], None) | {"summary": {"revenue"}}  # this month's sales alone
        return Front(state="not_compared", caution=caution, summary=_not_compared(numbers, code),
                     chart_note=chart_lines, waterfall=None, waterfall_note=None, checklist=[], data_checks=checks,
                     next_steps=None, notes=_notes(views, actions.forecast.notes, shows), **common)
    b, inside, decimals = sentence_b(diagnosis.headline.movement)
    a, c = sentence_a(metrics, bridge, code, decimals), sentence_c(diagnosis, ctx)
    summary = ([b, a] if inside and b else [a, b] if b else [a]) + c
    lever = tree.lever if tree is not None else None
    unit = "line" if ctx.lines_basis else "order"
    groups = checklist(diagnosis, causes.hypotheses, ctx)
    headline = diagnosis.headline
    named = (headline.named or ([headline.hypothesis_id] if headline.hypothesis_id else [])) if c else []
    shows = _shows(list(named), headline.rule if c else None)
    shows["checked"] |= _shows([h.id for h in diagnosis.hypotheses], None)["checked"] if groups else set()
    steps = next_steps(forecast, diagnosis.headline.rule)
    if steps.items and forecast.actions:
        # The facts listed are the checklist's lines: the same figures, notes.
        shows["next_steps"] = _shows([a.hypothesis_id for a in forecast.actions], None)["checked"]
    return Front(
        state="compared", caution=caution, summary=summary, chart_note=chart_lines,
        waterfall=waterfall(bridge, metrics, code) if bridge is not None else None,
        waterfall_note=None if bridge is not None else NOT_DRAWN.format(
            why=BRIDGE_WITHHELD[lever.bridge_withheld if lever is not None else None].format(unit=unit)),
        checklist=groups, data_checks=checks, next_steps=steps,
        notes=_notes(views, actions.forecast.notes, shows), **common)
