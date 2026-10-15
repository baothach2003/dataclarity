"""Thach's visual style (2026-10-15; docs/DASHBOARD_DESIGN.md section 11) in
report.html: the "OPERATIONAL DASHBOARD" reference's layout - a KPI row with a
small icon per tile, the chart cards, a strip of secondary KPIs - the
"STRATEGIC DASHBOARD" tile (the change under the figure), the dataviz skill's
validated palette in light and dark (selected, not flipped), green and red
for change only and always with the arrow, a second series only where two
months are compared, top products by sales with the value at the bar's end.
Failing tests first; the page's own in frontend/src/pages/InsightsVisual.test.tsx."""

import re
from pathlib import Path

import pytest

from contracts.report import ReportContract
from stages.report import html_dashboard
from stages.report.html_dashboard import DASHBOARD_STYLE, STRIP_TILES, TILE_ICONS
from stages.report.html_report import render_html
from tests.stages.report.test_dashboard_layout import _html, _real

ROOT = Path(__file__).resolve().parents[3]
ALL_FIVE = "demo_classed"  # sales, orders, AOV, customers, return rate


def _style(report: ReportContract) -> str:
    return re.search(r"<style>(.*?)</style>", _html(report), flags=re.S).group(1).replace("\n", "")


def _element(page: str, element_id: str) -> str:
    """The element with this id, to its matching close (sections and divs are not nested in themselves here
    beyond what the counter follows)."""
    start = page.index(f'id="{element_id}"')
    start = page.rindex("<", 0, start)
    tag = re.match(r"<(\w+)", page[start:]).group(1)
    depth, i = 0, start
    for match in re.finditer(rf"<(/?){tag}\b", page[start:]):
        depth += -1 if match.group(1) else 1
        if depth == 0:
            i = start + match.end()
            return page[start:page.index(">", i) + 1]
    raise AssertionError(f"{element_id} is not closed")


def _tiles_in(block: str) -> list[str]:
    return re.findall(r'data-tile="([a-z_]+)"', block)


# --- the layout: the main row, the cards, the strip ---------------------------------------------------------------

def test_the_main_row_holds_sales_orders_and_aov_and_the_strip_the_rest() -> None:
    page = _html(_real(ALL_FIVE))
    assert _tiles_in(_element(page, "tiles")) == ["sales", "orders", "aov"]
    assert _tiles_in(_element(page, "kpi-strip")) == ["customers", "return_rate"]
    # After the chart cards, before the bands (the reference's order).
    assert page.index('class="widgets"') < page.index('id="kpi-strip"') < page.index('id="band-next-month"')


def test_a_file_with_no_secondary_figure_has_no_strip() -> None:
    report = _real("kaggle")
    dashboard = report.dashboard.model_copy(update={"tiles": [t for t in report.dashboard.tiles
                                                              if t.id not in STRIP_TILES]})
    page = render_html(report.model_copy(update={"dashboard": dashboard}))
    assert 'id="kpi-strip"' not in page


def test_kaggle_has_customers_in_the_strip_and_no_return_rate() -> None:
    page = _html(_real("kaggle"))
    assert _tiles_in(_element(page, "kpi-strip")) == ["customers"]


def test_each_tile_has_a_small_neutral_decorative_icon() -> None:
    page = _html(_real(ALL_FIVE))
    for tile in re.findall(r'<div class="tile[^"]*" data-tile="[a-z_]+">.*?</svg>', page, flags=re.S):
        tile_id = re.search(r'data-tile="([a-z_]+)"', tile).group(1)
        svg = re.search(r"<svg[^>]*>.*?</svg>", tile, flags=re.S).group(0)
        assert 'aria-hidden="true"' in svg and 'class="ticon"' in svg and 'focusable="false"' in svg
        assert re.findall(r' d="([^"]+)"', svg) == list(TILE_ICONS[tile_id])
    rule = re.search(r"(?:^|\})\.ticon\{([^}]*)\}", DASHBOARD_STYLE.replace("\n", ""))
    assert rule is not None and "color:var(--ink2)" in rule.group(1) and "width:18px" in rule.group(1)


