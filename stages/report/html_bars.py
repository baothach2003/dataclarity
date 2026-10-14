"""The dashboard's bar charts, drawn in HTML and CSS (docs/DASHBOARD_DESIGN.md
section 3; Thach's D6): sorted horizontal bars, each row its label and its
printed value as real text - readable at 390 px and read by a screen reader
(step 3's review: SVG text scaled to ~6 px on a phone, and an SVG image hid its
figures) - and the bar under them, on one scale that holds zero: a negative
value runs left of the zero line, never drawn like a sale (the review). Last
month's value is a thin marker under this month's bar. Parts of a whole (2 or
3 parts, every one above zero) are one bar per month cut into its parts. Every
figure printed is report.json's text; the widths are layout, no figure."""

from contracts.report_dashboard import Bar
from stages.report.html_parts import esc


def _scale(bars: list[Bar]) -> tuple[float, float]:
    values = [b.now for b in bars] + [b.was for b in bars if b.was is not None]
    low, high = min([0.0, *values]), max([0.0, *values])
    return low, (high - low) or 1.0


def _span(value: float, low: float, span: float) -> tuple[float, float]:
    """(left, width) in percent of the track for a bar from zero to `value`."""
    start, end = sorted((0.0, value))
    return (start - low) / span * 100, (end - start) / span * 100


def _bar(value: float, low: float, span: float, kind: str) -> str:
    left, width = _span(value, low, span)
    return f'<span class="hb-bar {kind}" style="left:{left:.2f}%;width:{max(width, 0.4):.2f}%"></span>'


def bar_chart(bars: list[Bar], title: str, code: str | None, *, diverging: bool = False) -> str:
    """One row per bar. `diverging`: the bars are changes (up and down
    colours); else this month's values (one colour) with last month's marker."""
    del code  # the texts carry the currency code (report.json's own)
    low, span = _scale(bars)
    zero = (0.0 - low) / span * 100
    rows = []
    for bar in bars:
        if diverging:
            kind = "up" if bar.now > 0 else "down" if bar.now < 0 else "flat"
        else:
            kind = "down" if bar.now < 0 else "now"
        was = (f'<span class="hb-was">was {esc(bar.was_text)}</span>' if bar.was_text is not None else "")
        marker = _bar(bar.was, low, span, "was hb-marker") if bar.was is not None else ""
        rows.append(f'<li class="hb-row"><span class="hb-label">{esc(bar.label)}</span>'
                    f'<span class="hb-val">{esc(bar.now_text)}{(" " + was) if was else ""}</span>'
                    f'<span class="hb-track" aria-hidden="true">'
                    f'{_bar(bar.now, low, span, kind)}{marker}'
                    f'<span class="hb-zero" style="left:{zero:.2f}%"></span></span></li>')
    return f'<ul class="hbars" aria-label="{esc(title)}">{"".join(rows)}</ul>'


def parts_chart(bars: list[Bar], title: str, code: str | None) -> str:
    """Very few parts of a whole (D6): this month's bar (and last month's)
    cut into the parts in the bars' order; no share is printed (stage 5
    computes none) - the legend under it prints each part's own figure."""
    del code
    months = [("This month", [b.now for b in bars])]
    if all(b.was is not None for b in bars):
        months.append(("Last month", [b.was or 0.0 for b in bars]))
    rows = []
    for name, values in months:
        total = sum(values) or 1.0
        cells = "".join(f'<span class="hp-part p{i}" style="width:{value / total * 100:.2f}%"></span>'
                        for i, value in enumerate(values))
        rows.append(f'<li class="hp-row"><span class="hb-label">{esc(name)}</span>'
                    f'<span class="hp-track" aria-hidden="true">{cells}</span></li>')
    return f'<ul class="hparts" aria-label="{esc(title)}">{"".join(rows)}</ul>'
