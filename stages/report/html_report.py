"""Stage 5's report.html (session 5B): one self-contained page rendered from
report.json - the numbers, how to read them, the causes, the actions - that
can be downloaded and read offline.

It shows report.json as it stands and computes nothing: every figure is a
field of report.json, formatted. The rules report.json holds are kept in
the rendering too: a withheld figure shows its reason, never a 0; a
previous-month value is never shown beside the current when that month is
incomplete; every note is worded by its code, an always-on one once. Every
string is escaped (SPECS SEC-3).
"""

from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from contracts.forecast import MIN_HISTORY_MONTHS
from contracts.report import Actions, Chart, Kpi, Numbers, ReportContract
from shared.contract_files import write_atomically
from shared.later_outputs import REPORT_HTML
from shared.run_registry import run_file
from stages.report.wording import month_name
from stages.report.html_causes import causes_html
from stages.report.html_charts import chart_html, plotly_js
from stages.report.html_front import front_html
from stages.report.html_parts import (
    FORMATS,
    change,
    count,
    currency_code,
    esc,
    items,
    links,
    money,
    note,
    para,
    reason,
    scope_shown,
    share,
    signed_money,
    table,
)

_VERDICTS = {"trusted": "trusted", "caution": "caution", "blocked": "blocked - the figures below are not a base "
             "for conclusions"}
# A previous figure withheld for the incomplete month: its reason is said
# once, beside the period, not in every cell (5B review 1 #8).
_NOT_COMPARED = "not compared - see why above"
_STYLE = """body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;max-width:980px;margin:2rem auto;
padding:0 1rem;color:#1d2330;line-height:1.5}h1{margin-bottom:.2rem}.meta,.reason{color:#5a6272}
.reason{font-style:italic}table{border-collapse:collapse;width:100%;margin:.6rem 0 1rem}th,td{border-bottom:1px solid
#dde1e8;padding:.35rem .5rem;text-align:left;vertical-align:top}.badge{border-left:6px solid #8a93a5;padding:.4rem
.9rem;margin:1rem 0;background:#f5f6f8}.badge-trusted{border-color:#2e7d4f}.badge-caution{border-color:#c98a00}
.badge-blocked{border-color:#b3261e}.note{border-left:3px solid #dde1e8;padding-left:.8rem;margin:.6rem 0}
.caution{color:#7a5200}@media (prefers-color-scheme:dark){.caution{color:#f0c060}}section{margin-top:2.2rem}
@media print{.plotly-graph-div{break-inside:avoid}}"""


def _change_cell(kpi: Kpi, incomplete: str | None) -> str:
    """Revenue's change: since 2.8 its exact amount (Thach, Q22: the
    appendix's figure) beside the percentage, or beside why the percentage is
    null; before 2.8, the percentage alone."""
    pct = (change(kpi.change_pct) if kpi.change_pct is not None else
           _previous(kpi, None, kpi.change_reason, incomplete) if kpi.change_reason else "")
    if kpi.change is None:
        return pct
    return f"{signed_money(kpi.change)} ({pct})" if kpi.change_pct is not None else f"{signed_money(kpi.change)} {pct}"


def _chart(chart: Chart, band: float | None = None, *, with_note: bool = True) -> str:
    """The chart and, beside it, why its line breaks, the trust cautions of
    the months it plots and the notes naming its figure (the standing rule).
    No month to draw: the sentence alone, never an empty chart (5B review 1
    #11)."""
    drawn = bool(chart.series and chart.series[0].x)
    parts = [f"<h3>{esc(chart.title)}</h3>", chart_html(chart, band) if drawn else ""]
    if chart.note and with_note:
        parts.append(para(chart.note))
    # A caution the gap note already says is said once (5B review 2 #11).
    parts.append(items(f'<span class="caution">Caution: {esc(c)}</span>' for c in chart.cautions
                       if not (chart.note and c.rstrip(".").lower() in chart.note.lower())))
    if chart.notes:
        parts.append(f"<p>Read with: {links(chart.notes)}</p>")
    return "".join(parts)


def _previous(kpi: Kpi, value: int | float | None, why: str | None, incomplete: str | None) -> str:
    if value is not None:
        return FORMATS[kpi.unit](value)
    return reason(_NOT_COMPARED if incomplete and why == incomplete else why or "")


