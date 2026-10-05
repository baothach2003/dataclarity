"""Session 2E-g, stage 2 product tables (Thach), written before the change.

- Units are sale lines only (D1): a write-off or a free item is no unit sold.
- "(no product name)" - a line with neither SKU nor name - is a data gap:
  in the totals, never ranked (top products, decliners, velocity, Pareto).
- Labels come from shared/products.py: the name sale lines carry most,
  whole file, so a product reads the same in both months.
- Velocity needed stock on hand, derived from stock-in lines (2C); since
  2E-t2 (the line taxonomy's v1 scope cut) no file has a stock figure.
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


# --- stock: not supported in v1 (2E-t2) ---------------------------------------------------
# 2E-g derived stock on hand from stock-in lines; the line taxonomy's v1 scope
# cut (Thach, 2026-09-28) retired it: every stock KPI reads "not supported in
# v1" on every file, a file with stock-in lines included. The inputs of the
# 2E-g tests stay here as that file's cases.

def _typed(rows: list[dict]) -> list[dict]:
    return [{**r, "Type": "out"} for r in _base()] + rows


STOCK_FILES = {
    "no stock-in line": (_base(), MAPPING),
    "stock in for one product only": (_typed([
        {**row(date(2026, 7, 1), qty=100.0, product="Mug"), "Type": "in"},
        {**row(date(2026, 8, 10), qty=30.0, product="Mug"), "Type": "out"}]), WITH_TYPE),
    "a write-off beside the sales": (_typed([
        {**row(date(2026, 7, 1), qty=100.0, product="Mug"), "Type": "in"},
        {**row(date(2026, 8, 10), qty=30.0, product="Mug"), "Type": "out"},
        {**row(date(2026, 8, 11), qty=-10.0, price=0.0, product="Mug"), "Type": "out"}]), WITH_TYPE),
    "stock in with no price": (_typed([
        {**row(date(2026, 7, 1), qty=500.0, product="Mug"), "Type": "in", "Price": ""},
        {**row(date(2026, 7, 1), qty=50.0, product="Widget"), "Type": "in", "Price": None}]), WITH_TYPE),
    "a sale before any stock in": (_typed([
        {**row(date(2026, 7, 3), qty=50.0, product="Mug"), "Type": "out"},
        {**row(date(2026, 7, 20), qty=60.0, product="Mug"), "Type": "in", "Price": ""},
        {**row(date(2026, 8, 10), qty=5.0, product="Mug"), "Type": "out"}]), WITH_TYPE),
}


@pytest.mark.parametrize("name", list(STOCK_FILES))
def test_no_file_has_a_stock_figure_in_v1(name: str) -> None:
    rows, mapping = STOCK_FILES[name]
    products = _products(rows, mapping)

    assert products.velocity is None
    assert products.velocity_reason.startswith("stock figures are not supported in v1")


def test_revenue_scope_reads_in_as_it_always_has() -> None:
    """One reading of "in" (2E-g cycle 2 F4): " IN " is out of revenue
    (August revenue stays 20), and no stock figure is written from it."""
    rows = [{**r, "Type": "out"} for r in _base()]
    rows.append({**row(date(2026, 8, 10), qty=100.0, price=5.0), "Type": " IN "})

    metrics = assemble_metrics(pd.DataFrame(rows), WITH_TYPE, now=NOW)

    assert metrics.core.revenue_current == pytest.approx(20.0)
    assert metrics.products.velocity is None


def test_stage_2_and_stage_3_read_categories_alike() -> None:
    """Stage 2 and stage 3 read categories alike (cycle 2 F1 was the two
    stages disagreeing). Under option A a trailing zero-width space still made
    "Toys" two categories in both; one text reading for every stage (Thach,
    2E-i) makes it one, in both."""
    from stages.diagnose.members import category_totals
    from tests.stages.diagnose.diagnose_fixtures import run_data

    mapping = {**MAPPING, "Cat": "category"}
    rows = [{**r, "Cat": "Other"} for r in _base()]
    rows += [{**row(date(2026, 7, 15), price=300.0), "Cat": "Toys"},
             {**row(date(2026, 8, 15), price=300.0), "Cat": "Toys\u200b"}]

    data = run_data(rows, mapping)
    stage_2 = {c.name for c in data.metrics.by_dimension.category}
    stage_3 = set(category_totals(data).labels.values()) - {"(uncategorised)"}

    assert stage_2 == stage_3 == {"Other", "Toys"}


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

    # Since 2E-t2 any velocity list is refused too (not supported in v1).
    for change in ({"velocity": None, "velocity_reason": None},
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
    assert SCHEMA_VERSION == "16.2"  # 16.2 in the report redesign's step 1 (additive); 16.1 in 2E-u6 (additive); 9.0 in 2E-e2; 10.0 in 2E-k; 11.0 in 2E-d2; 12.0 in 2E-l; 13.0 in 2E-i; 14.0 in 2E-j; 15.0 in 2E-o; 16.0 since 2E-t1
    assert MetricsContract.supported_major == 16