def test_the_change_stands_under_the_figure() -> None:
    page = _html(_real("kaggle"))
    sales = re.search(r'<div class="tile[^"]*" data-tile="sales">(.*?)</details>|<div class="tile[^"]*" '
                      r'data-tile="sales">(.*?)</div></div>', page, flags=re.S).group(0)
    assert sales.index('class="tv') < sales.index('class="tc')


# --- the palette, light and dark (selected) ---------------------------------------------------------------------

LIGHT = {"--surface": "#fcfcfb", "--s1": "#2a78d6", "--s2": "#eb6834", "--s3": "#1baf7a", "--up": "#0ca30c",
         "--down": "#d03b3b", "--tot": "#898781", "--ink2": "#52514e"}
DARK = {"--surface": "#1a1a19", "--s1": "#3987e5", "--s2": "#d95926", "--s3": "#199e70", "--up": "#0ca30c",
        "--down": "#d03b3b", "--tot": "#898781", "--ink2": "#c3c2b7"}


def _light(style: str) -> str:
    """The first plain `:root{...}` block: the light tokens (a dark block is scoped by a media query or a stamp)."""
    return re.search(r"(?:^|\})\s*:root\{(.*?)\}", style).group(1)


def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"(--[a-z0-9]+):(#[0-9a-f]{6})", block))


def test_the_light_and_dark_palettes_are_the_validated_ones() -> None:
    style = _style(_real("kaggle"))
    light = _light(style)
    assert {k: _tokens(light).get(k) for k in LIGHT} == LIGHT
    media = re.search(r'@media \(prefers-color-scheme:dark\)\{:root:not\(\[data-theme="light"\]\)\{(.*?)\}', style)
    assert media is not None, "dark mode by the reader's setting, a light stamp wins"
    assert {k: _tokens(media.group(1)).get(k) for k in DARK} == DARK
    stamped = re.search(r':root\[data-theme="dark"\]\{(.*?)\}', style)
    assert stamped is not None and {k: _tokens(stamped.group(1)).get(k) for k in DARK} == DARK


def test_red_is_never_a_main_colour() -> None:
    style = _style(_real("kaggle"))
    for block in (_light(style), style):
        tokens = _tokens(block)
        assert tokens.get("--accent") in (LIGHT["--s1"], DARK["--s1"])
        assert tokens.get("--s1") not in (LIGHT["--down"], "#e34948")


def test_up_and_down_colour_only_the_arrow_never_the_text() -> None:
    # Thach's Q10 (2026-10-16): the colour is the metric's polarity (test_q10_* below), still on the arrow alone.
    style = DASHBOARD_STYLE.replace("\n", "")
    assert ".arrow.good{color:var(--up)}" in style and ".arrow.bad{color:var(--down)}" in style
    assert ".arrow.same{color:var(--ink2)}" in style
    assert ".tc{" in style and "color:var(--ink2)" in style.split(".tc{")[1].split("}")[0]
    page = _html(_real("kaggle"))
    sales = page[page.index('data-tile="sales"'):]
    assert re.search(r'<span class="arrow up good" role="img" aria-label="higher than last month">&#9650;</span>',
                     sales)


def test_bars_wear_the_series_colours_and_the_waterfall_the_change_colours() -> None:
    style = _style(_real("kaggle"))
    assert ".hb-bar.now{background:var(--s1)}" in style and ".hb-bar.was{background:var(--s2)}" in style
    assert ".series{fill:none;stroke:var(--s1)" in style
    assert ".wf .up{fill:var(--up)}" in style and ".wf .down{fill:var(--down)}" in style
    assert ".wf .tot{fill:var(--tot)}" in style
    assert ".p0{background:var(--s1)}" in style and ".p1{background:var(--s2)}" in style
    assert ".p2{background:var(--s3)}" in style


@pytest.mark.parametrize("run", ["kaggle", "demo_classed", "demo_unanswered"])
def test_no_chart_draws_a_change_colour_beside_the_second_series(run: str) -> None:
    # Red sits too close to orange (the validator: deltaE 10.8 light, 6.8 dark): never in one chart.
    page = _html(_real(run))
    for card in re.findall(r'<section id="[a-z0-9-]+" class="card widget chart">.*?</section>', page, flags=re.S):
        if "hb-bar was" in card:
            assert "hb-bar up" not in card and "hb-bar down" not in card


