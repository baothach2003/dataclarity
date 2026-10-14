"""contracts/report_dashboard.py (the dashboard's step 3): the order rule (D3)
and the tile rules (D2) the block is held to - one copy, read by stage 5 and
by the contract."""

import pytest
from pydantic import ValidationError

from contracts.report_dashboard import FALLBACK_ORDER, TIED, Dashboard, Tile, Widget, order_widgets


def _tile(tile_id: str = "orders", **changes: object) -> dict:
    tile = {"id": tile_id, "label": "Orders", "unit": "count", "now": "343", "now_value": 343.0, "was": "308",
            "was_value": 308.0, "change": None, "direction": "up", "reason": None, "notes": []}
    return tile | changes


def _sales(**changes: object) -> dict:
    return _tile("sales", label="Sales", unit="money", now="46,292.50", now_value=46292.5, was=None, was_value=None,
                 change="+4,925.00 (+11.9%) on November 2024") | changes


def _text(widget_id: str) -> dict:
    return {"id": widget_id, "kind": "text", "chart": None, "placed_by": "fallback", "title": None}


def _chart(widget_id: str, size: float | None, placed: str = "size", chart: str | None = None) -> dict:
    chart = chart or {"trend": "line", "waterfall": "waterfall"}.get(widget_id, "bars")
    bars = [] if chart in ("line", "waterfall") else [{"label": "A", "now": 1.0, "was": 2.0, "now_text": "1.00",
                                                        "was_text": "2.00"}]
    return {"id": widget_id, "kind": "chart", "chart": chart, "placed_by": placed, "size": size, "title": "T",
            "bars": bars, "column": "Col" if widget_id.startswith("breakdown_") else None}


def _dashboard(widgets: list[dict], tiles: list[dict] | None = None, state: str = "compared") -> dict:
    return {"state": state, "tiles": tiles or [_sales(), _tile()], "not_shown": [], "caution": [],
            "widgets": widgets}


# --- the order rule -----------------------------------------------------------------------------------------------


def test_the_named_widget_leads_even_when_smaller() -> None:
    sizes = {"trend": 4925.0, "waterfall": 4712.29, "products": 1148.0, "summary": None}
    assert order_widgets(sizes, "products") == ["products", "trend", "waterfall", "summary"]


def test_then_largest_first_then_the_unsized_in_the_fixed_order() -> None:
    sizes = {"cannot_know": None, "summary": None, "products": 10.0, "trend": 30.0, "category": 20.0}
    assert order_widgets(sizes, None) == ["trend", "category", "products", "summary", "cannot_know"]


def test_equal_sizes_follow_the_fixed_order() -> None:
    sizes = {"returns": 5.0, "customers": 5.0, "trend": 5.0}
    assert order_widgets(sizes, None) == ["trend", "customers", "returns"]


def test_a_zero_size_still_comes_before_the_unsized() -> None:
    assert order_widgets({"summary": None, "returns": 0.0}, None) == ["returns", "summary"]


def test_the_fixed_order_and_the_ties_are_the_designs() -> None:
    assert FALLBACK_ORDER == ("summary", "trend", "waterfall", "customers", "products", "category", "breakdown_1",
                              "breakdown_2", "returns", "checklist", "next_steps", "next_month", "cannot_know")
    # Step 3's review: no product cause is tied - the products chart is this month's best sellers.
    assert TIED == {"B1": "waterfall", "B2": "waterfall", "P1": "waterfall", "P2": "waterfall", "C1": "customers",
                    "C2": "customers", "C3": "customers", "P3": "returns", "T2": "trend"}


def test_a_dashboard_out_of_the_rules_order_is_refused() -> None:
    widgets = [_chart("products", 10.0), _chart("trend", 30.0, chart="line"), _text("summary")]
    with pytest.raises(ValidationError, match="order"):
        Dashboard.model_validate(_dashboard(widgets))
    Dashboard.model_validate(_dashboard([widgets[1], widgets[0], widgets[2]]))


def test_the_named_widget_must_come_first() -> None:
    widgets = [_chart("trend", 30.0, chart="line"), _chart("products", 10.0, placed="named"), _text("summary")]
    with pytest.raises(ValidationError):
        Dashboard.model_validate(_dashboard(widgets))


def test_two_named_widgets_are_refused() -> None:
    widgets = [_chart("trend", 30.0, placed="named", chart="line"), _chart("products", 10.0, placed="named")]
    with pytest.raises(ValidationError, match="one widget at most"):
        Dashboard.model_validate(_dashboard(widgets))


def test_a_widget_twice_is_refused() -> None:
    with pytest.raises(ValidationError, match="once"):
        Dashboard.model_validate(_dashboard([_text("summary"), _text("summary")]))


def test_placed_by_size_needs_a_size_and_a_size_is_placed_by_it() -> None:
    with pytest.raises(ValidationError, match="size"):
        Widget.model_validate(_chart("products", None, placed="size"))
    with pytest.raises(ValidationError, match="size"):
        Widget.model_validate(_chart("products", 3.0, placed="fallback"))


def test_a_blocked_dashboard_draws_only_its_three_text_widgets() -> None:
    tiles = [_sales(change=None, direction=None, reason="Not compared: the data checks did not pass.")]
    Dashboard.model_validate(_dashboard([_text("summary"), _text("next_month"), _text("cannot_know")], tiles,
                                        "blocked"))
    with pytest.raises(ValidationError, match="a blocked report draws"):
        Dashboard.model_validate(_dashboard([_text("summary"), _chart("trend", None, "fallback", "line"),
                                             _text("next_month"), _text("cannot_know")], tiles, "blocked"))