def _numbers(numbers: Numbers, charts: dict[str, Chart]) -> str:
    period, trust = numbers.period, numbers.trust
    whole, incomplete = period.previous_complete, period.previous_incomplete_reason
    withheld = numbers.kpis[0].current is None
    head = (f"{period.current}; {period.previous} is not compared." if not whole else
            f"{period.current} against {period.previous}: the current month's figures are withheld (see below)."
            if withheld else f"{period.current} compared with {period.previous}.")
    parts = ["<h2>What happened</h2>", para(f"{head} The file covers {period.data_start} to {period.data_end}.")]
    if numbers.future_lines_reason:
        # Why the dates covered end before the file's last line (2E-u6).
        parts.append(para(numbers.future_lines_reason, "reason"))
    if incomplete:
        parts.append(para(incomplete, "reason"))
    if numbers.current_note:
        parts.append(para(numbers.current_note, "reason"))
    checks = [f"{esc(c.id)} ({esc(c.status.replace('_', ' '))}): {esc(c.message)}" for c in trust.checks]
    parts.append(f'<div class="badge badge-{esc(trust.verdict)}"><p><strong>Data trust: '
                 f"{esc(_VERDICTS[trust.verdict])}</strong></p>{items(checks)}"
                 f"{items(esc(limit) for limit in trust.limitations)}</div>")
    rows = [[esc(kpi.label),
             reason(kpi.current_reason or "") if kpi.current is None else FORMATS[kpi.unit](kpi.current),
             _previous(kpi, kpi.previous, kpi.previous_reason, incomplete),
             _change_cell(kpi, incomplete), links(kpi.notes)]
            for kpi in numbers.kpis]
    parts.append(table(["Figure", period.current, period.previous, "Change", "Notes"], rows))
    if numbers.unconfirmed_placeholders_reason:
        # Beside the customer figures it qualifies (2E-u3; CLAUDE.md 3.3a).
        parts.append(para(numbers.unconfirmed_placeholders_reason, "reason"))
    if "revenue_trend" in charts:
        parts.append(_chart(charts["revenue_trend"]))
    month_rows = [[esc(m.period),
                   reason(m.revenue_reason or "") if m.revenue is None else
                   reason(_NOT_COMPARED) if m.period == period.previous and not whole else money(m.revenue),
                   "yes" if m.complete else "no"] for m in numbers.revenue_by_month]
    if month_rows:
        parts.append(f"<details><summary>Revenue by month</summary>"
                     f"{table(['Month', 'Revenue', 'Whole month'], month_rows)}</details>")
    parts.append(_other_lines(numbers, withheld))
    if numbers.notes:
        parts.append("<h3>Notes on these figures</h3>"
                     + "".join(note(n, previous_complete=whole) for n in numbers.notes))
    return "".join(parts)


def _other_lines(numbers: Numbers, withheld: bool) -> str:
    """Lines no figure counts, and the money of the classes you gave -
    never dropped silently (CONTRACTS 6). A previous scope only when that
    month is compared; a withheld month's non-product amount says why."""
    period, whole, parts = numbers.period, numbers.period.previous_complete, []
    if numbers.undated_lines_reason:
        parts.append(para(numbers.undated_lines_reason))
    rows = [[esc(u.scope), esc(u.reason), count(u.lines)] for u in numbers.unmeasurable
            if scope_shown(u.scope, previous_complete=whole)]
    if rows:
        parts.append(table(["Scope", "Why", "Lines"], rows, "Lines that cannot be measured"))
    rows = [[esc(n.line_class), count(n.lines), money(n.amount),
             # Only a withheld month's 0; a real amount stands (5B review 2 #8).
             reason("withheld, with the current month's figures") if withheld and n.amount_current == 0
             else money(n.amount_current),
             money(n.amount_previous) if whole else reason(_NOT_COMPARED), esc(n.reason)]
            for n in numbers.non_product]
    if rows:
        parts.append(table(["Class", "Lines", "Amount", period.current, period.previous, "Where it went"], rows,
                           "Lines of the classes you gave"))
    # Each with why, worded by its class code (Thach, 2026-10-04, decision (ix)).
    rows = [[esc(o.line_class), esc(o.scope), esc(o.sign or ""), count(o.lines), money(o.amount),
             count(o.lines_without_amount), esc(o.reason or "")] for o in numbers.outside_revenue
            if scope_shown(o.scope, previous_complete=whole)]
    if rows:
        parts.append(table(["Class", "Scope", "Sign", "Lines", "Amount", "Lines without an amount", "Why"], rows,
                           "Lines outside revenue"))
    return "<h3>Other lines and where their money went</h3>" + "".join(parts) if parts else ""


