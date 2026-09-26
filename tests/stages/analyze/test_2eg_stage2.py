"""Session 2E-g, stage 2 product tables (Thach), written before the change.

- Units are sale lines only (D1): a write-off or a free item is no unit sold.
- "(no product name)" - a line with neither SKU nor name - is a data gap:
  in the totals, never ranked (top products, decliners, velocity, Pareto).
- Labels come from shared/products.py: the name sale lines carry most,
  whole file, so a product reads the same in both months.
- Velocity needs stock on hand, derived from stock-in lines (2C). A file
  with no stock-in line at all - most POS exports, both demo files - has no
  velocity block, with one reason (it read "0 days to stockout" for 2,832 of
  2,858 Online Retail II products and all 150 Kaggle ones). In a file that
  has stock-in lines, a product with none has a null days_to_stockout with
  a reason.
- metrics.json 7.0.
"""

from datetime import date

import pandas as pd
import pytest

from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, row

WITH_TYPE = {**MAPPING, "Type": "transaction_type"}
WITH_SKU = {**MAPPING, "Sku": "sku"}


def _products(rows, mapping=MAPPING):
    return assemble_metrics(pd.DataFrame(rows), mapping, now=NOW).products


def _base() -> list[dict]:
    """July and August both complete: Widget sells 1 at 10 on the 1st and
    the last day of each month."""
    return [row(date(2026, 7, 1)), row(date(2026, 7, 31)), row(date(2026, 8, 1)),
            row(date(2026, 8, 31))]


def test_top_product_units_are_sale_lines_only() -> None:
    """August: Mug sells 3 at 10, two are written off (-2 at 0) and one given
    free (1 at 0). Units sold 3, not 3 - 2 + 1 = 2; revenue 30."""
    rows = _base() + [row(date(2026, 8, 5), qty=3.0, product="Mug"),
                      row(date(2026, 8, 6), qty=-2.0, price=0.0, product="Mug"),
                      row(date(2026, 8, 7), qty=1.0, price=0.0, product="Mug")]

    mug = next(p for p in _products(rows).top_products if p.product == "Mug")

    assert (mug.revenue, mug.units) == (pytest.approx(30.0), 3)


def test_the_gap_bucket_is_never_ranked() -> None:
    """Lines with no name and no SKU sell 2,000 in July and 1,000 in August:
    they would be the top product and the biggest decliner. They are not a
    product: August's top list is Widget alone and the Pareto counts 1."""
    rows = _base() + [row(date(2026, 7, 10), qty=1.0, price=2000.0, product="  "),
                      row(date(2026, 8, 10), qty=1.0, price=1000.0, product="")]

    products = _products(rows)

    assert [p.product for p in products.top_products] == ["Widget"]
    assert products.pareto.total_products == 1
    assert "(no product name)" not in [d.product for d in products.biggest_decliners or []]


def test_a_file_with_no_stock_in_line_has_no_velocity_block() -> None:
    products = _products(_base())

    assert products.velocity is None
    assert "stock-in" in products.velocity_reason


def test_a_product_with_no_stock_in_line_has_no_days_to_stockout() -> None:
    """The file records stock in for Mug only: 100 in on 1 July; August sells
    30 Mugs (sale lines). Mug: stock 100 - 30 = 70, 30/31 a day, 70 / (30/31)
    = 72.33 days. Widget has no stock-in line: null, with a reason."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows += [{**row(date(2026, 7, 1), qty=100.0, product="Mug"), "Type": "in"},
             {**row(date(2026, 8, 10), qty=30.0, product="Mug"), "Type": "out"}]

    velocity = {v.product: v for v in _products(rows, WITH_TYPE).velocity}

    assert velocity["Mug"].days_to_stockout == pytest.approx(70 / (30 / 31))
    assert velocity["Mug"].units_per_day == pytest.approx(30 / 31)
    assert velocity["Widget"].days_to_stockout is None
    assert "stock-in" in velocity["Widget"].days_to_stockout_reason


def test_velocity_units_a_day_are_sale_lines_only() -> None:
    """Mutation check (2E-g, S2): 100 Mugs in on 1 July; August sells 30 and
    writes 10 off (-10 at 0). Units sold a day are 30/31, not (30 - 10)/31."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows += [{**row(date(2026, 7, 1), qty=100.0, product="Mug"), "Type": "in"},
             {**row(date(2026, 8, 10), qty=30.0, product="Mug"), "Type": "out"},
             {**row(date(2026, 8, 11), qty=-10.0, price=0.0, product="Mug"), "Type": "out"}]

    mug = next(v for v in _products(rows, WITH_TYPE).velocity if v.product == "Mug")

    assert mug.units_per_day == pytest.approx(30 / 31)


