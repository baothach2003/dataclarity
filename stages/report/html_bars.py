"""The dashboard's bar charts, drawn in HTML and CSS (docs/DASHBOARD_DESIGN.md
section 3; Thach's D6): sorted horizontal bars, each row its label and its
printed value as real text - readable at 390 px and read by a screen reader
(step 3's review: SVG text scaled to ~6 px on a phone, and an SVG image hid its
figures) - and the bar under them, on one scale that holds zero: a negative
value runs left of the zero line, never drawn like a sale (the review). Last
month's value is a thin marker under this month's bar. Parts of a whole (2 or
3 parts, every one above zero) are one bar per month cut into its parts. Every
figure printed is report.json's text; the widths are layout, no figure.

Thach's visual style (2026-10-15; design section 11): one series (this month,
no negative value - the top products) prints each value at its bar's end; two
months compared keep the value above the bar and gain a legend (this month in
the main series colour, last month in the second); each row has a hover
title."""

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


def _hover(bar: Bar) -> str:
    return esc(f"{bar.label}: {bar.now_text}" + (f" (was {bar.was_text})" if bar.was_text is not None else ""))


def _at_end(bars: list[Bar]) -> str:
    """One series of no negative value: each value right after its bar, the
    longest bar the scale's whole (`--w` 1), the rest in proportion."""
    high = max(b.now for b in bars) or 1.0
    return "".join(f'<li class="hb-row end" title="{_hover(bar)}"><span class="hb-label">{esc(bar.label)}</span>'
                   f'<span class="hb-track end"><span class="hb-fill" style="--w:{bar.now / high:.4f}"></span>'
                   f'<span class="hb-val">{esc(bar.now_text)}</span></span></li>' for bar in bars)


LEGEND = ('<ul class="legend2"><li><span class="sw s1"></span>This month</li>'
          '<li><span class="sw s2"></span>Last month</li></ul>')


def bar_chart(bars: list[Bar], title: str, code: str | None, *, diverging: bool = False) -> str:
    """One row per bar. `diverging`: the bars are changes (up and down
    colours); else this month's values in the main series colour, last
    month's a marker in the second, with their legend."""
    del code  # the texts carry the currency code (report.json's own)
    two_months = any(b.was is not None for b in bars)
    if not diverging and not two_months and bars and all(b.now >= 0 for b in bars):
        return f'<ul class="hbars" aria-label="{esc(title)}">{_at_end(bars)}</ul>'
    low, span = _scale(bars)
    zero = (0.0 - low) / span * 100
    rows = []
    for bar in bars:
        # A negative value runs left of zero in the series colour: it is a value, not a change.
        kind = ("up" if bar.now > 0 else "down" if bar.now < 0 else "flat") if diverging else "now"
        was = (f'<span class="hb-was">was {esc(bar.was_text)}</span>' if bar.was_text is not None else "")
        marker = _bar(bar.was, low, span, "was hb-marker") if bar.was is not None else ""
        rows.append(f'<li class="hb-row" title="{_hover(bar)}"><span class="hb-label">{esc(bar.label)}</span>'
                    f'<span class="hb-val">{esc(bar.now_text)}{(" " + was) if was else ""}</span>'
                    f'<span class="hb-track" aria-hidden="true">'
                    f'{_bar(bar.now, low, span, kind)}{marker}'
                    f'<span class="hb-zero" style="left:{zero:.2f}%"></span></span></li>')
    legend = LEGEND if two_months and not diverging else ""
    return f'<ul class="hbars" aria-label="{esc(title)}">{"".join(rows)}</ul>{legend}'


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
