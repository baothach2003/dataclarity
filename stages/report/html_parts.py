"""The small parts report.html is built from (session 5B): escaping,
number formats, tables, notes.

Every string taken from report.json passes through `esc` before it reaches
the page - the AI's text and the uploaded file's alike (SPECS SEC-3, as 5B
extended it). Numbers are formatted here, never computed: a format rounds
for display (CONTRACTS 9, "stage 5 performs no analysis").
"""

import json
import re
from collections.abc import Callable, Iterable, Sequence
from html import escape

from contracts.lines import NoteMeasure
from contracts.report import NoteView

_ZERO = re.compile(r"[-+][0.,]+%?")


def esc(value: object) -> str:
    return escape(str(value), quote=True)


def _signless(text: str) -> str:
    """A value that shows as zero shows no sign: -0.0 in a file, or a small
    negative rounded away (CONTRACTS 11; 5B review 1 #4)."""
    return text[1:] if text.startswith("-") and _ZERO.fullmatch(text) else text


def money(value: float) -> str:
    return _signless(f"{value:,.2f}")


def count(value: float) -> str:
    return _signless(f"{value:,.0f}")


def ratio(value: float) -> str:
    return _signless(f"{value:.3f}")


def one_decimal(value: float) -> str:
    return _signless(f"{value:,.1f}")


def change(value: float) -> str:
    text = f"{value:+,.1f}%"
    return text[1:] if _ZERO.fullmatch(text) else text


def share(value: float) -> str:
    return _signless(f"{value:.0%}")


def number(value: float) -> str:
    """A figure of no fixed unit (a hypothesis's evidence): two decimals from
    100 up, four significant digits below."""
    return money(value) if abs(value) >= 100 else _signless(f"{value:.4g}")


FORMATS: dict[str, Callable[[float], str]] = {"money": money, "count": count, "ratio": ratio}
# A signal row's unit is its series' (and a year-over-year row's, a percent).
SERIES_FORMATS: dict[str, Callable[[float], str]] = {
    "revenue": money, "aov": money, "price_per_unit": money, "orders": one_decimal,
    "active_customers": one_decimal, "frequency": ratio, "units_per_order": ratio, "return_rate": ratio}


def signal_value(series: str, mode: str, value: float) -> str:
    if mode == "yoy":
        return change(value)
    return SERIES_FORMATS.get(series, number)(value)


def _plain(value: object) -> object:
    if isinstance(value, float):
        return float(number(value).replace(",", ""))
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    return value


def _marked(value: object, marks: dict[str, str]) -> object:
    if isinstance(value, str) and value in marks:
        return f"{value} (suggested: {marks[value]}, not confirmed)"
    if isinstance(value, dict):
        return {key: _marked(item, marks) for key, item in value.items()}
    if isinstance(value, list):
        return [_marked(item, marks) for item in value]
    return value


def evidence_value(value: object, marks: dict[str, str] | None = None) -> str:
    """A hypothesis's evidence as it stands, readably (text, not HTML: the
    caller escapes it) - names as written, None as "none" (5B review 1 #13);
    a product whose class was suggested and not confirmed with its mark,
    "(suggested: <class>, not confirmed)" (CONTRACTS 6 and 7; 5B review 2
    #9)."""
    value = _marked(value, marks or {})
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return count(value)
    if isinstance(value, float):
        return number(value)
    if isinstance(value, str):
        return value
    return json.dumps(_plain(value), ensure_ascii=False, default=str)


def reason(text: str) -> str:
    return f'<span class="reason">{esc(text)}</span>'


def para(text: str, cls: str | None = None) -> str:
    return f'<p class="{cls}">{esc(text)}</p>' if cls else f"<p>{esc(text)}</p>"


def items(cells: Iterable[str]) -> str:
    """A list of already-built HTML items."""
    found = "".join(f"<li>{cell}</li>" for cell in cells)
    return f"<ul>{found}</ul>" if found else ""


def table(headers: Sequence[str], rows: Iterable[Sequence[str]], caption: str | None = None) -> str:
    """Headers are escaped here; cells arrive as HTML built with `esc`."""
    head = "".join(f'<th scope="col">{esc(h)}</th>' for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    title = f"<caption>{esc(caption)}</caption>" if caption else ""
    return f"<table>{title}<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def links(codes: Sequence[str]) -> str:
    """The notes beside a figure, by code, each a link to its sentence."""
    return " ".join(f'<a href="#note-{esc(code)}">{esc(code.replace("_", " "))}</a>' for code in codes)


def scope_shown(scope: str, *, previous_complete: bool) -> bool:
    """Never a previous value beside a current one when the previous month
    is incomplete (CONTRACTS 9 and 11; 5A review 3 #4). A current scope is
    shown whatever the KPIs: its lines are real - they are why a month is
    withheld (5B review 1 #5)."""
    return scope != "previous" or previous_complete


def measures(rows: Sequence[NoteMeasure], *, previous_complete: bool) -> str:
    shown = [m for m in rows if scope_shown(m.scope, previous_complete=previous_complete)]
    if not shown:
        return ""
    return table(["Measure", "Scope", "Lines", "Amount", "Orders", "Keys"], [
        [esc(m.name), esc(m.scope), count(m.lines), "" if m.amount is None else money(m.amount),
         "" if m.orders is None else count(m.orders), "" if m.keys is None else count(m.keys)] for m in shown])


def note(view: NoteView, *, previous_complete: bool) -> str:
    """A note worded by its code (the report's text is NOTE_TEXTS'), with
    its measures; the anchor its figures link to."""
    return (f'<div class="note" id="note-{esc(view.code)}">{para(view.text)}'
            f"{measures(view.measures, previous_complete=previous_complete)}</div>")
