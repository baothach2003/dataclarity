"""report.json's dashboard block (2.10; docs/DASHBOARD_DESIGN.md sections 2-4):
the KPI tiles and the widgets, in the order code decides
(`contracts.report_dashboard.order_widgets`). Built from the layers and the
front section already chosen and from the earlier files; every figure is a
field of one of them, formatted - nothing is computed (CONTRACTS 11). The
widgets' charts: `dashboard_widgets.py`; the line under the tiles, the chips
and the bands (2.11, Thach's layout): `dashboard_bands.py`."""

from contracts.cleaning import CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import MetricsContract
from contracts.report import Chart, ForecastView, HypothesisView, Kpi, NoteView, Numbers
from contracts.report_dashboard import BLOCKED_WIDGETS, TIED, Dashboard, Tile, Widget, WidgetId, order_widgets
from contracts.report_front import Front
from shared.wording import amount, count, month_name, prints_as_zero
from stages.report import dashboard_bands
from stages.report.dashboard_widgets import chart_widgets
from stages.report.front_summary import sales_change

# A ratio is printed as the appendix prints it (html_parts.ratio): it is not a
# share, so never a percentage (CONTRACTS 6: return_rate).
RATIO_DECIMALS = 3
NOT_COMPARED_BLOCKED = "Not compared: the data checks did not pass - see Technical details."


def _ratio(value: float) -> str:
    return f"{value:.{RATIO_DECIMALS}f}"


def _direction(now: str, was: str) -> str:
    """From the two PRINTED figures: equal as printed is "same" (Q58's rule)."""
    a, b = (float(text.split(" ")[-1].replace(",", "")) for text in (now, was))
    return "up" if a > b else "down" if a < b else "same"


def _not_compared_why(numbers: Numbers) -> str:
    """The front's own reasons, in its words (front.py `_not_compared`)."""
    period, revenue = numbers.period, numbers.kpis[0]
    previous = month_name(period.previous)
    if not period.previous_complete:
        return f"Not compared with {previous}: the file does not cover {previous} whole."
    if revenue.previous is None:
        return f"Not compared with {previous}: no sale dated in {previous} can be counted - see Technical details."
    return f"Not compared with {previous}."


def _sales(numbers: Numbers, front: Front, metrics: MetricsContract, diagnosis: DiagnosisContract,
           code: str | None) -> Tile:
    kpi = numbers.kpis[0]
    current = month_name(numbers.period.current)
    if kpi.current is None:
        return Tile(id="sales", label="Sales", unit="money", now=None, now_value=None, was=None, change=None,
                    direction=None, reason=f"Not shown: no sale dated in {current} can be counted - see Technical "
                                           "details.", notes=list(kpi.notes))
    if front.state == "compared":
        bridge = diagnosis.tree.lever.bridge if diagnosis.tree is not None else None
        shown, value, change, change_value = sales_change(metrics, bridge, code, diagnosis.headline.movement)
        direction = None if change_value is None else (
            "same" if prints_as_zero(change_value) else "up" if change_value > 0 else "down")
        return Tile(id="sales", label="Sales", unit="money", now=shown, now_value=value, was=None, change=change,
                    direction=direction, reason=None, notes=list(kpi.notes))
    reason = NOT_COMPARED_BLOCKED if front.state == "blocked" else _not_compared_why(numbers)
    return Tile(id="sales", label="Sales", unit="money", now=amount(kpi.current, code), now_value=kpi.current,
                was=None, change=None, direction=None, reason=reason, notes=list(kpi.notes))


def _kpi_tile(tile_id: str, label: str, kpi: Kpi, compared: bool, fmt) -> Tile:
    now = fmt(kpi.current)
    was = fmt(kpi.previous) if compared and kpi.previous is not None else None
    return Tile(id=tile_id, label=label, unit=kpi.unit, now=now, now_value=kpi.current, was=was,
                was_value=None if was is None else kpi.previous, change=None,
                direction=None if was is None else _direction(now, was), reason=None, notes=list(kpi.notes))


def _has_returns(metrics: MetricsContract, compared: bool) -> bool:
    identity = metrics.core.identity
    return not prints_as_zero(identity.current.returns) or (compared and not prints_as_zero(identity.previous.returns))


