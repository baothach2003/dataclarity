"""report.html's dashboard (2.10; 2.11 Thach's layout - docs/DASHBOARD_DESIGN.md
sections 1-3 and 10): pictures and figures, almost no text. Row 1 the KPI
tiles (label, figure, arrow, change); row 2 one short line; row 3 the chart
cards in report.json's order; row 4 full-width bands - next month, the
checked chips, the next step. A note stands where its figure is, as a marker
that opens its sentence (CLAUDE.md 3.3a as amended): a `details` element, so
it opens by keyboard and needs no script. Every long text is printed whole
in Technical details ("The dashboard in words": `words_html`). This module
only lays it out; every string is escaped (SPECS SEC-3)."""

from contracts.report import ReportContract
from contracts.report_dashboard import Chip, Dashboard, NextMonthBand, Tile, Widget
from contracts.report_front import Front
from stages.report.html_front import cannot_know_html, checked_html, next_month_html, next_steps_html, read_with
from stages.report.html_parts import esc, para, table
from stages.report.html_bars import bar_chart, parts_chart
from stages.report.html_svg import sales_chart, waterfall_chart

# The dashboard's layout in the report's own tokens (_FRONT_STYLE's): tiles in
# a row that wraps, the chart cards in a grid of one column on a phone, the
# bands full width at every size; the parts' colours the accent, the total's
# grey and a light accent (no new hue).
DASHBOARD_STYLE = """.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:12px;
margin-top:18px}.tile:has(details.mk[open]){grid-column:1/-1}.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 14px;
min-width:0}.tl{font-size:.85rem;color:var(--ink2)}.tv{font-size:1.45rem;font-weight:600;line-height:1.3;
overflow-wrap:anywhere}.tile .num{white-space:normal}.tc{font-size:.8rem;color:var(--ink2)}.arrow{font-size:.7rem}
.headline{display:flex;flex-wrap:wrap;align-items:flex-start;gap:4px 8px;margin:16px 0 4px;font-size:1.05rem;
font-weight:600}.headline>span{min-width:0;overflow-wrap:anywhere}
.widgets{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:0 18px;
align-items:start}.widgets .card{min-width:0}.whead{display:flex;flex-wrap:wrap;align-items:flex-start;gap:8px}
.whead h2{flex:1;min-width:0}a{color:var(--accent)}
.band{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px 16px;margin-top:14px;
display:flex;flex-wrap:wrap;align-items:baseline;gap:6px 14px}.band h2{font-size:1rem;margin:0}
.band .bandline{margin:0;font-weight:600;overflow-wrap:anywhere;min-width:0}.band ul{margin:0;padding-left:18px}
.chips{display:flex;flex-wrap:wrap;gap:6px;list-style:none;margin:0;padding:0}.chip{border:1px solid var(--line);
border-radius:999px;padding:2px 10px;font-size:.85rem;white-space:nowrap}.chip .cs{color:var(--ink2)}
.chip.st-checked{color:var(--ink2)}
details.mk{display:inline-block;vertical-align:top}details.mk[open]{display:block;flex-basis:100%}
.mk>summary{list-style:none;cursor:pointer;display:inline-block;width:24px;height:24px;line-height:24px;
text-align:center;border:1px solid var(--line);border-radius:50%;font-size:.8rem;font-weight:600;color:var(--ink2)}
.mk>summary::-webkit-details-marker{display:none}.mk-panel{margin-top:6px;padding:8px 10px;border-left:3px solid
var(--line);font-size:.85rem;font-weight:400}.mk-panel p{margin:0 0 6px}
.visually-hidden{position:absolute;width:1px;height:1px;margin:-1px;overflow:hidden;clip:rect(0 0 0 0);
white-space:nowrap;border:0}
.hbars,.hparts,.legend{list-style:none;margin:0;padding:0}.hb-row,.hp-row{display:grid;grid-template-columns:1fr auto;
gap:2px 10px;padding:5px 0}.hb-label{font-size:.85rem;overflow-wrap:anywhere;min-width:0}.hb-val{font-size:.85rem;
font-weight:600;text-align:right;white-space:nowrap}.hb-was{font-weight:400;color:var(--ink2)}
.hb-track,.hp-track{grid-column:1/-1;position:relative;height:12px;display:block}.hp-track{display:flex;height:20px;
gap:2px}.hb-bar{position:absolute;top:0;height:9px;border-radius:3px}.hb-marker{top:10px;height:3px}
.hb-zero{position:absolute;top:-2px;bottom:-2px;width:1px;background:var(--ink2)}.hb-bar.now,.hb-bar.up{background:var(--up)}
.hb-bar.down{background:var(--down)}.hb-bar.was{background:var(--tot)}.hb-bar.flat{background:var(--ink2)}
.hp-part{display:block;height:100%;border-radius:3px}.p0{background:var(--up)}.p1{background:var(--tot)}
.p2{background:var(--up);opacity:.45}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px}
.legend li{font-size:.85rem}#dashboard-words h3{margin-top:14px}
@media (max-width:420px){.hb-val{white-space:normal}.chip{white-space:normal}}"""
_ARROWS = {"up": "&#9650;", "down": "&#9660;", "same": "&#9679;"}
_DIRECTION_WORDS = {"up": "higher than", "down": "lower than", "same": "the same as"}
# A chip's mark and words: the check mark for "checked, not the reason"; a status word on every other.
_CHIP_MARKS = {"checked": "&#10003;", "matches": "&#9679;", "moved": "&#8597;", "other way": "&#8644;",
               "can't tell": "?", "caution": "!"}