# --- the charts ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("run", ["kaggle", "demo_classed", "demo_unanswered"])
def test_a_chart_of_two_months_has_a_legend(run: str) -> None:
    page = _html(_real(run))
    for card in re.findall(r'<section id="[a-z0-9-]+" class="card widget chart">.*?</section>', page, flags=re.S):
        if "hb-bar was" in card:
            legend = re.search(r'<ul class="legend2">(.*?)</ul>', card, flags=re.S)
            assert legend is not None, card[:120]
            assert re.findall(r'<span class="sw (s1|s2)"></span>([^<]+)</li>', legend.group(1)) == [
                ("s1", "This month"), ("s2", "Last month")]


@pytest.mark.parametrize("run", ["kaggle", "demo_classed"])
def test_top_products_by_sales_with_the_value_at_the_bars_end(run: str) -> None:
    report = _real(run)
    products = next(w for w in report.dashboard.widgets if w.id == "products")
    assert [b.now for b in products.bars] == sorted((b.now for b in products.bars), reverse=True)
    card = _element(_html(report), "products")
    rows = re.findall(r'<li class="hb-row end"[^>]*>(.*?)</li>', card, flags=re.S)
    assert len(rows) == len(products.bars)
    for row, bar in zip(rows, products.bars, strict=True):
        # The bar, then its value right after it, in one track.
        track = re.search(r'<span class="hb-track end">(.*?)</span></span>', row + "</span>", flags=re.S)
        assert track is not None and re.search(r'<span class="hb-fill" style="--w:[0-9.]+"></span><span '
                                               r'class="hb-val">' + re.escape(bar.now_text.replace("&", "&amp;")),
                                               row)
    assert not re.search(r"quantit|units|\bqty\b", card, flags=re.I)


def test_the_value_at_the_end_keeps_one_scale() -> None:
    # The longest bar is the scale's whole (--w:1), the rest in proportion: a layout width, no printed figure.
    card = _element(_html(_real("kaggle")), "products")
    widths = [float(w) for w in re.findall(r'class="hb-fill" style="--w:([0-9.]+)"', card)]
    bars = next(w for w in _real("kaggle").dashboard.widgets if w.id == "products").bars
    assert widths[0] == 1.0
    assert widths == pytest.approx([b.now / bars[0].now for b in bars], abs=1e-4)


@pytest.mark.parametrize("run", ["kaggle", "demo_classed"])
def test_each_waterfall_bar_carries_its_arrow(run: str) -> None:
    report = _real(run)
    svg = re.search(r'<svg[^>]*class="wf".*?</svg>', _html(report), flags=re.S).group(0)
    for bar in report.front.waterfall.bars:
        arrow = "&#9650;" if bar.shown > 0 else "&#9660;" if bar.shown < 0 else ""
        kind = "up" if bar.shown > 0 else "down" if bar.shown < 0 else "flat"
        assert re.search(rf'class="{kind}"/><text[^>]*class="val"[^>]*>{re.escape(arrow)}\s?'
                         + re.escape(bar.worth.replace("&", "&amp;")), svg), bar.label


@pytest.mark.parametrize("run", ["kaggle", "demo_classed"])
def test_each_bar_row_has_a_hover_title(run: str) -> None:
    page = _html(_real(run))
    rows = re.findall(r'<li class="hb-row[^"]*"([^>]*)>', page)
    assert rows and all(re.match(r' title="[^"]+: [^"]+"', attrs) for attrs in rows)


# --- one copy: the page draws the same (D7) -----------------------------------------------------------------------

