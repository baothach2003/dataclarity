"""The dashboard's step 3 (Thach's D2, D3, D6, D7, 2026-10-14;
docs/DASHBOARD_DESIGN.md sections 2-4, 8): report.json 2.10's `dashboard`
block - the KPI tiles and the widgets in the order code decides - and
report.html drawing it. Symptom tests first: each failed before the block
existed. Expected figures are the real runs' own fields (fixtures/) or worked
by hand in the comments."""

import copy
import re
from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import CleaningReportContract
from contracts.report import ReportContract
from contracts.report_front import FRONT_BANNED
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.assemble import diagnose
from stages.diagnose.inputs import build_run_data
from stages.predict.assemble import predict
from stages.report.builder import SCHEMA_VERSION, build_report
from stages.report.html_dashboard import SECTION_IDS
from stages.report.html_report import render_html
from tests.contracts.test_cleaning import report_payload as cleaning_report_payload
from tests.scenarios.scenarios import s0, s4, s6, s10
from tests.scenarios.store import MAPPING as STORE
from tests.stages.report.html_probe import Page
from tests.stages.report.real_runs import build_real, files

NOW = datetime(2026, 10, 1, tzinfo=UTC)
TEXT = ["summary", "checklist", "next_steps", "next_month", "cannot_know"]
# The illustrative breakdowns of the design's mock: the Kaggle run's Location and Payment Method, by stage 2's
# definition (members sum to 46,292.50 and 41,367.50).
KAGGLE_SPLITS = [
    {"column": "Location", "change_reason": None, "withheld_reason": None, "members": [
        {"name": "In-store", "is_blank": False, "revenue_current": 25469.5, "revenue_previous": 17704.0,
         "change": 7765.5},
        {"name": "Online", "is_blank": False, "revenue_current": 20823.0, "revenue_previous": 23663.5,
         "change": -2840.5}]},
    {"column": "Payment Method", "change_reason": None, "withheld_reason": None, "members": [
        {"name": "Cash", "is_blank": False, "revenue_current": 15916.5, "revenue_previous": 13492.0, "change": 2424.5},
        {"name": "Credit Card", "is_blank": False, "revenue_current": 14575.5, "revenue_previous": 13706.5,
         "change": 869.0},
        {"name": "Digital Wallet", "is_blank": False, "revenue_current": 15800.5, "revenue_previous": 14169.0,
         "change": 1631.5}]}]


def _ids(report: ReportContract) -> tuple[list[str], list[str]]:
    dashboard = report.dashboard
    assert dashboard is not None
    return [t.id for t in dashboard.tiles], [w.id for w in dashboard.widgets]


def _kaggle_with_splits() -> ReportContract:
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["schema_version"] = "16.3"
    metrics["by_dimension"]["breakdowns"] = copy.deepcopy(KAGGLE_SPLITS)
    cleaning = files("kaggle")["cleaning_report.json"] | {"breakdowns": ["Location", "Payment Method"]}
    return build_real("kaggle", metrics=metrics, cleaning=cleaning)


def _pipeline(frame: pd.DataFrame, mapping: dict[str, str] = STORE, breakdowns: list[str] | None = None,
              ) -> ReportContract:
    metrics = assemble_metrics(frame, mapping, now=NOW, breakdowns=breakdowns or [])
    diagnosis = diagnose(build_run_data(frame, mapping, metrics), NOW)
    forecast = predict(metrics, diagnosis, NOW).contract
    cleaning = CleaningReportContract.model_validate(cleaning_report_payload() | {"column_mapping": mapping,
                                                                                  "breakdowns": breakdowns or []})
    return build_report(run_id="0c000000-0000-4000-8000-000000000003", source_file="store.csv", metrics=metrics,
                        diagnosis=diagnosis, forecast=forecast, cleaning=cleaning, schema=None, plan_source=None,
                        now=NOW)


# --- the tiles (D2) --------------------------------------------------------------------------------------------


def test_the_version_is_2_10() -> None:
    assert SCHEMA_VERSION == "2.10"  # 2.10: the dashboard block (2026-10-14)