def marker(about: str, codes: list[str], asides: list[str], texts: dict[str, str]) -> str:
    """A note where its figure is (CLAUDE.md 3.3a as amended): "i", named for
    a screen reader, opening the sentences behind it - the element's own
    lines (`asides`), then each note's sentence by its code."""
    if not codes and not asides:
        return ""
    body = "".join(para(line) for line in asides)
    body += "".join(f'<p><strong>{esc(code.replace("_", " "))}.</strong> {esc(texts[code])}</p>' for code in codes)
    return (f'<details class="mk" data-notes="{esc(" ".join(codes))}"><summary aria-label="About {esc(about)}">'
            f'i</summary><div class="mk-panel">{body}</div></details>')


def _tile(tile: Tile, texts: dict[str, str]) -> str:
    parts = [f'<div class="tile"><div class="tl">{esc(tile.label)}</div>']
    # A figure, or the two words "not shown": its reason stands behind the marker.
    parts.append(f'<div class="tv num">{esc(tile.now)}</div>' if tile.now is not None else '<div class="tv">not shown</div>')
    arrow = (f'<span class="arrow" role="img" aria-label="{_DIRECTION_WORDS[tile.direction]} last month">'
             f"{_ARROWS[tile.direction]}</span> ") if tile.direction else ""
    if tile.change is not None:
        parts.append(f'<div class="tc">{arrow}{esc(tile.change)}</div>')
    elif tile.was is not None:
        parts.append(f'<div class="tc">{arrow}was {esc(tile.was)}</div>')
    parts.append(marker(tile.label, tile.notes, [tile.reason] if tile.reason else [], texts))
    parts.append("</div>")
    return "".join(parts)


def _bars(widget: Widget, code: str | None) -> str:
    if widget.chart == "parts":
        legend = "".join(f'<li><span class="sw p{i}"></span>{esc(b.label)}: {esc(b.now_text)}'
                         f'{f" (was {esc(b.was_text)})" if b.was_text else ""}</li>' for i, b in enumerate(widget.bars))
        return parts_chart(widget.bars, widget.title or "", code) + f'<ul class="legend">{legend}</ul>'
    return bar_chart(widget.bars, widget.title or "", code, diverging=widget.chart == "diverging")


# Each chart card's section id: the front's own where it had the part.
SECTION_IDS = {"summary": "summary", "waterfall": "change", "checklist": "checked", "next_steps": "next-steps",
               "next_month": "next-month", "cannot_know": "cannot-know", "trend": "sales-by-month",
               "customers": "customers", "products": "products", "category": "category",
               "breakdown_1": "breakdown-1", "breakdown_2": "breakdown-2", "returns": "returns"}


def _waterfall(front: Front, code: str | None) -> tuple[str, list[str]]:
    """The bars and, for a screen reader, the table of their words; the
    caption and the note stand behind the card's marker."""
    waterfall = front.waterfall
    if waterfall is None:
        return "", [front.waterfall_note or ""]
    previous, current = waterfall.previous_label.rsplit(" ", 2)[0], waterfall.current_label.rsplit(" ", 2)[0]
    rows = [[esc(bar.label), f"{esc(bar.was)} → {esc(bar.now)}", esc(bar.worth)] for bar in waterfall.bars]
    rows.append(["Total change", "", esc(waterfall.change_text)])
    words = f'<div class="visually-hidden">{table(["Part", f"{previous} → {current}", "Worth"], rows)}</div>'
    return waterfall_chart(waterfall, code) + words, [waterfall.caption, *([waterfall.note] if waterfall.note else [])]


def _card(report: ReportContract, front: Front, widget: Widget, code: str | None, texts: dict[str, str]) -> str:
    title = widget.title or ""
    asides = list(widget.caption)
    if widget.id == "trend":
        trend = next(c for c in report.charts if c.id == "revenue_trend")
        body = sales_chart(trend, title, code)
    elif widget.id == "waterfall":
        body, lines = _waterfall(front, code)
        asides = lines + asides
    else:
        body = _bars(widget, code)
    return (f'<section id="{SECTION_IDS[widget.id]}" class="card widget chart"><div class="whead">'
            f"<h2>{esc(title)}</h2>{marker(title, widget.notes, asides, texts)}</div>{body}</section>")