def test_the_page_has_the_same_icons_and_the_same_strip() -> None:
    source = (ROOT / "frontend" / "src" / "components" / "dashboardIcons.ts").read_text(encoding="utf-8")
    page_icons = {tile: re.findall(r"'([^']+)'", body)
                  for tile, body in re.findall(r"^  ([a-z_]+): \[(.*?)\],?$", source, flags=re.M)}
    assert page_icons == {tile: list(paths) for tile, paths in TILE_ICONS.items()}
    strip = re.search(r"export const STRIP_TILES[^=]*= \[(.*?)\]", source).group(1)
    assert re.findall(r"'([a-z_]+)'", strip) == list(STRIP_TILES)


def test_the_page_tokens_are_the_same_palette() -> None:
    tokens = (ROOT / "frontend" / "src" / "styles" / "tokens.css").read_text(encoding="utf-8").replace("\n", " ")
    page_light = {"--chart-surface": LIGHT["--surface"], "--series-1": LIGHT["--s1"], "--series-2": LIGHT["--s2"],
                  "--series-3": LIGHT["--s3"], "--change-up": LIGHT["--up"], "--change-down": LIGHT["--down"],
                  "--change-total": LIGHT["--tot"]}
    light = tokens.split("@media")[0]
    assert {k: re.search(rf"{k}:\s*(#[0-9a-f]{{6}})", light).group(1) for k in page_light} == page_light
    dark = re.search(r'@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{(.*?)\}',
                     tokens).group(1)
    page_dark = {"--chart-surface": DARK["--surface"], "--series-1": DARK["--s1"], "--series-2": DARK["--s2"],
                 "--series-3": DARK["--s3"], "--change-up": DARK["--up"], "--change-down": DARK["--down"],
                 "--change-total": DARK["--tot"]}
    assert {k: re.search(rf"{k}:\s*(#[0-9a-f]{{6}})", dark).group(1) for k in page_dark} == page_dark
    assert ':root[data-theme="dark"]' in tokens


def test_nothing_new_is_imported_into_report_html() -> None:
    # Inline only (no network): the icons are paths in the page, the palette is CSS.
    assert "http" not in "".join(TILE_ICONS[t][0] for t in TILE_ICONS)
    assert html_dashboard.__all__.count("STRIP_TILES") == 1


# --- mutation's survivors (each its own test) ---------------------------------------------------------------------

def test_a_chart_of_two_months_keeps_the_value_above_its_bar_and_last_months_marker() -> None:
    card = _element(_html(_real("kaggle")), "category")
    assert "hb-bar was" in card and 'class="hb-row end"' not in card and '<ul class="legend2">' in card


def test_one_series_with_a_negative_value_keeps_the_zero_line() -> None:
    from contracts.report_dashboard import Bar
    from stages.report.html_bars import bar_chart

    bars = [Bar(label="Till", now=400.0, was=None, now_text="400.00", was_text=None, is_blank=False),
            Bar(label="Returns desk", now=-100.0, was=None, now_text="-100.00", was_text=None, is_blank=False)]
    chart = bar_chart(bars, "Sales by Desk", None)
    assert "hb-row end" not in chart and "hb-zero" in chart
    left = float(re.search(r'hb-bar now" style="left:([0-9.]+)%', chart.split("Returns desk")[-1]).group(1))
    zero = float(re.search(r'hb-zero" style="left:([0-9.]+)%', chart.split("Returns desk")[-1]).group(1))
    assert left < zero


# --- the display review's findings (each reproduced first) ------------------------------------------------------------

APP_CSS = ROOT / "frontend" / "src" / "styles" / "app.css"


def _css_rule(css: str, selector: str) -> str:
    match = re.search(r"(?:^|\}|\*/)\s*" + re.escape(selector) + r"\s*\{([^}]*)\}", css)
    assert match is not None, selector
    return match.group(1)


def test_r2_the_checklists_marks_are_the_same_on_the_page() -> None:
    # report.html: "pulled the other way" in the secondary ink (red is for change only), "matches" in the series.
    css = APP_CSS.read_text(encoding="utf-8")
    assert "var(--text-secondary)" in _css_rule(css, ".front-check--against li::before")
    assert "var(--series-1)" in _css_rule(css, ".front-check--yes li::before")
    style = _style(_real("kaggle"))
    assert r'.against li::before{content:"\2193";color:var(--ink2)}' in style