def test_kaggle_tiles_are_sales_orders_order_value_and_customers() -> None:
    tiles = {t.id: t for t in build_real("kaggle").dashboard.tiles}

    assert list(tiles) == ["sales", "orders", "aov", "customers"]  # no return line in the file: no return rate
    sales = tiles["sales"]
    # Sentence A's own figures: 46,292.50, up 4,925.00 (+11.9%) on November 2024.
    assert (sales.label, sales.now, sales.change, sales.direction) == (
        "Sales", "46,292.50", "+4,925.00 (+11.9%) on November 2024", "up")
    assert (tiles["orders"].label, tiles["orders"].now, tiles["orders"].was, tiles["orders"].direction) == (
        "Orders", "343", "308", "up")
    assert (tiles["aov"].label, tiles["aov"].now, tiles["aov"].was) == ("Average order value", "134.96", "134.31")
    # The bridge's count of customers who placed an order (Thach's Q4), 25 in both months.
    assert (tiles["customers"].label, tiles["customers"].now, tiles["customers"].was,
            tiles["customers"].direction) == ("Customers who placed an order", "25", "25", "same")
    assert all(t.change is None for t in tiles.values() if t.id != "sales")  # no computed change (CONTRACTS 11)


def test_online_retail_has_the_return_rate_as_a_ratio_never_a_percentage() -> None:
    tiles = {t.id: t for t in build_real("demo_classed").dashboard.tiles}

    assert list(tiles) == ["sales", "orders", "aov", "customers", "return_rate"]
    rate = tiles["return_rate"]
    assert (rate.label, rate.now, rate.was, rate.direction, rate.unit) == (
        "Orders with a return, per order sold", "0.152", "0.169", "down", "ratio")
    assert (tiles["customers"].now, tiles["customers"].was) == ("756", "609")
    assert tiles["sales"].change == "+141,755.41 (+27.2%) on October 2011"


def test_a_file_with_no_order_id_and_no_customer_says_lines_and_has_no_customer_tile() -> None:
    frame = s0(1).drop(columns=["Invoice", "Customer", "Category"])
    mapping = {k: v for k, v in STORE.items() if k in frame.columns}
    dashboard = _pipeline(frame, mapping).dashboard

    tiles = {t.id: t for t in dashboard.tiles}
    assert "customers" not in tiles and not any("ustomer" in line for line in dashboard.not_shown)
    assert (tiles["orders"].label, tiles["aov"].label) == ("Lines", "Average line value")


def test_an_incomplete_previous_month_shows_this_month_alone_with_the_reason() -> None:
    # The hand-built report whose previous month the file covers only in part (stage 2's period; stage 3 does
    # not block it): this month alone.
    from tests.contracts.test_metrics_reasons import _partial
    from tests.stages.report.report_fixtures import build, metrics_data

    report = build(metrics=_partial(metrics_data()))
    dashboard = report.dashboard
    previous = report.layer_1_numbers.period.previous
    month = f"{__import__('calendar').month_name[int(previous[5:])]} {previous[:4]}"

    assert dashboard.state == "not_compared"
    assert all(t.was is None and t.change is None and t.direction is None for t in dashboard.tiles)
    assert dashboard.tiles[0].reason == f"Not compared with {month}: the file does not cover {month} whole."
    assert not {"waterfall", "customers", "products", "returns", "checklist", "next_steps"} & set(_ids(report)[1])
    assert all(w.size is None for w in dashboard.widgets)
    assert not any("ustomers who placed" in t.label for t in dashboard.tiles)


def test_no_tile_is_shown_without_a_figure() -> None:
    for run in ("kaggle", "demo_classed", "demo_unanswered"):
        for tile in build_real(run).dashboard.tiles:
            assert tile.now is not None and tile.now_value is not None, (run, tile.id)


# --- the order rule (D3) -----------------------------------------------------------------------------------------


def test_kaggle_leads_with_the_change_split_its_named_cause_draws() -> None:
    _, widgets = _ids(build_real("kaggle"))
    # B1 named (rule 6) -> the waterfall, which draws B1's bar; then by size: the change 4,925.00, the category
    # 2,562.50 (stage 3's largest category move); then the unsized in the fixed order - the summary, this
    # month's best sellers (stage 2's list, no movement: step 3's review), the rest of the text. No customers
    # widget: new, back and stopped buying are 0.00 in both months.
    assert widgets == ["waterfall", "trend", "category", *TEXT]
    placed = {w.id: w.placed_by for w in build_real("kaggle").dashboard.widgets}
    assert placed["waterfall"] == "named" and placed["trend"] == "size" and placed["summary"] == "fallback"


