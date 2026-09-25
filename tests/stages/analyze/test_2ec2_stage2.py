"""Session 2E-c2, stage 2 (Thach, after 2E-c's review), written before the
change.

1. A return line needs quantity < 0 AND a negative amount (symmetric with the
   sale row). A zero-amount negative-quantity line is a stock write-off, not
   a customer return: it leaves return_rate. On Online Retail II 3,393 such
   lines ("check", "damaged", "missing", "thrown away") inflated return_rate
   by 7% to 78% a month.
2. "Returns only" is renamed "No purchases in file": it holds gift-only and
   coupon-only customers too, who returned nothing.
3. metrics_products no longer crashes on a product whose every row has a
   blank name (TypeError sorting a float against strings, on raw Online
   Retail II): such a product is shown by its SKU.
4. metrics.json 4.0: return_rate and new customers changed meaning.
"""

from datetime import date

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.metrics import MetricsContract
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.analyze.metrics_products import compute_product_metrics
from stages.analyze.rfm import rfm_snapshot
from tests.stages.analyze.products_fixtures import period_for
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, row


def _two_months(extra: list[dict]) -> list[dict]:
    """Ten customers each buy one unit at 10 on the 1st-10th of July and of
    August 2026, plus `extra`, plus a sale on 1 September."""
    rows = []
    for month in (7, 8):
        rows += [row(date(2026, month, day), qty=1.0, price=10.0, customer=f"C{day}")
                 for day in range(1, 11)]
    rows.append(row(date(2026, 9, 1), qty=1.0, price=10.0, customer="C1"))
    return rows + extra


def test_a_zero_amount_write_off_is_not_a_return() -> None:
    """August adds one real return (C1 returns 1 @ 10) and three stock
    write-offs with no money (-1 @ 0, "damaged"). By hand: return_rate =
    1 return line / 10 orders = 0.1, not 4 / 10 = 0.4."""
    extra = [row(date(2026, 8, 12), qty=-1.0, price=10.0, customer="C1")]
    extra += [row(date(2026, 8, 13 + i), qty=-1.0, price=0.0, customer="") for i in range(3)]

    core = assemble_metrics(pd.DataFrame(_two_months(extra)), MAPPING, now=NOW).core

    assert core.return_rate_current == pytest.approx(0.1)


def test_a_customer_with_no_purchase_is_labelled_for_what_is_true_of_them() -> None:
    """A gift-only customer returned nothing, so "Returns only" was false for
    them; "No purchases in file" is true of refund-only and gift-only alike."""
    table = pd.DataFrame({
        "customer": ["buyer", "gift_only", "refund_only"],
        "date": pd.to_datetime(["2011-11-01", "2011-11-10", "2011-11-12"]),
        "revenue": [20.0, 0.0, -5.0],
        "sale": [True, False, False],
    })

    segments = rfm_snapshot(table, date(2011, 12, 1))["segment"]

    assert segments["gift_only"] == "No purchases in file"
    assert segments["refund_only"] == "No purchases in file"


def test_a_product_with_no_name_on_any_row_is_shown_by_its_sku() -> None:
    """Raw Online Retail II crashed stage 2: every row of a product had a
    missing Description, its display name was NaN, and sorting it against
    real names raised TypeError. X9's name is missing on every row, Y7's is
    blank on every row (it would show as ""). Both are shown by their SKU.
    Since 2E-g the file, which has no stock-in line, has no velocity block
    (Thach: stock on hand cannot be derived), so the names are read from the
    top products alone."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Product": "product_name", "Sku": "sku"}
    df = pd.DataFrame([
        {"Date": "2019-12-10", "Qty": "2", "Price": "5.0", "Product": "Mug", "Sku": "M1"},
        {"Date": "2019-12-11", "Qty": "1", "Price": "5.0", "Product": None, "Sku": "X9"},
        {"Date": "2019-12-12", "Qty": "1", "Price": "5.0", "Product": "  ", "Sku": "Y7"},
        {"Date": "2020-01-10", "Qty": "3", "Price": "5.0", "Product": "Mug", "Sku": "M1"},
        {"Date": "2020-01-30", "Qty": "1", "Price": "5.0", "Product": "  ", "Sku": "Y7"},
        {"Date": "2020-01-31", "Qty": "1", "Price": "5.0", "Product": None, "Sku": "X9"},
    ])

    products = compute_product_metrics(df, mapping, period_for(df, mapping))

    assert products.velocity is None
    assert {p.product for p in products.top_products} == {"Mug", "X9", "Y7"}


def test_metrics_json_is_major_version_4_or_the_current_one() -> None:
    # 4.0 in 2E-c2; 5.0 in 2E-e; 6.0 in 2E-f; 7.0 in 2E-g; 8.0 in 2E-h; 9.0 since 2E-e2. A 3.x file is refused.
    assert SCHEMA_VERSION == "9.0"
    payload = assemble_metrics(pd.DataFrame(_two_months([])), MAPPING,
                               now=NOW).model_dump(mode="json")
    payload["schema_version"] = "3.0"

    with pytest.raises(ValidationError, match="re-analyse"):
        MetricsContract.model_validate(payload)


def test_every_nameless_row_is_one_visible_product() -> None:
    """2E-c2 doubt-review F2: with no SKU mapped, a MISSING name keyed to NaN
    and left the product tables, while a whitespace name became "(no
    product name)" - so the file's largest line (1,000) vanished and the
    bucket showed 500. Stage 3 puts both in one bucket (members.py): 1,500.
    SUPERSEDED in part (Thach, 2E-g): the bucket is a data gap, never ranked
    as a product - it was this file's top product. Both lines stay in the
    money: January's revenue is 100 + 1,000 + 500 + 0.5 + 1 = 1,601.5, and
    stage 3's gap member still holds 1,500 (test_2eg_stage3)."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Product": "product_name"}
    df = pd.DataFrame([
        {"Date": f"2020-01-{day:02d}", "Qty": "1", "Price": price, "Product": name}
        for day, (name, price) in enumerate([("Widget", "100"), (None, "1000"),
                                             ("   ", "500"), ("Widget", "0.5")], start=1)
    ] + [{"Date": "2019-12-10", "Qty": "1", "Price": "100", "Product": "Widget"},
         {"Date": "2020-01-31", "Qty": "1", "Price": "1", "Product": "Widget"}])

    products = compute_product_metrics(df, mapping, period_for(df, mapping))

    revenue = {p.product: p.revenue for p in products.top_products}
    assert revenue == {"Widget": pytest.approx(101.5)}
    core = assemble_metrics(df, mapping, now=NOW).core
    assert core.revenue_current == pytest.approx(1601.5)