@pytest.mark.parametrize("component", ["FrontSalesChart", "FrontWaterfall", "RevenueChartCard", "ForecastCard"])
def test_r3_the_pages_chart_axes_and_tooltips_wear_the_tokens(component: str) -> None:
    # Recharts' defaults are #666 ticks and a white tooltip whose label inherits the page's ink: unreadable dark.
    source = (ROOT / "frontend" / "src" / "components" / f"{component}.tsx").read_text(encoding="utf-8")
    for axis in re.findall(r"<[XY]Axis\b.*?/>", source, flags=re.S):
        assert "fill: 'var(--text-secondary)'" in axis, axis
    for tooltip in re.findall(r"<Tooltip\b.*?/>", source, flags=re.S):
        assert "contentStyle={TOOLTIP_STYLE}" in tooltip and "labelStyle={TOOLTIP_LABEL}" in tooltip, tooltip


def test_r4_error_text_is_readable_in_dark() -> None:
    tokens = (ROOT / "frontend" / "src" / "styles" / "tokens.css").read_text(encoding="utf-8").replace("\n", " ")
    dark = re.search(r'@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{(.*?)\}',
                     tokens).group(1)
    # The reference's red slot, dark step: 5.0:1 on #1a1a19 (#d03b3b was 3.62:1 as text).
    assert re.search(r"--severity-high:\s*#e66767", dark)


def test_r5_report_htmls_own_inks_follow_the_theme() -> None:
    style = _style(_real("kaggle"))
    assert ".meta,.reason{color:var(--ink2)}" in style and ".caution{color:var(--caution)}" in style
    assert ".note{border-left-color:var(--line)}" in style
    light, dark = _light(style), re.search(r':root\[data-theme="dark"\]\{(.*?)\}', style).group(1)
    assert "--caution:#7a5200" in light and "--caution:#f0c060" in dark
    assert "color-scheme:light" in light and "color-scheme:dark" in dark


def test_r6_the_icon_stands_in_the_label_row_never_beside_the_figure() -> None:
    page = _html(_real("demo_classed"))
    for tile in re.findall(r'<div class="tile" data-tile="[a-z_]+">.*?</div>', page, flags=re.S):
        assert re.match(r'<div class="tile" data-tile="[a-z_]+"><div class="tl"><svg class="ticon"', tile), tile[:120]
    assert "grid-template-columns:auto minmax(0,1fr)" not in DASHBOARD_STYLE.replace("\n", "")


def test_r8_a_waterfall_part_printed_as_zero_has_no_arrow() -> None:
    from stages.report.html_svg import waterfall_chart

    report = _real("kaggle")
    waterfall = report.front.waterfall
    bar = waterfall.bars[0].model_copy(update={"shown": -0.004, "worth": "0.00"})
    svg = waterfall_chart(waterfall.model_copy(update={"bars": [bar, *waterfall.bars[1:]]}))
    assert re.search(r'class="flat"/><text[^>]*class="val"[^>]*>0\.00<', svg)


# --- its scoped review's findings ------------------------------------------------------------------------------------

def test_s1_figures_line_up_across_a_row_whatever_the_labels_length() -> None:
    # A label of three lines beside one of two: the label grows, so each figure sits at its tile's foot.
    style = DASHBOARD_STYLE.replace("\n", "")
    assert re.search(r"\.tile\{[^}]*display:flex;flex-direction:column", style)
    assert ".tl{display:flex;align-items:flex-start;gap:8px;flex:1 0 auto}" in style
    css = APP_CSS.read_text(encoding="utf-8")
    label = _css_rule(css, ".tile__label")
    assert "flex: 1 0 auto" in label and "align-items: flex-start" in label and "gap: var(--space-2)" in label


# --- Thach's Q10 (2026-10-16): the arrow's colour by the metric's fixed polarity ---------------------------------------
# Polarity is a property of the metric, not a verdict on the month (ADR-0007 unaffected): sales, orders, average
# order value and customers up = good (green); the return rate down = good (green). The arrow's shape stays the meaning.