def test_a_stock_in_line_needs_no_price() -> None:
    """2E-g doubt-review F1: goods received are often written with no sale
    price. Such an "in" line was invalid (a price is needed to be a counted
    line) and the file read as having no stock-in line at all. Mug: 500 in,
    31 sold in August (1 a day): 469 days. Widget: 50 in, 2 sold in August
    and 2 in July: 46 / (2/31) = 713."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows += [{**row(date(2026, 7, 1), qty=500.0, product="Mug"), "Type": "in", "Price": ""},
             {**row(date(2026, 7, 1), qty=50.0, product="Widget"), "Type": "in", "Price": None}]
    rows += [{**row(day, product="Mug"), "Type": "out"}
             for day in (date(2026, 8, d) for d in range(1, 32))]

    velocity = {v.product: v for v in _products(rows, WITH_TYPE).velocity}

    assert velocity["Mug"].days_to_stockout == pytest.approx(469.0)
    assert velocity["Widget"].days_to_stockout == pytest.approx(46 / (2 / 31))


def test_stock_in_that_covers_less_than_was_sold_is_no_stock_figure() -> None:
    """2E-g doubt-review cycle 2, F2: Mug sells 40 in July and 40 in August;
    one "in" line of 50 on 20 August. In minus out is -30: the file's stock
    history is incomplete (it began with stock on hand), so there is no
    days-to-stockout figure - not "0 days"."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows += [{**row(date(2026, month, day), qty=10.0, product="Mug"), "Type": "out"}
             for month in (7, 8) for day in (3, 10, 17, 24)]
    rows.append({**row(date(2026, 8, 20), qty=50.0, product="Mug"), "Type": "in", "Price": ""})

    mug = next(v for v in _products(rows, WITH_TYPE).velocity if v.product == "Mug")

    assert mug.days_to_stockout is None
    assert "incomplete" in mug.days_to_stockout_reason


def test_a_sale_before_any_stock_in_makes_the_history_incomplete() -> None:
    """2E-g doubt-review cycle 3 F1: Mug sells 50 on 3 July before any stock
    comes in, 60 arrive on 20 July, 5 sell on 10 August. The end balance is
    60 - 55 = 5 (31 days), but the 50 sold first prove stock on hand before
    the file: the running balance fell to -50, so the history is incomplete
    and there is no figure."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows += [{**row(date(2026, 7, 3), qty=50.0, product="Mug"), "Type": "out"},
             {**row(date(2026, 7, 20), qty=60.0, product="Mug"), "Type": "in", "Price": ""},
             {**row(date(2026, 8, 10), qty=5.0, product="Mug"), "Type": "out"}]

    mug = next(v for v in _products(rows, WITH_TYPE).velocity if v.product == "Mug")

    assert mug.days_to_stockout is None
    assert "incomplete" in mug.days_to_stockout_reason


def test_stock_in_on_the_day_of_a_sale_counts_first() -> None:
    """Same-day ordering: 10 arrive and 10 sell on 1 July - no dip below
    zero. Then 20 arrive on 2 July and 5 sell on 10 August: 25 / (5/31)."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows += [{**row(date(2026, 7, 1), qty=10.0, product="Mug"), "Type": "out"},
             {**row(date(2026, 7, 1), qty=10.0, product="Mug"), "Type": "in", "Price": ""},
             {**row(date(2026, 7, 2), qty=20.0, product="Mug"), "Type": "in", "Price": ""},
             {**row(date(2026, 8, 10), qty=5.0, product="Mug"), "Type": "out"}]

    mug = next(v for v in _products(rows, WITH_TYPE).velocity if v.product == "Mug")

    assert mug.days_to_stockout == pytest.approx(15 / (5 / 31))


