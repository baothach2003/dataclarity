"""report.html's front section (the report redesign, step 3): report.json's
`front` printed as it stands - the summary and the sales chart, the
waterfall, the checklist, what to do next, next month, what this report
cannot know (docs/REPORT_REDESIGN.md section 1). The wording is report.json's
one copy (the page will print the same); this module only lays it out.
Every string is escaped (SPECS SEC-3). Each part's body is also drawn by the
dashboard (html_dashboard.py, 2.10), in the order report.json gives."""

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
    parts.append(read_with(front.notes.summary))
    trend = next((c for c in report.charts if c.id == "revenue_trend"), None)
    # A blocked report is one sentence: no chart (the review).
    if front.state != "blocked" and trend is not None and trend.series and trend.series[0].x:
        parts.append(f"<h3>{esc(front.chart_title)}</h3>{sales_chart(trend, front.chart_title, code)}")
        parts += [para(line, "small") for line in front.chart_note]
    parts.append("</section>")
    return "".join(parts)


def read_with(codes: list[str]) -> str:
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


def change_html(front: Front, code: str | None) -> str:
    body = _waterfall(front.waterfall, code) if front.waterfall is not None else para(front.waterfall_note or "")
    return body + read_with(front.notes.change)


_MARKS = {"matches": "yes", "moved": "yes", "against": "against", "not_reason": "no", "cannot_show": "cant"}


def checked_html(front: Front) -> str:
    parts = [] if front.caution else [para(line) for line in front.data_checks]
    for group in front.checklist:
        parts.append(f"<h3>{esc(group.title)}</h3>")
        if group.note:
            parts.append(para(group.note, "small"))
        parts.append(f'<ul class="check {_MARKS[group.kind]}">'
                     + "".join(f"<li>{esc(line)}</li>" for line in group.lines)
                     + "</ul>")
        if group.after:
            parts.append(para(group.after, "small"))
    parts.append(read_with(front.notes.checked))
    return "".join(parts)


def next_steps_html(front: Front) -> str:
    steps = front.next_steps
    parts = []
    if steps is not None and steps.sentence:
        parts.append(para(steps.sentence))
    for item in steps.items if steps is not None else []:
        parts.append(f'<div class="rec">{para("Rests on: " + item.rests_on, "small")}'
                     f"<p><strong>Action:</strong> {esc(item.action)}</p><p><strong>Why:</strong> {esc(item.why)}</p>"
                     f"{para(item.watch, 'small')}</div>")
    parts.append(read_with(front.notes.next_steps))
    return "".join(parts)


def next_month_html(front: Front) -> str:
    return f'{"".join(para(line) for line in front.next_month)}{read_with(front.notes.next_month)}'


def cannot_know_html(front: Front) -> str:
    return items(f"<strong>{esc(item.title)}.</strong> {esc(item.text)}" for item in front.cannot_know)


def front_html(report: ReportContract, front: Front) -> str:
    """Sections 1 to 6 (a report before 2.10). A blocked report keeps section
    1's one sentence; a month not compared shows section 1 alone of the first
    four (CONTRACTS 11)."""
    parts = [_summary(report, front)]
    code = report.currency.code if report.currency is not None else None
    if front.state == "compared":
        parts += [f'<section id="change" class="card"><h2>Where the change came from</h2>{change_html(front, code)}'
                  "</section>",
                  f'<section id="checked" class="card"><h2>What was checked</h2>{checked_html(front)}</section>',
                  f'<section id="next-steps" class="card"><h2>What to do next</h2>{next_steps_html(front)}</section>']
    parts += [f'<section id="next-month" class="card"><h2>Next month</h2>{next_month_html(front)}</section>',
              f'<section id="cannot-know" class="card"><h2>What this report cannot know</h2>'
              f"{cannot_know_html(front)}</section>"]
    return "".join(parts)