def _actions(actions: Actions, charts: dict[str, Chart]) -> str:
    forecast, parts = actions.forecast, ["<h2>What next</h2>"]
    months = f"{forecast.months_used} complete month{'' if forecast.months_used == 1 else 's'}"
    if forecast.insufficient_history:
        parts.append(para(f"There is too little history for a forecast: {months}, and {MIN_HISTORY_MONTHS} are "
                          "needed."))
    else:
        parts.append(para(f"Method: {forecast.method}. Learned from {months}."))
    # The forecast's own notes, whenever it has them - once (5B review 1 #3, #12).
    parts.extend(para(n, "reason") for n in (forecast.history_note, forecast.season_note) if n)
    if forecast.points:
        first = forecast.points[0]
        if forecast.partial_first_month_until is not None:
            # "The dates the file covers": a line dated after the upload is in no figure, so "the file ends"
            # could be false (Thach, 2026-10-04, decision (x)).
            parts.append(para(f"The dates the file covers end on {forecast.partial_first_month_until}, part-way "
                              f"through {first.period}: that month's revenue so far is not compared with the "
                              "forecast."))
        elif forecast.first_month_in_file:
            parts.append(para(f"The file already holds a line for {first.period}: its revenue so far is not "
                              "compared with the forecast."))
        parts.append(table(["Month", "Forecast", "Low", "High"],
                           [[esc(p.period), money(p.point), money(p.low), money(p.high)] for p in forecast.points],
                           f"Low and high: the {share(first.confidence)} band, from the method's own past errors"))
        # How the front's "likely between" range is built (Thach, Q12: moved here).
        parts.append(para(f"The range is an {share(first.confidence)} interval worked out from how far off this "
                          "method's past estimates were (their root mean square times Student's t) or, with too few "
                          "past estimates, from the spread of the months themselves."))
        if "forecast" in charts:
            parts.append(_chart(charts["forecast"], first.confidence, with_note=False))
        elif forecast.notes:
            # The chart carries them when drawn - once, never twice (5B review 2 #4, #6).
            parts.append(f"<p>Read the forecast with: {links(forecast.notes)}</p>")
    parts.append("<h3>Recommendations</h3>")
    # The free-text recommendations are printed nowhere, whoever wrote the
    # report.json (Thach, Q42): the unchecked format v1 switched off because
    # it fabricated numbers.
    if actions.recommendations_status == "switched_off":
        parts.append(para("The AI recommendations are switched off for this report."))
    else:
        parts.append(para("No AI recommendation is available for this run."))
    return "".join(parts)


# The appendix opens to the note a front link names, and resizes its charts
# when opened: a chart drawn while closed has no width (inline, no network).
_APPENDIX_JS = ("(function(){var a=document.getElementById('appendix');if(!a)return;"
                "function open(){if(location.hash&&a.querySelector(location.hash)){a.open=true;}}"
                "window.addEventListener('hashchange',open);open();"
                "a.addEventListener('toggle',function(){if(a.open&&window.Plotly){"
                "document.querySelectorAll('.plotly-graph-div').forEach(function(d){Plotly.Plots.resize(d);});"
                "}});})();")
_FRONT_STYLE = """:root{--card:#fff;--ink2:#52514e;--line:#e4e3df;--up:#2a78d6;--down:#e34948;--tot:#8a8984;
--accent:#2a78d6}@media (prefers-color-scheme:dark){:root{--card:#232321;--ink2:#c3c2b7;--line:#383835;
--up:#3987e5;--down:#e66767;--tot:#8f8e88;--accent:#3987e5}body{background:#1a1a19;color:#fff}
.badge{background:#2b2b29}}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin-top:18px}.card h2{margin:0 0 .6rem;font-size:1.15rem}.summary p{font-size:1.05rem}
.small{font-size:.9rem;color:var(--ink2)}svg{width:100%;height:auto;display:block}.grid{stroke:var(--line)}
.base{stroke:var(--ink2)}.tick{fill:var(--ink2);font-size:11px}.val{fill:currentColor;font-size:12px;font-weight:600}
.lab{fill:var(--ink2);font-size:11.5px}.up{fill:var(--up)}.down{fill:var(--down)}.tot{fill:var(--tot)}
.flat{fill:var(--ink2)}.series{fill:none;stroke:var(--accent);stroke-width:2}.hit{fill:transparent}
.dot,.pt-last{fill:var(--accent)}.mark:hover .hit{fill:var(--accent);fill-opacity:.25}.num{white-space:nowrap}
ul.check{list-style:none;padding-left:0}ul.check li{padding:3px 0 3px 24px;position:relative}
ul.check li::before{position:absolute;left:0;width:18px;text-align:center;font-weight:700}
.yes li::before{content:"\\2713";color:var(--up)}.against li::before{content:"\\2193";color:var(--down)}
.no li::before{content:"\\2715";color:var(--ink2)}.cant li::before{content:"?";color:var(--ink2)}
.rec{border-top:1px solid var(--line);padding-top:8px;margin-top:8px}.scroll{overflow-x:auto}
#appendix{margin-top:18px}#appendix>summary{cursor:pointer;font-weight:600;padding:8px 0}
#appendix table{display:block;overflow-x:auto}p,li,td,h1,h2,h3{overflow-wrap:anywhere}th{overflow-wrap:break-word}"""


