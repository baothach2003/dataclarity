"""report.html's front section (the report redesign, step 3): report.json's
`front` printed as it stands - the summary and the sales chart, the
waterfall, the checklist, what to do next, next month, what this report
cannot know (docs/REPORT_REDESIGN.md section 1). The wording is report.json's
one copy (the page will print the same); this module only lays it out.
Every string is escaped (SPECS SEC-3)."""

from contracts.report import ReportContract
from contracts.report_front import Front, Waterfall
from stages.report.html_parts import esc, items, links, para, table
from stages.report.html_svg import sales_chart, waterfall_chart


def _summary(report: ReportContract, front: Front) -> str:
    code = report.currency.code if report.currency is not None else None
    parts = ['<section id="summary" class="card summary"><h2>In 30 seconds</h2>']
    parts += [para(line, "caution") for line in front.caution]
    parts += [para(line) for line in front.summary]
    # Shown once: a caution's lines open the section; otherwise the one data
    # checks line stands in section 3, or here when there is no section 3.
    if front.state == "not_compared" and not front.caution:
        parts += [para(line, "small") for line in front.data_checks]
    parts.append(para(front.sales_note, "small"))
    parts.append(_read_with(front.notes.summary))
    trend = next((c for c in report.charts if c.id == "revenue_trend"), None)
    # A blocked report is one sentence: no chart (the review).
    if front.state != "blocked" and trend is not None and trend.series and trend.series[0].x:
        parts.append(f"<h3>{esc(front.chart_title)}</h3>{sales_chart(trend, front.chart_title, code)}")
        parts += [para(line, "small") for line in front.chart_note]
    parts.append("</section>")
    return "".join(parts)


def _read_with(codes: list[str]) -> str:
    """The notes beside a section's figures (Q35), each a link to its
    sentence in the appendix."""
    return f'<p class="small">Read these figures with: {links(codes)}</p>' if codes else ""


def _waterfall(waterfall: Waterfall, code: str | None) -> str:
    previous, current = waterfall.previous_label.rsplit(" ", 2)[0], waterfall.current_label.rsplit(" ", 2)[0]
    rows = [[esc(bar.label), f"{esc(bar.was)} → {esc(bar.now)}", f'<span class="num">{esc(bar.worth)}</span>']
            for bar in waterfall.bars]
    rows.append(["<strong>Total change</strong>", "", f'<strong class="num">{esc(waterfall.change_text)}</strong>'])
    return (para(waterfall.caption, "small") + waterfall_chart(waterfall, code)
            + f'<div class="scroll">{table(["Part", f"{previous} → {current}", "Worth"], rows)}</div>'
            + (para(waterfall.note, "small") if waterfall.note else ""))


def _change(front: Front, code: str | None) -> str:
    body = _waterfall(front.waterfall, code) if front.waterfall is not None else para(front.waterfall_note or "")
    return (f'<section id="change" class="card"><h2>Where the change came from</h2>{body}'
            f"{_read_with(front.notes.change)}</section>")


_MARKS = {"matches": "yes", "moved": "yes", "against": "against", "not_reason": "no", "cannot_show": "cant"}


def _checked(front: Front) -> str:
    parts = ['<section id="checked" class="card"><h2>What was checked</h2>']
    if not front.caution:
        parts += [para(line) for line in front.data_checks]
    for group in front.checklist:
        parts.append(f"<h3>{esc(group.title)}</h3>")
        if group.note:
            parts.append(para(group.note, "small"))
        parts.append(f'<ul class="check {_MARKS[group.kind]}">'
                     + "".join(f"<li>{esc(line)}</li>" for line in group.lines)
                     + "</ul>")
        if group.after:
            parts.append(para(group.after, "small"))
    parts.append(_read_with(front.notes.checked))
    parts.append("</section>")
    return "".join(parts)


def _next_steps(front: Front) -> str:
    steps = front.next_steps
    parts = ['<section id="next-steps" class="card"><h2>What to do next</h2>']
    if steps is not None and steps.sentence:
        parts.append(para(steps.sentence))
    for item in steps.items if steps is not None else []:
        parts.append(f'<div class="rec">{para("Rests on: " + item.rests_on, "small")}'
                     f"<p><strong>Action:</strong> {esc(item.action)}</p><p><strong>Why:</strong> {esc(item.why)}</p>"
                     f"{para(item.watch, 'small')}</div>")
    parts.append("</section>")
    return "".join(parts)


def _next_month(front: Front) -> str:
    return (f'<section id="next-month" class="card"><h2>Next month</h2>'
            f'{"".join(para(line) for line in front.next_month)}{_read_with(front.notes.next_month)}</section>')


def _cannot_know(front: Front) -> str:
    rows = (f"<strong>{esc(item.title)}.</strong> {esc(item.text)}" for item in front.cannot_know)
    return f'<section id="cannot-know" class="card"><h2>What this report cannot know</h2>{items(rows)}</section>'


def front_html(report: ReportContract, front: Front) -> str:
    """Sections 1 to 6. A blocked report keeps section 1's one sentence; a
    month not compared shows section 1 alone of the first four (CONTRACTS 11)."""
    parts = [_summary(report, front)]
    code = report.currency.code if report.currency is not None else None
    if front.state == "compared":
        parts += [_change(front, code), _checked(front), _next_steps(front)]
    parts += [_next_month(front), _cannot_know(front)]
    return "".join(parts)
