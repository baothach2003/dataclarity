"""The front section's two charts as inline SVG (the report redesign, step 3;
the mock's form): sales by month, whole months only (report.json's
revenue_trend chart, its gaps kept), and the waterfall of the change
(report.json's front.waterfall). Drawn from report.json's figures: the
geometry is the page's, no figure is computed. Every label is escaped; a
point's own words are in its <title> (hover, and read by screen readers)."""

from contracts.report import Chart
from contracts.report_front import Waterfall
from shared.wording import amount, count, month_name
from stages.report.html_charts import months_only
from stages.report.html_parts import esc

WIDTH, HEIGHT, LEFT, RIGHT, TOP, BOTTOM = 640, 230, 64, 20, 22, 34


def _ticks(low: float, high: float, n: int = 4) -> list[float]:
    """Round tick values covering [low, high]: steps of 1, 2 or 5 times a
    power of ten."""
    span = (high - low) or abs(high) or 1.0
    raw = span / n
    power = 10 ** len(str(int(raw))) / 10 if raw >= 1 else 1.0
    step = next(m * power for m in (1, 2, 5, 10) if m * power >= raw)
    start = (low // step) * step
    ticks = [start]
    # Up to the first tick at or above the highest value, so no point is
    # drawn above the chart (the review: the demo's top month was clipped).
    while ticks[-1] < high:
        ticks.append(ticks[-1] + step)
    return ticks


def _scale(ticks: list[float]):
    low, high = ticks[0], ticks[-1]

    def y(value: float) -> float:
        return TOP + (HEIGHT - TOP - BOTTOM) * (1 - (value - low) / ((high - low) or 1.0))
    return y


def _grid(ticks: list[float], y, label) -> str:
    return "".join(f'<line x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{y(t):.1f}" y2="{y(t):.1f}" class="grid"/>'
                   f'<text x="{LEFT - 6}" y="{y(t) + 4:.1f}" class="tick" text-anchor="end">{esc(label(t))}</text>'
                   for t in ticks)


def sales_chart(chart: Chart, title: str, code: str | None) -> str:
    """Whole months as report.json draws them: a null is a gap, never a zero
    and never joined (CONTRACTS 11)."""
    months_only(chart)
    series = chart.series[0]
    points = [(x, y) for x, y in zip(series.x, series.y)]
    values = [y for _, y in points if y is not None]
    if not values:
        return ""
    ticks = _ticks(min(values), max(values))
    y = _scale(ticks)
    step = (WIDTH - LEFT - RIGHT) / max(len(points) - 1, 1)
    xs = [LEFT + i * step for i in range(len(points))]
    parts = [f'<svg viewBox="0 0 {WIDTH} {HEIGHT}" role="img" class="sales" aria-label="{esc(title)}">',
             f"<title>{esc(title)}</title>", _grid(ticks, y, lambda t: _coded(count(t), code))]
    run: list[str] = []
    for (month, value), x in zip([*points, (None, None)], [*xs, 0.0]):
        if value is None:
            if len(run) > 1:
                parts.append(f'<polyline class="series" points="{" ".join(run)}"/>')
            elif run:
                parts.append(f'<circle cx="{run[0].split(",")[0]}" cy="{run[0].split(",")[1]}" r="3" class="dot"/>')
            run = []
            continue
        run.append(f"{x:.1f},{y(value):.1f}")
    for i, ((month, value), x) in enumerate(zip(points, xs)):
        if month.endswith("-01") or i == 0:
            parts.append(f'<text x="{x:.1f}" y="{HEIGHT - 10}" class="tick" text-anchor="middle">{month[:4]}</text>')
        if value is None:
            continue
        last = i == len(points) - 1
        parts.append(f'<g class="mark"><title>{esc(month_name(month))}: {esc(amount(value, code))}</title>'
                     f'<circle cx="{x:.1f}" cy="{y(value):.1f}" r="{5 if last else 9}" '
                     f'class="{"pt-last" if last else "hit"}"/></g>')
        if last:
            parts.append(f'<text x="{x - 6:.1f}" y="{y(value) - 10:.1f}" class="val" text-anchor="end">'
                         f"{esc(amount(value, code))}</text>")
    parts.append("</svg>")
    return "".join(parts)


def _coded(text: str, code: str | None) -> str:
    """An axis amount carries the currency code too (Q8)."""
    return f"{code} {text}" if code else text


def _two_lines(label: str) -> tuple[str, str]:
    words = label.split()
    best = min(range(1, len(words) + 1), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return " ".join(words[:best]), " ".join(words[best:])


def waterfall_chart(waterfall: Waterfall, code: str | None = None) -> str:
    """Each part from where the last ended, last month's sales at 0, then the
    whole change (the mock's form)."""
    steps, total = [], 0.0
    for bar in waterfall.bars:
        steps.append((bar.label, total, total + bar.shown, bar.worth, bar.shown))
        total += bar.shown
    steps.append((f"Change to {waterfall.current_label.rsplit(' ', 2)[0]}", 0.0, waterfall.shown_change,
                  waterfall.change_text, waterfall.shown_change))
    levels = [0.0] + [v for _, a, b, _, _ in steps for v in (a, b)]
    ticks = _ticks(min(levels), max(levels))
    y = _scale(ticks)
    height = HEIGHT + 30
    slot = (WIDTH - LEFT - RIGHT) / len(steps)
    parts = [f'<svg viewBox="0 0 {WIDTH} {height}" role="img" class="wf" aria-label="Where the change came from">',
             "<title>Where the change came from</title>",
             _grid(ticks, y, lambda t: _coded(f"{t:+,.0f}", code) if t else "0"),
             f'<line x1="{LEFT}" x2="{WIDTH - RIGHT}" y1="{y(0):.1f}" y2="{y(0):.1f}" class="base"/>',
             f'<text x="{LEFT}" y="12" class="tick">0 = {esc(waterfall.previous_label)} '
             f"({esc(waterfall.previous_text)})</text>"]
    for i, (label, start, end, worth, shown) in enumerate(steps):
        x = LEFT + i * slot + slot * 0.15
        width = slot * 0.7
        top, bottom = min(y(start), y(end)), max(y(start), y(end))
        last = i == len(steps) - 1
        kind = "tot" if last else "flat" if bottom - top < 1.5 else "up" if shown > 0 else "down"
        parts.append(f'<g class="mark"><title>{esc(label)}: {esc(worth)}</title>'
                     f'<rect x="{x:.1f}" y="{top:.1f}" width="{width:.1f}" height="{max(bottom - top, 1.5):.1f}" '
                     f'rx="3" class="{kind}"/>'
                     f'<text x="{x + width / 2:.1f}" y="{top - 6:.1f}" class="val" text-anchor="middle">'
                     f"{esc(worth)}</text></g>")
        first, second = _two_lines(label)
        parts.append(f'<text x="{x + width / 2:.1f}" y="{HEIGHT + 2}" class="lab" text-anchor="middle">{esc(first)}'
                     f'</text><text x="{x + width / 2:.1f}" y="{HEIGHT + 16}" class="lab" text-anchor="middle">'
                     f"{esc(second)}</text>")
    parts.append("</svg>")
    return "".join(parts)