def render_html(report: ReportContract) -> str:
    """The front section, then today's report in a closed appendix (2.9);
    a report from before 2.9 as it was rendered then."""
    with currency_code(report.currency.code if report.currency is not None else None):
        return _render(report)


def _render(report: ReportContract) -> str:
    numbers, charts = report.layer_1_numbers, {c.id: c for c in report.charts}
    provenance, quality = report.provenance, report.data_quality
    models = f" ({esc(', '.join(provenance.models_used))})" if provenance.models_used else ""
    meta = para(f"File: {report.source_file} - run {report.run_id} - generated "
                f"{report.generated_at:%Y-%m-%d %H:%M %Z}", "meta")
    front = report.front
    if front is None:
        header, opening, closing = f"<header><h1>Sales report</h1>{meta}</header>", "", ""
    else:
        period = numbers.period
        header = (f"<header><h1>Your sales report</h1>{meta}"
                  f"{para(f'{month_name(period.current)} compared with {month_name(period.previous)}', 'meta')}"
                  f"</header>{front_html(report, front)}")
        opening = ('<details id="appendix"><summary>Technical details (for an analyst)</summary>'
                   + para("In this appendix, 'revenue' is the same figure as 'sales' above.")
                   + (para(f"Amounts are in {report.currency.code}. Sentences quoted from the analysis, and the "
                           "evidence of each check, are shown as written, their amounts without the code.")
                      if report.currency is not None and report.currency.code else ""))
        closing = "</details>"
    body = "".join([
        header, opening,
        '<section id="quality"><h2>The file</h2>',
        para(f"Rows in: {count(quality.rows_in)}. Rows out: {count(quality.rows_out)}. Changes that did "
             f"something: {count(quality.issues_fixed)}. Warnings: {count(quality.warnings)}."), "</section>",
        f'<section id="numbers">{_numbers(numbers, charts)}</section>',
        '<section id="how-to-read"><h2>How to read these figures</h2>',
        "".join(note(n, previous_complete=numbers.period.previous_complete) for n in numbers.how_to_read),
        "</section>",
        f'<section id="causes">{causes_html(report.layer_2_causes, numbers)}</section>',
        f'<section id="actions">{_actions(report.layer_3_actions, charts)}</section>',
        '<section id="provenance"><h2>Where these figures come from</h2>',
        f"<p>Stages run: {esc(', '.join(provenance.stages_run))}. AI answers used: {count(provenance.ai_calls)}"
        # An AI answer counted here can be a column mapping or a cleaning plan
        # (builder.py), not only words; what holds for every one is that it
        # computes no figure (CLAUDE.md 3.2; the 6E1 review #9).
        f"{models}. Every figure is computed by code from the earlier stages' files; the AI computes none.</p>",
        "</section>", closing, f"<script>{_APPENDIX_JS}</script>" if front is not None else ""])
    style = _STYLE + (_FRONT_STYLE if front is not None else "")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width, initial-scale=1">'
            f"<title>DataClarity report - {esc(report.source_file)}</title><style>{style}</style>"
            f"<script>{plotly_js()}</script></head><body>{body}</body></html>")


def html_run(runs_root: Path, run_id: str, *,
             around_write: Callable[[], AbstractContextManager[object]] | None = None) -> Path:
    """Render runs/<run_id>/report.json to report.html beside it, atomically:
    a failure leaves the previous page whole."""
    source = run_file(runs_root, run_id, ReportContract.filename or "report.json")
    report = ReportContract.model_validate_json(source.read_text(encoding="utf-8"))
    path = run_file(runs_root, run_id, REPORT_HTML)
    write_atomically(path, render_html(report).encode("utf-8"), around_replace=around_write)
    return path