def test_kaggle_with_two_breakdowns_places_each_by_its_largest_move() -> None:
    report = _kaggle_with_splits()
    _, widgets = _ids(report)
    # Location's largest move +7,765.50 (in-store) comes before the change itself; Payment Method's +2,424.50
    # (cash) after the category's 2,562.50.
    assert widgets == ["waterfall", "breakdown_1", "trend", "category", "breakdown_2", *TEXT]
    by_id = {w.id: w for w in report.dashboard.widgets}
    location, payment = by_id["breakdown_1"], by_id["breakdown_2"]
    assert (location.title, location.column, location.chart, location.size) == (
        "Sales by Location", "Location", "parts", 7765.5)
    assert [(b.label, b.now_text, b.was_text) for b in location.bars] == [
        ("In-store", "25,469.50", "17,704.00"), ("Online", "20,823.00", "23,663.50")]
    assert payment.chart == "parts" and [b.label for b in payment.bars] == ["Cash", "Digital Wallet", "Credit Card"]


def test_online_retail_has_no_named_cause_so_the_largest_move_leads() -> None:
    for run in ("demo_classed", "demo_unanswered"):
        report = build_real(run)
        _, widgets = _ids(report)
        assert widgets == ["trend", "waterfall", "customers", "returns", *TEXT], run


def test_no_products_widget_is_drawn_the_stop_rules_element_hidden() -> None:
    # Thach's stop rule (2026-10-14): the products widget fabricated on a demo file twice - "moved most" over
    # stage 3's larger members only (Kaggle), then DOTCOM POSTAGE, a suggested charge, as Online Retail II's
    # top product without its mark (the scoped review) - so it is not shown, on any run, in report.json or the page.
    for run in ("kaggle", "demo_classed", "demo_unanswered"):
        report = build_real(run)
        assert "products" not in _ids(report)[1], run
        page = Page(render_html(report))
        assert "products" not in [attrs["id"] for attrs in page.named("section")], run
        assert "DOTCOM POSTAGE" not in page.front_text and "Products with the most sales" not in page.front_text


def test_lapsed_customers_lead_with_the_customers_widget() -> None:
    _, widgets = _ids(_pipeline(s4(1)))  # rule 6, C2 named
    assert widgets[0] == "customers"


def test_offsetting_moves_lead_with_the_change_split() -> None:
    _, widgets = _ids(_pipeline(s6(1)))  # rule 4
    assert widgets[0] == "waterfall"


def test_the_caution_stands_under_the_tiles() -> None:
    report = _pipeline(s10(1))  # every September price x100: D2 cautions
    assert report.dashboard.caution and report.dashboard.caution == report.front.caution
    page = render_html(report)
    tiles_at, caution_at = page.index('id="tiles"'), page.index(report.dashboard.caution[0].split(":")[0])
    first_widget = page.index('class="card widget')
    assert tiles_at < caution_at < first_widget


def test_a_blocked_report_draws_no_chart() -> None:
    # Half of September with no line at all: D1 blocks the comparison.
    frame = s0(1)
    frame = frame[~frame["Date"].between("2023-09-01", "2023-09-18")].reset_index(drop=True)
    report = _pipeline(frame)

    assert report.dashboard.state == "blocked"
    assert _ids(report)[1] == ["summary", "next_month", "cannot_know"]
    assert all(t.was is None and t.change is None for t in report.dashboard.tiles)
    assert report.dashboard.tiles[0].reason == "Not compared: the data checks did not pass - see Technical details."


# --- words (D7, the front's rules) ----------------------------------------------------------------------------