def tiles(numbers: Numbers, front: Front, metrics: MetricsContract, diagnosis: DiagnosisContract,
          cleaning: CleaningReportContract, code: str | None) -> tuple[list[Tile], list[str]]:
    """D2 (design section 2): sales always; orders or lines; the average
    order or line value; customers who placed an order (the bridge's count:
    Thach's Q4) with a customer column; the return rate with returns. A tile
    with no figure is not shown - its reason under the row."""
    found = [_sales(numbers, front, metrics, diagnosis, code)]
    if numbers.kpis[0].current is None:
        return found, []  # the month's figures are withheld whole: the sales tile says why
    kpis = {kpi.id: kpi for kpi in numbers.kpis}
    compared = front.state == "compared"
    lines = metrics.core.orders_basis == "lines"
    not_shown: list[str] = []
    found.append(_kpi_tile("orders", "Lines" if lines else "Orders", kpis["orders"], compared, count))
    aov_label = "Average line value" if lines else "Average order value"
    if kpis["aov"].current is not None:
        found.append(_kpi_tile("aov", aov_label, kpis["aov"], compared, lambda value: amount(value, code)))
    else:
        not_shown.append(f"{aov_label} is not shown this month - see Technical details for why.")
    who = "Customers who bought" if lines else "Customers who placed an order"
    if "customer" in cleaning.column_mapping.values():
        bridge = diagnosis.tree.lever.bridge if diagnosis.tree is not None else None
        bar = next((b for b in bridge.bars if b.factor == "customers"), None) if bridge is not None else None
        if compared and bar is not None:
            now, was = count(bar.value_cur), count(bar.value_prev)
            found.append(Tile(id="customers", label=who, unit="count", now=now, now_value=bar.value_cur, was=was,
                              was_value=bar.value_prev,
                              change=None, direction=_direction(now, was), reason=None,
                              notes=list(kpis["active_customers"].notes)))
        elif compared:
            not_shown.append(f"{who} are not shown: this month's split of the change has no count of them.")
        else:
            not_shown.append(f"{who} are not shown: this month is not compared with the last.")
    if _has_returns(metrics, compared):
        label = "Return lines per sale line" if lines else "Orders with a return, per order sold"
        if kpis["return_rate"].current is not None:
            found.append(_kpi_tile("return_rate", label, kpis["return_rate"], compared, _ratio))
        else:
            not_shown.append(f"{label} is not shown this month - see Technical details for why.")
    return found, not_shown


def _tied(diagnosis: DiagnosisContract, draws: dict[WidgetId, set[str]], compared: bool) -> WidgetId | None:
    """The widget tied to stage 3's named cause (D3): rules 5 and 6 by
    `headline.named` - its first id whose widget DRAWS it (step 3's review: a
    widget about customers that does not draw the named group is no tie) - and
    rule 4 the waterfall (it draws the offsetting pair). Only beside a
    comparison."""
    headline = diagnosis.headline
    if not compared:
        return None
    if headline.rule == 4:
        return "waterfall" if "waterfall" in draws else None
    if headline.rule in (5, 6):
        named = headline.named or ([headline.hypothesis_id] if headline.hypothesis_id else [])
        return next((TIED[i] for i in named if i in TIED and i in draws.get(TIED[i], set())), None)
    return None


def build_dashboard(*, metrics: MetricsContract, diagnosis: DiagnosisContract, cleaning: CleaningReportContract,
                    numbers: Numbers, front: Front, charts: list[Chart], notes: list[NoteView],
                    code: str | None, views: list[HypothesisView], forecast: ForecastView) -> Dashboard:
    found, not_shown = tiles(numbers, front, metrics, diagnosis, cleaning, code)
    bridge = diagnosis.tree.lever.bridge if diagnosis.tree is not None else None
    bands = {"headline": dashboard_bands.headline(metrics=metrics, diagnosis=diagnosis, bridge=bridge, front=front,
                                                  numbers=numbers, code=code),
             "checked": dashboard_bands.checked(front=front, diagnosis=diagnosis, views=views,
                                                lines_basis=metrics.core.orders_basis == "lines"),
             "next_month": dashboard_bands.next_month(view=forecast, front=front, code=code),
             "next_steps": dashboard_bands.next_steps(front),
             "checked_notes": list(front.notes.checked), "next_steps_notes": list(front.notes.next_steps)}
    if front.state == "blocked":
        widgets = [Widget(id=w, kind="text", chart=None, placed_by="fallback", title=None) for w in BLOCKED_WIDGETS]
        return Dashboard(state="blocked", tiles=found, not_shown=not_shown, caution=[], widgets=widgets, **bands)
    compared = front.state == "compared"
    drawn, draws, widget_lines = chart_widgets(metrics=metrics, diagnosis=diagnosis, cleaning=cleaning, front=front,
                                               charts=charts, notes=notes, code=code, compared=compared,
                                               has_returns=_has_returns(metrics, compared))
    texts: list[WidgetId] = ["summary", "next_month", "cannot_know"]
    if compared:
        texts += (["checklist"] if front.checklist else []) + (["next_steps"] if front.next_steps else [])
    by_id: dict[WidgetId, Widget] = {w.id: w for w in drawn}
    sizes: dict[WidgetId, float | None] = {w.id: w.size for w in drawn} | dict.fromkeys(texts)
    tied = _tied(diagnosis, draws, compared)
    ordered = []
    for widget_id in order_widgets(sizes, tied):
        if widget_id in by_id:
            widget = by_id[widget_id]
            placed = "named" if widget_id == tied else "size" if widget.size is not None else "fallback"
            ordered.append(Widget.model_validate(widget.model_dump() | {"placed_by": placed}))
        else:
            ordered.append(Widget(id=widget_id, kind="text", chart=None, placed_by="fallback", title=None))
    return Dashboard(state=front.state, tiles=found, not_shown=not_shown + widget_lines, caution=list(front.caution),
                     widgets=ordered, **bands)


__all__ = ["build_dashboard", "tiles"]