def _arrow_classes(page: str, tile_id: str) -> str:
    tile = page[page.index(f'data-tile="{tile_id}"'):]
    return re.search(r'<span class="(arrow [^"]+)" role="img"', tile).group(1)


def test_q10_the_polarity_table_is_fixed_per_metric() -> None:
    from typing import get_args

    from contracts.report_dashboard import TileId
    from stages.report.html_dashboard import TILE_POLARITY

    assert TILE_POLARITY == {"sales": 1, "orders": 1, "aov": 1, "customers": 1, "return_rate": -1}
    assert set(TILE_POLARITY) == set(get_args(TileId))


def test_q10_a_falling_return_rate_is_green_a_falling_average_red() -> None:
    page = _html(_real(ALL_FIVE))  # the demo: return rate 0.169 -> 0.152, AOV down, the rest up
    assert _arrow_classes(page, "return_rate") == "arrow down good"
    assert _arrow_classes(page, "aov") == "arrow down bad"
    for tile_id in ("sales", "orders", "customers"):
        assert _arrow_classes(page, tile_id) == "arrow up good"
    # The arrow keeps its shape and its words: the direction, never a verdict.
    tile = page[page.index('data-tile="return_rate"'):]
    assert re.search(r'aria-label="lower than last month">&#9660;</span>', tile)


@pytest.mark.parametrize(("tile_id", "direction", "tone"), [
    ("return_rate", "up", "bad"), ("return_rate", "down", "good"), ("customers", "down", "bad"),
    ("sales", "down", "bad"), ("orders", "up", "good"), ("return_rate", "same", None), ("sales", "same", None)])
def test_q10_each_direction_and_polarity(tile_id: str, direction: str, tone: str | None) -> None:
    report = _real(ALL_FIVE)
    tile = next(t for t in report.dashboard.tiles if t.id == tile_id).model_copy(update={"direction": direction})
    html = html_dashboard._tile(tile, html_dashboard.note_texts(report))
    classes = re.search(r'<span class="(arrow [^"]+)" role="img"', html).group(1)
    assert classes == (f"arrow {direction} {tone}" if tone else f"arrow {direction}")


def test_q10_the_colours_follow_the_tone_never_the_direction_alone() -> None:
    style = DASHBOARD_STYLE.replace("\n", "")
    assert ".arrow.up{" not in style and ".arrow.down{" not in style
    css = APP_CSS.read_text(encoding="utf-8")
    assert "var(--change-up)" in _css_rule(css, ".tile__arrow--good")
    assert "var(--change-down)" in _css_rule(css, ".tile__arrow--bad")
    assert "var(--text-secondary)" in _css_rule(css, ".tile__arrow--same")
    assert not re.search(r"\.tile__arrow--(up|down)\s*\{", css)


def test_q10_the_page_has_the_same_polarity_table() -> None:
    from stages.report.html_dashboard import TILE_POLARITY

    source = (ROOT / "frontend" / "src" / "components" / "dashboardIcons.ts").read_text(encoding="utf-8")
    body = re.search(r"export const TILE_POLARITY[^=]*= \{(.*?)\}", source, flags=re.S).group(1)
    assert {k: int(v) for k, v in re.findall(r"([a-z_]+): (-?1)", body)} == TILE_POLARITY


def test_q10_no_direction_draws_no_arrow() -> None:
    # Its review's nit: a tile with nothing to compare has no arrow, so no tone.
    report = _real(ALL_FIVE)
    tile = next(t for t in report.dashboard.tiles if t.id == "return_rate")
    html = html_dashboard._tile(tile.model_copy(update={"direction": None}), html_dashboard.note_texts(report))
    assert 'class="arrow' not in html


def test_q10_orders_worded_as_lines_keep_their_polarity() -> None:
    # Its review's nit: a file with no order id words the orders tile "Lines" - the id, so the polarity, stays.
    report = _real(ALL_FIVE)
    tile = next(t for t in report.dashboard.tiles if t.id == "orders")
    tile = tile.model_copy(update={"label": "Lines", "direction": "down"})
    html = html_dashboard._tile(tile, html_dashboard.note_texts(report))
    assert re.search(r'<span class="arrow down bad" role="img"', html)
