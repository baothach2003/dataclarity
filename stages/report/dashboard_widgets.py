"""The dashboard's chart widgets (docs/DASHBOARD_DESIGN.md section 3; Thach's
D3, D6): each shown only when the file holds its data, each with the size the
order rule reads - an EXISTING money contribution of an earlier file, never a
figure computed for it - and its bars, the earlier files' figures formatted.

Chart type by the data's shape (D6): the months a line; categories sorted
horizontal bars; parts of a whole only for 2 or 3 parts, every one above zero
in each month drawn (a negative part is no part of a whole)."""

from typing import NamedTuple

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import BLANK_LABEL, Breakdown, MetricsContract
from contracts.report import Chart, NoteView
from contracts.report_dashboard import Bar, Widget, WidgetId
from contracts.report_front import Front
from shared.claim_lines import Context, money_terms
from shared.wording import amount, prints_as_zero

MAX_PARTS = 3
_CUSTOMER_IDS = ("C1", "C3", "C2")  # new, came back, stopped buying - the order a shop owner reads them
# The note figures each widget draws (contracts/lines NoteFigure; CLAUDE.md
# 3.3a: a note stands wherever its figure is shown).
_FIGURES: dict[WidgetId, set[str]] = {
    "customers": {"customers", "diagnosis"}, "products": {"products", "diagnosis"},
    "returns": {"returns", "return_rate", "diagnosis"}, "category": {"revenue"}, "breakdown_1": {"revenue"},
    "breakdown_2": {"revenue"}}


def _notes(views: list[NoteView], widget: WidgetId) -> list[str]:
    figures = _FIGURES[widget]
    return list(dict.fromkeys(view.code for view in views if figures & set(view.figures)))


def _bar(label: str, now: float, was: float | None, code: str | None, is_blank: bool = False) -> Bar:
    return Bar(label=label, now=now, was=was, now_text=amount(now, code),
               was_text=None if was is None else amount(was, code), is_blank=is_blank)


def _split_chart(bars: list[Bar]) -> str:
    """Parts of a whole only for very few parts, each above zero (D6)."""
    positive = all(b.now > 0 and (b.was is None or b.was > 0) for b in bars)
    return "parts" if len(bars) <= MAX_PARTS and positive else "bars"


def _sorted(bars: list[Bar]) -> list[Bar]:
    """Largest this month first; the blank bucket last (stage 3's visible bucket)."""
    return sorted(bars, key=lambda b: (b.is_blank, -b.now, b.label))


def _breakdown(widget: WidgetId, split: Breakdown, compared: bool, size: float | None, code: str | None,
               notes: list[str]) -> Widget | None:
    if not split.members:
        return None  # withheld by stage 2, with its reason (CONTRACTS 6): nothing drawn
    bars = _sorted([_bar(m.name, m.revenue_current, m.revenue_previous if compared else None, code, m.is_blank)
                    for m in split.members])
    blank = [f'"{BLANK_LABEL}" is the lines with no value in this column.'] if any(b.is_blank for b in bars) else []
    return Widget(id=widget, kind="chart", chart=_split_chart(bars), placed_by="size" if size is not None else
                  "fallback", size=size, title=f"Sales by {split.column}", column=split.column, bars=bars,
                  caption=blank, notes=notes)


class Drawn(NamedTuple):
    """The chart widgets, the hypotheses each one draws (the tie of D3 reads
    what a widget SHOWS, never what it is about: step 3's review), and why a
    chart the file's columns call for is not drawn (a breakdown stage 2
    withheld - design 5.5: with its reason)."""

    widgets: list[Widget]
    draws: dict[WidgetId, set[str]]
    not_shown: list[str]


# A bridge bar and the hypotheses whose figure it is (the waterfall draws them).
_BAR_DRAWS = {"frequency": {"B1"}, "units_per_order": {"B2"}, "price_per_unit": {"P1", "P2"}, "aov": {"P1", "P2"}}