def test_no_banned_word_in_any_tile_title_caption_or_line() -> None:
    for report in (build_real("kaggle"), build_real("demo_classed"), _kaggle_with_splits()):
        dashboard = report.dashboard
        words = [t.label for t in dashboard.tiles] + [t.change or "" for t in dashboard.tiles]
        words += [t.reason or "" for t in dashboard.tiles] + dashboard.not_shown
        words += [w.title or "" for w in dashboard.widgets] + [c for w in dashboard.widgets for c in w.caption]
        text = " ".join(words).lower()
        assert not [word for word in FRONT_BANNED if re.search(rf"\b{re.escape(word)}", text)]


def test_no_front_sentence_points_at_a_section_number() -> None:
    for run in ("kaggle", "demo_classed", "demo_unanswered"):
        text = Page(render_html(build_real(run))).text
        assert not re.search(r"\bsection \d", text), run


def test_with_a_breakdown_drawn_cannot_know_names_it() -> None:
    report = _kaggle_with_splits()
    split = next(item for item in report.front.cannot_know if item.title.startswith("Sales by channel"))
    assert "does not split sales" not in split.text
    assert "Location" in split.text and "Payment Method" in split.text


# --- report.html draws the block (D7) ---------------------------------------------------------------------------


def test_report_html_draws_the_tiles_then_the_widgets_in_the_blocks_order() -> None:
    report = _kaggle_with_splits()
    page = render_html(report)
    probe = Page(page)
    widget_ids = [attrs["id"] for attrs in probe.named("section") if (attrs.get("class") or "").startswith("card widget")]
    assert widget_ids == [SECTION_IDS[w.id] for w in report.dashboard.widgets]
    tiles = probe.section("tiles")
    assert tiles.index("Sales") < tiles.index("Orders") < tiles.index("Average order value")
    assert "+4,925.00 (+11.9%) on November 2024" in tiles
    assert "Sales by Location" in probe.section("breakdown-1")
    assert page.index('id="tiles"') < page.index('id="appendix"')


def test_a_report_before_2_10_still_renders_its_front() -> None:
    data = build_real("kaggle").model_dump(mode="json")
    data["schema_version"] = "2.9"
    del data["dashboard"]
    page = render_html(ReportContract.model_validate(data))
    assert 'id="tiles"' not in page and 'id="summary"' in page


def test_a_2_10_report_without_its_dashboard_is_refused() -> None:
    data = build_real("kaggle").model_dump(mode="json")
    del data["dashboard"]
    with pytest.raises(ValueError, match="dashboard"):
        ReportContract.model_validate(data)


# --- the rules one by one (mutation: each branch its own test) ---------------------------------------------------


def _real_parts(run: str):
    from contracts.cleaning import CleaningReportContract as Cleaning
    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract

    data = files(run)
    report = build_real(run)
    return (report, MetricsContract.model_validate(data["metrics.json"]),
            DiagnosisContract.model_validate(data["diagnosis.json"]),
            Cleaning.model_validate(data["cleaning_report.json"]))


def test_an_order_value_with_no_figure_is_no_tile_and_says_why() -> None:
    from stages.report.dashboard import tiles

    report, metrics, diagnosis, cleaning = _real_parts("kaggle")
    numbers = report.layer_1_numbers
    kpis = [k.model_copy(update={"current": None, "current_reason": "no order"}) if k.id == "aov" else k
            for k in numbers.kpis]
    found, not_shown = tiles(numbers.model_copy(update={"kpis": kpis}), report.front, metrics, diagnosis, cleaning,
                             None)
    assert "aov" not in [t.id for t in found]
    assert not_shown == ["Average order value is not shown this month - see Technical details for why."]


def test_no_customer_tile_beside_a_month_not_compared_even_with_the_bridges_count() -> None:
    from stages.report.dashboard import tiles

    report, metrics, diagnosis, cleaning = _real_parts("kaggle")
    front = report.front.model_copy(update={"state": "not_compared"})
    found, not_shown = tiles(report.layer_1_numbers, front, metrics, diagnosis, cleaning, None)
    assert "customers" not in [t.id for t in found]
    assert not_shown == ["Customers who placed an order are not shown: this month is not compared with the last."]