def _headline(dashboard: Dashboard, texts: dict[str, str]) -> str:
    line = dashboard.headline
    if line is None:
        return ""
    return (f'<div id="headline" class="headline"><span>{esc(line.text)}</span>'
            f'{marker("these sales figures", line.notes, line.asides, texts)}</div>')


def _next_month(band: NextMonthBand | None, texts: dict[str, str]) -> str:
    if band is None:
        return ""
    line = (f"{band.month}: about {band.figure} · likely {band.low} to {band.high}" if band.figure is not None
            else f"Next month: {band.reason}")
    return (f'<section id="band-next-month" class="band next-month"><h2>Next month</h2>'
            f'<p class="bandline">{esc(line)}</p>{marker("next month", band.notes, band.asides, texts)}</section>')


def _chip(chip: Chip) -> str:
    status = "" if chip.status == "checked" else f' <span class="cs">{esc(chip.status)}</span>'
    hidden = '<span class="visually-hidden"> checked</span>' if chip.status == "checked" else ""
    return (f'<li class="chip st-{chip.status.replace(" ", "-").replace(chr(39), "")}">'
            f'<span aria-hidden="true">{_CHIP_MARKS[chip.status]}</span> {esc(chip.label)}{status}{hidden}</li>')


def _checked(dashboard: Dashboard, texts: dict[str, str]) -> str:
    if not dashboard.checked:
        return ""
    chips = "".join(_chip(chip) for chip in dashboard.checked)
    return (f'<section id="band-checked" class="band checked"><h2>Checked</h2><ul class="chips">{chips}</ul>'
            f'{marker("what was checked", dashboard.checked_notes, [], texts)}</section>')


def _next_steps(dashboard: Dashboard, texts: dict[str, str]) -> str:
    if not dashboard.next_steps:
        return ""
    lines = "".join(f"<li>{esc(step)}</li>" for step in dashboard.next_steps)
    return (f'<section id="band-next-steps" class="band next-steps"><h2>Next step</h2><ul>{lines}</ul>'
            f'{marker("the next step", dashboard.next_steps_notes, [], texts)}</section>')


def note_texts(report: ReportContract) -> dict[str, str]:
    """Each note's sentence by its code: the report's own (NOTE_TEXTS)."""
    return {note.code: note.text for note in [*report.layer_1_numbers.notes, *report.layer_2_causes.notes]}


def dashboard_html(report: ReportContract, dashboard: Dashboard, front: Front) -> str:
    code = report.currency.code if report.currency is not None else None
    texts = note_texts(report)
    tiles = "".join(_tile(tile, texts) for tile in dashboard.tiles)
    cards = "".join(_card(report, front, widget, code, texts) for widget in dashboard.widgets if widget.kind == "chart")
    return (f'<section id="tiles" class="tiles-row"><div class="tiles">{tiles}</div></section>'
            f'{_headline(dashboard, texts)}<div class="widgets">{cards}</div>'
            f"{_next_month(dashboard.next_month, texts)}{_checked(dashboard, texts)}{_next_steps(dashboard, texts)}")


def words_html(report: ReportContract, dashboard: Dashboard, front: Front) -> str:
    """Technical details' first part: every sentence the dashboard leaves out
    of its rows - the front section whole, each chart's caption, each "not
    shown" line (Thach's layout: nothing deleted)."""
    # The page's order (DashboardWords): one copy, drawn alike.
    summary = [*(para(line, "caution") for line in front.caution), *(para(line) for line in front.summary),
               *(para(line, "small") for line in front.data_checks if front.state != "compared" and not front.caution),
               para(front.sales_note, "small"), read_with(front.notes.summary),
               para(front.waterfall_note, "small") if front.waterfall_note else "",
               *(para(line, "small") for line in dashboard.not_shown)]
    captions = [f"{widget.title}: {line}" for widget in dashboard.widgets for line in widget.caption]
    if front.waterfall is not None:
        captions.append(f"Where the change came from: {front.waterfall.caption}")
        if front.waterfall.note:
            captions.append(f"Where the change came from: {front.waterfall.note}")
    parts = [f'<section id="summary"><h3>In short</h3>{"".join(summary)}</section>']
    if captions:
        parts.append('<section id="chart-notes"><h3>About the charts</h3>'
                     + "".join(para(line) for line in captions) + "</section>")
    if front.state == "compared":
        parts.append(f'<section id="checked"><h3>What was checked</h3>{checked_html(front)}</section>')
        parts.append(f'<section id="next-steps"><h3>What to do next</h3>{next_steps_html(front)}</section>')
    parts.append(f'<section id="next-month"><h3>Next month</h3>{next_month_html(front)}</section>')
    parts.append(f'<section id="cannot-know"><h3>What this report cannot know</h3>{cannot_know_html(front)}</section>')
    return f'<div id="dashboard-words" class="card"><h2>The dashboard in words</h2>{"".join(parts)}</div>'


__all__ = ["DASHBOARD_STYLE", "SECTION_IDS", "dashboard_html", "marker", "note_texts", "words_html"]