def test_a_month_not_compared_draws_no_difference() -> None:
    tiles = [_sales(change=None, direction=None, reason="Not compared."), _tile(was=None, was_value=None,
                                                                                    direction=None)]
    with pytest.raises(ValidationError, match="not compared"):
        Dashboard.model_validate(_dashboard([_chart("waterfall", None, "fallback", "waterfall")], tiles,
                                            "not_compared"))
    with pytest.raises(ValidationError, match="not compared"):
        Dashboard.model_validate(_dashboard([_chart("category", None, "fallback")], tiles, "not_compared"))
    with pytest.raises(ValidationError, match="CONTRACTS 11"):
        Dashboard.model_validate(_dashboard([_text("summary")], [_sales(change=None, direction=None,
                                                                        reason="r"), _tile()], "not_compared"))


# --- the tile rules -------------------------------------------------------------------------------------------------


def test_sales_first_and_the_tiles_in_their_order() -> None:
    with pytest.raises(ValidationError, match="sales always first"):
        Dashboard.model_validate(_dashboard([_text("summary")], [_tile(), _sales()]))
    with pytest.raises(ValidationError, match="order"):
        Dashboard.model_validate(_dashboard([_text("summary")], [_sales(), _tile("aov", label="AOV"), _tile()]))


def test_a_tile_without_a_figure_is_refused_but_sales_with_its_reason() -> None:
    with pytest.raises(ValidationError, match="shows a figure"):
        Tile.model_validate(_tile(now=None, now_value=None, was=None, was_value=None, direction=None, reason="why"))
    Tile.model_validate(_sales(now=None, now_value=None, change=None, direction=None, reason="why"))
    with pytest.raises(ValidationError, match="shows a figure"):
        Tile.model_validate(_sales(now=None, now_value=None, change=None, direction=None))


def test_a_figure_and_its_value_go_together() -> None:
    with pytest.raises(ValidationError, match="together"):
        Tile.model_validate(_tile(now_value=None))


def test_only_sales_carries_a_change() -> None:
    with pytest.raises(ValidationError, match="only sales"):
        Tile.model_validate(_tile(was=None, was_value=None, change="+35"))


def test_a_change_and_last_months_value_are_not_both_shown() -> None:
    with pytest.raises(ValidationError, match="not both"):
        Tile.model_validate(_sales(was="41,367.50", was_value=41367.5))


def test_a_direction_needs_its_comparison() -> None:
    with pytest.raises(ValidationError, match="direction"):
        Tile.model_validate(_tile(was=None, was_value=None, direction="up"))


def test_a_text_widget_carries_nothing_but_its_place() -> None:
    with pytest.raises(ValidationError, match="text widget"):
        Widget.model_validate(_text("summary") | {"title": "x"})
    with pytest.raises(ValidationError, match="text widgets"):
        Widget.model_validate(_text("trend"))


def test_a_chart_widget_is_drawn_as_its_kind() -> None:
    with pytest.raises(ValidationError, match="drawn as"):
        Widget.model_validate(_chart("products", 1.0, chart="diverging"))  # this month's sales: no change chart
    with pytest.raises(ValidationError, match="has bars"):
        Widget.model_validate(_chart("category", 1.0) | {"bars": []})
    with pytest.raises(ValidationError, match="own chart"):
        Widget.model_validate(_chart("trend", 1.0, chart="line") | {"bars": _chart("category", 1.0)["bars"]})
    with pytest.raises(ValidationError, match="names its column"):
        Widget.model_validate(_chart("category", 1.0) | {"column": "C"})



# --- step 3's review: every printed figure agrees with its value -------------------------------------------------


def test_a_printed_figure_that_is_not_its_value_is_refused() -> None:
    with pytest.raises(ValidationError, match="printed figure is not its value"):
        Tile.model_validate(_tile(now="344"))
    with pytest.raises(ValidationError, match="last month's printed figure"):
        Tile.model_validate(_tile(was="309"))
    with pytest.raises(ValidationError, match="go together"):
        Tile.model_validate(_tile(was_value=None))


def test_the_arrow_follows_the_printed_figures() -> None:
    with pytest.raises(ValidationError, match="arrow"):
        Tile.model_validate(_tile(direction="down"))
    Tile.model_validate(_tile(now="308", now_value=308.0, direction="same"))


def test_a_ratio_is_never_a_percentage() -> None:
    ratio = _tile("return_rate", label="Orders with a return, per order sold", unit="ratio", now="0.152",
                  now_value=0.15235, was="0.169", was_value=0.16924, direction="down")
    Tile.model_validate(ratio)
    with pytest.raises(ValidationError):
        Tile.model_validate(ratio | {"now": "15.2%"})


def test_a_bars_text_is_its_value() -> None:
    bar = {"label": "A", "now": 1.0, "was": 2.0, "now_text": "1.00", "was_text": "2.00"}
    with pytest.raises(ValidationError, match="printed figure is its value"):
        Widget.model_validate(_chart("category", 1.0) | {"bars": [bar | {"now_text": "1.50"}]})
    with pytest.raises(ValidationError, match="printed figure is its value"):
        Widget.model_validate(_chart("category", 1.0) | {"bars": [bar | {"was_text": "GBP 2.10"}]})