def test_returns_last_month_only_still_show_the_return_rate() -> None:
    from stages.report.dashboard import _has_returns

    _, metrics, _, _ = _real_parts("demo_classed")
    identity = metrics.core.identity
    now_none = identity.model_copy(update={"current": identity.current.model_copy(update={"returns": 0.0})})
    changed = metrics.model_copy(update={"core": metrics.core.model_copy(update={"identity": now_none})})
    assert _has_returns(changed, compared=True) is True
    assert _has_returns(changed, compared=False) is False


@pytest.mark.parametrize(("rule", "named", "tied"), [
    (6, ["T1", "B1"], "waterfall"),  # the first named cause with a widget leads (T1 has none)
    (5, ["T2"], "trend"),            # rule 5 names the time of year: the months
    (4, None, "waterfall"),          # the offsetting pair is the change's split
    (7, None, None), (2, None, None)])
def test_the_widget_tied_to_the_named_cause(rule: int, named: list[str] | None, tied: str | None) -> None:
    from stages.report.dashboard import _tied

    _, _, diagnosis, _ = _real_parts("kaggle")
    headline = diagnosis.headline.model_copy(update={"rule": rule, "named": named, "hypothesis_id": None})
    draws = {"waterfall": {"B1", "B2", "P1", "P2"}, "trend": {"T2"}, "customers": {"C1", "C3"}, "returns": {"P3"}}
    assert _tied(diagnosis.model_copy(update={"headline": headline}), draws, compared=True) == tied
    assert _tied(diagnosis.model_copy(update={"headline": headline}), draws, compared=False) is None


def test_a_widget_that_does_not_draw_the_named_cause_is_no_tie() -> None:
    # Step 3's review #8: C2 named, but its term is no loss, so the customers widget does not draw it.
    from stages.report.dashboard import _tied

    _, _, diagnosis, _ = _real_parts("kaggle")
    headline = diagnosis.headline.model_copy(update={"rule": 6, "named": ["C2"], "hypothesis_id": None})
    assert _tied(diagnosis.model_copy(update={"headline": headline}), {"customers": {"C1", "C3"}}, True) is None
    assert _tied(diagnosis.model_copy(update={"headline": headline}), {"customers": {"C2"}}, True) == "customers"


def test_a_file_with_no_order_id_says_customers_who_bought() -> None:
    frame = s0(1).drop(columns=["Invoice"])
    mapping = {k: v for k, v in STORE.items() if k in frame.columns}
    tiles = {t.id: t for t in _pipeline(frame, mapping).dashboard.tiles}
    assert tiles["customers"].label == "Customers who bought" and tiles["orders"].label == "Lines"


def test_a_negative_part_is_never_drawn_as_a_part_of_a_whole() -> None:
    from contracts.report_dashboard import Bar
    from stages.report.dashboard_widgets import _split_chart

    def bar(now: float, was: float | None = None) -> Bar:
        return Bar(label=f"{now}", now=now, was=was, now_text=f"{now:.2f}", was_text=None if was is None else f"{was:.2f}")

    assert _split_chart([bar(5.0, 4.0), bar(3.0, 2.0)]) == "parts"
    assert _split_chart([bar(5.0, 4.0), bar(-1.0, 2.0)]) == "bars"
    assert _split_chart([bar(5.0, 4.0), bar(1.0, -2.0)]) == "bars"
    assert _split_chart([bar(1.0), bar(2.0), bar(3.0), bar(4.0)]) == "bars"


def test_a_single_month_is_no_line() -> None:
    from contracts.report import Chart, ChartSeries
    from stages.report.dashboard_widgets import chart_widgets

    report, metrics, diagnosis, cleaning = _real_parts("kaggle")
    one = Chart(id="revenue_trend", type="line", title="t", notes=[], note=None, cautions=[],
                series=[ChartSeries(name="revenue", x=["2024-11", "2024-12"], y=[None, 46292.5])])
    found = chart_widgets(metrics=metrics, diagnosis=diagnosis, cleaning=cleaning, front=report.front,
                          charts=[one], notes=[], code=None, compared=True, has_returns=False)
    assert "trend" not in [w.id for w in found.widgets]


# --- step 3's review, each fix its test ----------------------------------------------------------------------------