def test_revenue_scope_and_stock_in_read_in_alike() -> None:
    """One reading of "in" (2E-g cycle 2 F4), HEAD's: " IN " is a stock-in line
    for velocity and out of revenue alike (August revenue stays 20)."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows.append({**row(date(2026, 8, 10), qty=100.0, price=5.0), "Type": " IN "})

    metrics = assemble_metrics(pd.DataFrame(rows), WITH_TYPE, now=NOW)

    assert metrics.core.revenue_current == pytest.approx(20.0)
    assert metrics.products.velocity is not None


def test_stage_2_and_stage_3_read_categories_alike() -> None:
    """Categories read as before 2E-g in BOTH stages (option A): a trailing
    zero-width space still makes "Toys" two categories - the FABRICATE the
    one-text-reading session fixes - but stage 2 and stage 3 split it the
    same way (cycle 2 F1 was the two stages disagreeing)."""
    from stages.diagnose.members import category_totals
    from tests.stages.diagnose.diagnose_fixtures import run_data

    mapping = {**MAPPING, "Cat": "category"}
    rows = [{**r, "Cat": "Other"} for r in _base()]
    rows += [{**row(date(2026, 7, 15), price=300.0), "Cat": "Toys"},
             {**row(date(2026, 8, 15), price=300.0), "Cat": "Toys\u200b"}]

    data = run_data(rows, mapping)
    stage_2 = {c.name for c in data.metrics.by_dimension.category}
    stage_3 = set(category_totals(data).labels.values()) - {"(uncategorised)"}

    assert stage_2 == stage_3 == {"Other", "Toys", "Toys\u200b"}


def test_a_product_keeps_one_label_in_both_months() -> None:
    """S1 sold as "Old name" once in July, then "New name" twice in August:
    the label is "New name" in the top list and among the decliners."""
    rows = _base() + [{**row(date(2026, 7, 5), qty=10.0, product="Old name"), "Sku": "S1"},
                      {**row(date(2026, 8, 5), product="New name"), "Sku": "S1"},
                      {**row(date(2026, 8, 6), product="New name"), "Sku": "S1"}]
    rows = [{"Sku": None, **r} for r in rows]

    products = _products(rows, WITH_SKU)

    assert "New name" in [p.product for p in products.top_products]
    assert [d.product for d in products.biggest_decliners] == ["New name"]


def test_two_products_sharing_a_name_show_their_skus() -> None:
    rows = _base() + [{**row(date(2026, 8, 5), product="SIGN"), "Sku": "21171"},
                      {**row(date(2026, 8, 5), price=20.0, product="SIGN"), "Sku": "82580"}]
    rows = [{"Sku": None, **r} for r in rows]

    names = [p.product for p in _products(rows, WITH_SKU).top_products]

    # 20 (82580), 20 (Widget, two lines) - tie by label - then 10 (21171).
    assert names == ["SIGN (82580)", "Widget", "SIGN (21171)"]


def test_a_missing_velocity_or_days_to_stockout_must_say_why() -> None:
    """The contract pairs each null with its reason (2E's rule), and a value
    never carries one."""
    from pydantic import ValidationError

    from tests.contracts.test_metrics import metrics_payload

    for change in ({"velocity": None},
                   {"velocity": [{"product": "P", "units_per_day": 1.0, "days_to_stockout": None,
                                  "days_to_stockout_reason": None}]},
                   {"velocity": [{"product": "P", "units_per_day": 1.0, "days_to_stockout": 3.0,
                                  "days_to_stockout_reason": "why"}]}):
        payload = metrics_payload()
        payload["products"].update(change)
        with pytest.raises(ValidationError):
            MetricsContract.model_validate(payload)


def test_metrics_json_is_version_7_or_the_current_one() -> None:
    # 7.0 in 2E-g; 8.0 in 2E-h; 9.0 since 2E-e2 (test_2ee2_stage2.py).
    assert SCHEMA_VERSION == "11.0"  # 9.0 in 2E-e2; 10.0 in 2E-k; 11.0 since 2E-d2
    assert MetricsContract.supported_major == 11