def chart_widgets(*, metrics: MetricsContract, diagnosis: DiagnosisContract, cleaning: CleaningReportContract,
                  front: Front, charts: list[Chart], notes: list[NoteView], code: str | None, compared: bool,
                  has_returns: bool) -> Drawn:
    found: list[Widget] = []
    draws: dict[WidgetId, set[str]] = {}
    not_shown: list[str] = []
    tree = diagnosis.tree
    bridge = tree.lever.bridge if tree is not None else None
    hypotheses = {h.id: h for h in diagnosis.hypotheses}

    def contribution(*ids: str) -> float:
        return max((abs(hypotheses[i].contribution or 0.0) if i in hypotheses else 0.0 for i in ids), default=0.0)

    trend = next((c for c in charts if c.id == "revenue_trend"), None)
    if trend is not None and trend.series and sum(y is not None for y in trend.series[0].y) >= 2:
        change = (bridge.shown_change if bridge is not None else metrics.core.revenue_change) if compared else None
        found.append(Widget(id="trend", kind="chart", chart="line", placed_by="fallback" if change is None else "size",
                            size=None if change is None else abs(change), title=front.chart_title,
                            caption=list(front.chart_note), notes=list(trend.notes)))
        # The year before is on the line only when the chart draws both of its months whole (T2's pair).
        drawn = {x for x, y in zip(trend.series[0].x, trend.series[0].y) if y is not None}
        year_ago = (diagnosis.frame.year_ago_previous, diagnosis.frame.year_ago_current)
        draws["trend"] = {"T2"} if None not in year_ago and set(year_ago) <= drawn else set()
    if compared and front.waterfall is not None:
        found.append(Widget(id="waterfall", kind="chart", chart="waterfall", placed_by="size",
                            size=max(abs(bar.shown) for bar in front.waterfall.bars),
                            title="Where the change came from", notes=list(front.notes.change)))
        draws["waterfall"] = set().union(*(_BAR_DRAWS.get(bar.factor, set()) for bar in front.waterfall.bars))
    ctx = Context(metrics=metrics, tree=tree, bridge=bridge, year_ago=diagnosis.year_ago, code=code)
    if compared and "customer" in cleaning.column_mapping.values() and tree is not None and tree.customers is not None:
        terms = {i: t for i in _CUSTOMER_IDS if (t := money_terms(i, ctx)) is not None}
        if any(not prints_as_zero(v) for _, now, was in terms.values() for v in (now, was)):
            # Sized and tied by the groups it draws only (a lapsed term that is no loss is not drawn: review 3 #8).
            found.append(Widget(id="customers", kind="chart", chart="bars", placed_by="size",
                                size=contribution(*terms), title="Customers: new, back after a break, "
                                "stopped buying", bars=[_bar(s, now, was, code) for s, now, was in terms.values()],
                                notes=_notes(notes, "customers")))
            draws["customers"] = set(terms)
    localization = diagnosis.localization
    dims = {d.name: d for d in localization.dimensions} if localization is not None else {}
    # No products widget (Thach's stop rule, 2026-10-14): its first form ("moved most", stage 3's members)
    # was false on the Kaggle file; its fix (stage 2's top products) still named a suggested charge, DOTCOM
    # POSTAGE, as Online Retail II's top product without its "suggested, not confirmed" mark - a fabrication
    # on a demo file found by the scoped review, so the element is not shown. The appendix keeps the tables.
    categories = metrics.by_dimension.category
    if len(categories) >= 2:
        size = (max(abs(m.delta) for m in dims["category"].members) if compared and "category" in dims
                and dims["category"].members else None)
        bars = _sorted([_bar(c.name, c.revenue_current, c.revenue_previous if compared else None, code)
                        for c in categories])
        # Never parts of a whole: stage 2's categories leave the lines with no category out (review 3 #4).
        found.append(Widget(id="category", kind="chart", chart="bars", placed_by="size" if size is not None
                            else "fallback", size=size, title="Sales by category", bars=bars,
                            caption=["Each bar is one category's sales; lines with no category are not in this "
                                     "chart."], notes=_notes(notes, "category")))
    for index, split in enumerate(metrics.by_dimension.breakdowns, start=1):
        widget_id: WidgetId = "breakdown_1" if index == 1 else "breakdown_2"
        changes = [abs(m.change) for m in split.members if m.change is not None]
        widget = _breakdown(widget_id, split, compared, max(changes) if compared and changes else None, code,
                            _notes(notes, widget_id))
        if widget is not None:
            found.append(widget)
        elif split.withheld_reason is not None:
            not_shown.append(f'Sales by "{split.column}" are not shown: {split.withheld_reason}.')
    returns = money_terms("P3", ctx) if compared and has_returns and tree is not None else None
    if returns is not None:
        subject, now, was = returns
        found.append(Widget(id="returns", kind="chart", chart="bars", placed_by="size", size=contribution("P3"),
                            title=subject, bars=[_bar(subject, now, was, code)], notes=_notes(notes, "returns")))
        draws["returns"] = {"P3"}
    return Drawn(found, draws, not_shown)