def _kaggle_split(members: list[dict], withheld: str | None = None) -> ReportContract:
    metrics = copy.deepcopy(files("kaggle")["metrics.json"])
    metrics["schema_version"] = "16.3"
    metrics["by_dimension"]["breakdowns"] = [{"column": "Desk", "change_reason": None, "withheld_reason": withheld,
                                              "members": members}]
    cleaning = files("kaggle")["cleaning_report.json"] | {"breakdowns": ["Desk"]}
    return build_real("kaggle", metrics=metrics, cleaning=cleaning)


def test_a_negative_value_is_drawn_left_of_zero_never_like_a_sale() -> None:
    # Review 3 #2: a returns desk netting -2,000.00 was a rightward bar like a sale.
    report = _kaggle_split([
        {"name": "Returns desk", "is_blank": False, "revenue_current": -2000.0, "revenue_previous": -500.0,
         "change": -1500.0},
        {"name": "Till", "is_blank": False, "revenue_current": 48292.5, "revenue_previous": 41867.5,
         "change": 6425.0}])
    widget = next(w for w in report.dashboard.widgets if w.id == "breakdown_1")
    assert widget.chart == "bars"  # a negative part is no part of a whole
    page = render_html(report)
    row = re.search(r'<li class="hb-row"><span class="hb-label">Returns desk</span>.*?</li>', page).group(0)
    assert 'class="hb-bar down"' in row and "-2,000.00" in row
    left = float(re.search(r'hb-bar down" style="left:([0-9.]+)%', row).group(1))
    zero = float(re.search(r'hb-zero" style="left:([0-9.]+)%', row).group(1))
    assert left < zero  # it runs left of the zero line


def test_a_withheld_breakdown_says_why_under_the_tiles() -> None:
    report = _kaggle_split([], withheld="the column has 14 values in November 2024 and December 2024; a split is "
                                         "drawn for 12 at most")
    assert "breakdown_1" not in _ids(report)[1]
    assert report.dashboard.not_shown[-1] == ('Sales by "Desk" are not shown: the column has 14 values in November '
                                              "2024 and December 2024; a split is drawn for 12 at most.")
    assert 'Sales by "Desk" are not shown' in Page(render_html(report)).section("tiles")


def test_a_blocked_report_names_no_split_in_what_it_cannot_know() -> None:
    # Review 3 #3: the line said "Sales are split only by ..." where no split is drawn. Half of September with
    # no line at all: D1 blocks; a column split by stage 2 all the same.
    frame = s0(1)
    frame = frame[~frame["Date"].between("2023-09-01", "2023-09-18")].reset_index(drop=True)
    frame["Till"] = ["T1", "T2"] * (len(frame) // 2) + ["T1"] * (len(frame) % 2)
    report = _pipeline(frame, breakdowns=["Till"])
    assert report.dashboard.state == "blocked"
    assert report.dashboard.widgets[0].id == "summary" and "breakdown_1" not in _ids(report)[1]
    line = next(item.text for item in report.front.cannot_know if item.title.startswith("Sales by channel"))
    assert line == "This version does not split sales that way."

def test_the_category_chart_is_never_parts_of_a_whole() -> None:
    # Review 3 #4: stage 2's categories leave the lines with no category out, so they are not the whole.
    report = build_real("kaggle")
    category = next(w for w in report.dashboard.widgets if w.id == "category")
    assert category.chart == "bars"
    assert category.caption == ["Each bar is one category's sales; lines with no category are not in this chart."]


def test_a_tiles_figure_wraps_on_a_phone_never_cut() -> None:
    # Review 3 #5: "GBP 663,315.58" in a 143 px tile lost its last digit under nowrap.
    from stages.report.html_dashboard import DASHBOARD_STYLE

    assert ".tile .num{white-space:normal}" in DASHBOARD_STYLE


def test_a_charts_figures_are_text_a_reader_and_a_screen_reader_get() -> None:
    # Review 3 #6: the SVG charts hid their figures from screen readers and shrank them to ~6 px on a phone.
    page = render_html(_kaggle_with_splits())
    probe = Page(page)
    location = probe.section("breakdown-1")
    assert "In-store" in location and "25,469.50" in location and "was 17,704.00" in location
    assert '<ul class="hbars"' in page and "<svg" not in probe.sections.get("category", "")
