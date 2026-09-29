"""report.html's charts (session 5B): Plotly, its library inlined once so the
page needs no network (PROJECT_PLAN 5B: self-contained).

A chart carries only months and numbers. Plotly draws its own markup in
labels, so no text from the file or the AI ever reaches it (SPECS SEC-3):
the axis labels are checked to be months, and the trace names are this
module's own words.
"""

import re

import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

from contracts.report import Chart
from stages.report.html_parts import share

_MONTH = re.compile(r"[0-9]{4}-(0[1-9]|1[0-2])")
_CONFIG = {"displaylogo": False, "responsive": True}


def plotly_js() -> str:
    """The library, for one inline <script>: it must not close the tag."""
    js = get_plotlyjs()
    if "</script" in js.lower():
        raise ValueError("the plotly.js bundle closes a <script> tag; it cannot be inlined")
    return js


def _months(chart: Chart) -> None:
    for series in chart.series:
        if not all(_MONTH.fullmatch(x) for x in series.x):
            raise ValueError(f"chart {chart.id!r}: a chart's x values are months (YYYY-MM), nothing else")


def _figure(chart: Chart, band: float | None) -> go.Figure:
    series = {s.name: s for s in chart.series}
    if chart.id == "revenue_trend":
        line = series["revenue"]
        traces = [go.Scatter(x=line.x, y=line.y, mode="lines+markers", name="Revenue", connectgaps=False)]
    else:
        point, low, high = series["point"], series["low"], series["high"]
        label = "Band" if band is None else f"{share(band)} band"
        traces = [
            go.Scatter(x=high.x, y=high.y, mode="lines", line={"width": 0}, showlegend=False, name="High",
                       connectgaps=False),
            go.Scatter(x=low.x, y=low.y, mode="lines", line={"width": 0}, fill="tonexty", name=label,
                       fillcolor="rgba(31, 90, 153, 0.18)", connectgaps=False),
            go.Scatter(x=point.x, y=point.y, mode="lines+markers", name="Forecast", connectgaps=False),
        ]
    figure = go.Figure(traces)
    figure.update_layout(template="none", height=320, margin={"l": 70, "r": 20, "t": 20, "b": 40},
                         xaxis={"type": "category"}, yaxis={"tickformat": ",.0f"},
                         legend={"orientation": "h", "y": -0.2})
    return figure


def chart_html(chart: Chart, band: float | None = None) -> str:
    """The chart's <div> and its one <script>; `band` is the forecast band's
    coverage (0.8), named in the legend."""
    _months(chart)
    html: str = pio.to_html(_figure(chart, band), include_plotlyjs=False, full_html=False,
                            div_id=f"chart-{chart.id}", config=_CONFIG, default_height="320px")
    return html
