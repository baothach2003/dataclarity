"""report.html's dashboard (2.10; docs/DASHBOARD_DESIGN.md sections 1-3): the
KPI tiles, the caution lines under them, then report.json's widgets in the
order it gives - the charts drawn from its figures, the text widgets the
front section's own sentences (one copy: html_front's renderers). This module
only lays it out; every string is escaped (SPECS SEC-3)."""

from contracts.report import ReportContract
from contracts.report_dashboard import Bar, Dashboard, Tile, Widget
from contracts.report_front import Front
from stages.report.html_front import cannot_know_html, change_html, checked_html, next_month_html, \
    next_steps_html, read_with
from stages.report.html_parts import esc, para
from stages.report.html_bars import bar_chart, parts_chart
from stages.report.html_svg import sales_chart

# The dashboard's layout in the report's own tokens (_FRONT_STYLE's): tiles in
# a row that wraps, the widgets in a grid of one column on a phone; the parts'
# colours the accent, the total's grey and a light accent (no new hue).
DASHBOARD_STYLE = """.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:12px;
margin-top:18px}.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
min-width:0}.tl{font-size:.85rem;color:var(--ink2)}.tv{font-size:1.45rem;font-weight:600;line-height:1.3;
overflow-wrap:anywhere}.tile .num{white-space:normal}.tc{font-size:.8rem;color:var(--ink2)}.arrow{font-size:.7rem}
.widgets{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:0 18px;
align-items:start}.widgets .card{min-width:0}a{color:var(--accent)}
.hbars,.hparts{list-style:none;margin:0;padding:0}.hb-row,.hp-row{display:grid;grid-template-columns:1fr auto;
gap:2px 10px;padding:5px 0}.hb-label{font-size:.85rem;overflow-wrap:anywhere;min-width:0}.hb-val{font-size:.85rem;
font-weight:600;text-align:right;white-space:nowrap}.hb-was{font-weight:400;color:var(--ink2)}
.hb-track,.hp-track{grid-column:1/-1;position:relative;height:12px;display:block}.hp-track{display:flex;height:20px;
gap:2px}.hb-bar{position:absolute;top:0;height:9px;border-radius:3px}.hb-marker{top:10px;height:3px}
.hb-zero{position:absolute;top:-2px;bottom:-2px;width:1px;background:var(--ink2)}.hb-bar.now,.hb-bar.up{background:var(--up)}
.hb-bar.down{background:var(--down)}.hb-bar.was{background:var(--tot)}.hb-bar.flat{background:var(--ink2)}
.hp-part{display:block;height:100%;border-radius:3px}.p0{background:var(--up)}.p1{background:var(--tot)}
.p2{background:var(--up);opacity:.45}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
@media (max-width:420px){.hb-val{white-space:normal}}"""
_ARROWS = {"up": "&#9650;", "down": "&#9660;", "same": "&#9679;"}
_DIRECTION_WORDS = {"up": "higher than", "down": "lower than", "same": "the same as"}


def _tile(tile: Tile, previous: str) -> str:
    parts = [f'<div class="tile"><div class="tl">{esc(tile.label)}</div>']
    parts.append(f'<div class="tv num">{esc(tile.now)}</div>' if tile.now is not None else "")
    arrow = (f'<span class="arrow" role="img" aria-label="{_DIRECTION_WORDS[tile.direction]} last month">'
             f"{_ARROWS[tile.direction]}</span> ") if tile.direction else ""
    if tile.change is not None:
        parts.append(f'<div class="tc">{arrow}{esc(tile.change)}</div>')
    elif tile.was is not None:
        parts.append(f'<div class="tc">{arrow}was {esc(tile.was)} in {esc(previous)}</div>')
    if tile.reason:
        parts.append(f'<div class="tc">{esc(tile.reason)}</div>')
    parts.append(read_with(tile.notes))
    parts.append("</div>")
    return "".join(parts)


def _tiles(dashboard: Dashboard, previous: str) -> str:
    body = "".join(_tile(tile, previous) for tile in dashboard.tiles)
    lines = "".join(para(line, "small") for line in dashboard.not_shown)
    caution = "".join(para(line, "caution") for line in dashboard.caution)
    return f'<section id="tiles" class="tiles-row"><div class="tiles">{body}</div>{lines}{caution}</section>'


def _summary(front: Front) -> str:
    parts = [para(line) for line in front.summary]
    # Shown once: beside a month not compared, the data checks line stands here
    # (with no checklist); a caution's lines stand under the tiles.
    if front.state == "not_compared" and not front.caution:
        parts += [para(line, "small") for line in front.data_checks]
    if front.waterfall_note:
        parts.append(para(front.waterfall_note, "small"))
    parts.append(para(front.sales_note, "small"))
    parts.append(read_with(front.notes.summary))
    return "".join(parts)


def _bars(widget: Widget, code: str | None) -> str:
    if widget.chart == "parts":
        return parts_chart(widget.bars, widget.title or "", code)
    return bar_chart(widget.bars, widget.title or "", code, diverging=widget.chart == "diverging")


def _legend(bars: list[Bar]) -> str:
    return "".join(f'<p class="small"><span class="sw p{i}"></span>{esc(b.label)}: {esc(b.now_text)}'
                   f'{f" (was {esc(b.was_text)})" if b.was_text else ""}</p>' for i, b in enumerate(bars))


# Each widget's section id: the front's own ids where it had the part (the
# links and anchors a reader or a test knows stay where they were).
SECTION_IDS = {"summary": "summary", "waterfall": "change", "checklist": "checked", "next_steps": "next-steps",
               "next_month": "next-month", "cannot_know": "cannot-know", "trend": "sales-by-month",
               "customers": "customers", "products": "products", "category": "category",
               "breakdown_1": "breakdown-1", "breakdown_2": "breakdown-2", "returns": "returns"}
_TEXT_TITLES = {"summary": "In short", "checklist": "What was checked", "next_steps": "What to do next",
                "next_month": "Next month", "cannot_know": "What this report cannot know"}


def _widget(report: ReportContract, front: Front, widget: Widget, code: str | None) -> str:
    title = widget.title or _TEXT_TITLES[widget.id]
    head = f'<section id="{SECTION_IDS[widget.id]}" class="card widget {esc(widget.kind)}"><h2>{esc(title)}</h2>'
    if widget.id == "summary":
        body = _summary(front)
    elif widget.id == "checklist":
        body = checked_html(front)
    elif widget.id == "next_steps":
        body = next_steps_html(front)
    elif widget.id == "next_month":
        body = next_month_html(front)
    elif widget.id == "cannot_know":
        body = cannot_know_html(front)
    elif widget.id == "trend":
        trend = next(c for c in report.charts if c.id == "revenue_trend")
        body = sales_chart(trend, title, code)
    elif widget.id == "waterfall":
        body = change_html(front, code)
    else:
        body = _bars(widget, code) + (_legend(widget.bars) if widget.chart == "parts" else "")
    body += "".join(para(line, "small") for line in widget.caption)
    if widget.kind == "chart" and widget.id != "waterfall":
        body += read_with(widget.notes)
    return f"{head}{body}</section>"


def dashboard_html(report: ReportContract, dashboard: Dashboard, front: Front, previous: str) -> str:
    code = report.currency.code if report.currency is not None else None
    widgets = "".join(_widget(report, front, widget, code) for widget in dashboard.widgets)
    return f'{_tiles(dashboard, previous)}<div class="widgets">{widgets}</div>'
