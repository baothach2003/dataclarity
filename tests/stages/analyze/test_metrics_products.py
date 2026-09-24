from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningReportContract
from shared.run_registry import create_run
from stages.analyze.metrics_core import RequiredColumnMissingError
from stages.analyze.metrics_products import compute_product_metrics, product_metrics_for_run
from tests.stages.analyze.products_fixtures import MAPPING, NOW, frame, period_for

# --- Pareto + top_products: the hand-calculated scenario --------------------


def _pareto_scenario() -> pd.DataFrame:
    return frame(
        [
            {"Date": "2020-01-31", "Qty": "5", "Price": "10.0", "Product": "A"},  # revenue 50
            {"Date": "2020-01-31", "Qty": "5", "Price": "5.0", "Product": "B"},  # revenue 25
            {"Date": "2020-01-31", "Qty": "3", "Price": "5.0", "Product": "C"},  # revenue 15
            {"Date": "2020-01-31", "Qty": "7", "Price": "1.0", "Product": "D"},  # revenue 7
            {"Date": "2020-01-31", "Qty": "3", "Price": "1.0", "Product": "E"},  # revenue 3
        ]
    )


def test_pareto_and_top_products_hand_calculated() -> None:
    df = _pareto_scenario()
    period = period_for(df)
    assert period.current == "2020-01"  # data_end 2020-01-31 is month-end

    products = compute_product_metrics(df, MAPPING, period)

    # sorted desc: 50,25,15,7,3 -> cumulative 50,75,90,97,100; threshold=80.
    # 50+25=75<80, +15=90>=80 -> 3 products needed for 80% of revenue.
    assert products.pareto.products_for_80pct_revenue == 3
    assert products.pareto.total_products == 5
    assert products.pareto.concentration_pct == 60.0  # 3 / 5 * 100

    assert [(p.product, p.revenue, p.units) for p in products.top_products] == [
        ("A", 50.0, 5),
        ("B", 25.0, 5),
        ("C", 15.0, 3),
        ("D", 7.0, 7),
        ("E", 3.0, 3),
    ]


def test_top_products_excludes_a_net_negative_revenue_product() -> None:
    df = frame(
        [
            {"Date": "2020-01-10", "Qty": "5", "Price": "10.0", "Product": "Good"},  # revenue 50
            {"Date": "2020-01-31", "Qty": "-10", "Price": "10.0", "Product": "Bad"},  # revenue -100
        ]
    )
    period = period_for(df)

    products = compute_product_metrics(df, MAPPING, period)

    assert [p.product for p in products.top_products] == ["Good"]


def test_top_products_caps_at_ten_and_breaks_ties_by_name() -> None:
    rows = [
        {"Date": "2020-01-15", "Qty": "1", "Price": str(revenue), "Product": f"P{revenue}"}
        for revenue in [100, 90, 80, 70, 60, 50, 40, 30, 20]
    ]
    rows += [
        {"Date": "2020-01-15", "Qty": "1", "Price": "10", "Product": name}
        for name in ["Zeta", "Alpha", "Mike"]  # all tied at revenue 10
    ]
    rows.append({"Date": "2020-01-31", "Qty": "1", "Price": "1.0", "Product": "Lowest"})
    df = frame(rows)
    period = period_for(df)

    products = compute_product_metrics(df, MAPPING, period)

    # 9 distinct-revenue products + "Alpha" (alphabetically first of the
    # 3-way tie at revenue 10) fill the cap; "Mike"/"Zeta"/"Lowest" don't.
    assert [p.product for p in products.top_products] == [
        "P100", "P90", "P80", "P70", "P60", "P50", "P40", "P30", "P20", "Alpha",
    ]  # fmt: skip


def test_top_products_units_rounds_rather_than_truncates() -> None:
    # Doubt-review finding: int() truncates 5.9 down to 5; round() gives the
    # nearer whole number, 6.
    df = frame(
        [
            {"Date": "2020-01-10", "Qty": "3.0", "Price": "10.0", "Product": "Widget"},
            {"Date": "2020-01-31", "Qty": "2.9", "Price": "10.0", "Product": "Widget"},
        ]
    )
    period = period_for(df)

    products = compute_product_metrics(df, MAPPING, period)

    assert products.top_products[0].units == 6


def test_pareto_population_matches_top_products_excluding_non_positive_revenue() -> None:
    # Doubt-review finding: pareto.total_products previously counted
    # net-negative and net-zero-revenue products that top_products already
    # excludes, so the two numbers in the same contract object described
    # different populations.
    df = frame(
        [
            {"Date": "2020-01-05", "Qty": "7", "Price": "100.0", "Product": "A"},  # revenue 700
            {"Date": "2020-01-06", "Qty": "2", "Price": "100.0", "Product": "B"},  # revenue 200
            {"Date": "2020-01-07", "Qty": "1", "Price": "100.0", "Product": "C"},  # revenue 100
            {"Date": "2020-01-08", "Qty": "-1", "Price": "50.0", "Product": "D"},  # revenue -50
            {"Date": "2020-01-31", "Qty": "-1", "Price": "30.0", "Product": "E"},  # revenue -30
        ]
    )
    period = period_for(df)

    products = compute_product_metrics(df, MAPPING, period)

    assert [p.product for p in products.top_products] == ["A", "B", "C"]
    assert products.pareto.total_products == 3  # D and E excluded, same population as top_products
    # sorted desc 700,200,100 (total 1000); threshold 800; 700<800, 700+200=900>=800 -> 2 products
    assert products.pareto.products_for_80pct_revenue == 2
    assert products.pareto.concentration_pct == pytest.approx(2 / 3 * 100)


# --- product identity (sku, else product_name) ---------------------------


def test_sku_identity_groups_rows_and_falls_back_to_product_name_when_blank() -> None:
    mapping = {**MAPPING, "SKU": "sku"}
    df = frame(
        [
            {"Date": "2020-01-10", "Qty": "2", "Price": "10.0", "Product": "Widget", "SKU": "SKU1"},
            {"Date": "2020-01-20", "Qty": "3", "Price": "10.0", "Product": "widget (typo)", "SKU": "SKU1"},
            {"Date": "2020-01-31", "Qty": "1", "Price": "10.0", "Product": "Other", "SKU": "   "},
        ]
    )
    period = period_for(df, mapping)

    products = compute_product_metrics(df, mapping, period)

    by_product = {p.product: p for p in products.top_products}
    assert by_product["Widget"].units == 5  # 2 + 3, grouped by the shared SKU despite differing spellings
    assert by_product["Widget"].revenue == 50.0
    assert by_product["Other"].units == 1  # blank SKU (whitespace-only) falls back to product_name


def test_sku_and_product_name_identities_cannot_collide() -> None:
    # Doubt-review finding: a SKU that happens to read the same as an
    # unrelated product's name must not merge them.
    mapping = {**MAPPING, "SKU": "sku"}
    df = frame(
        [
            {"Date": "2020-01-10", "Qty": "2", "Price": "10.0", "Product": "Gadget Pro", "SKU": "Widget"},
            {"Date": "2020-01-31", "Qty": "5", "Price": "10.0", "Product": "Widget", "SKU": ""},
        ]
    )
    period = period_for(df, mapping)

    products = compute_product_metrics(df, mapping, period)

    by_product = {p.product: p for p in products.top_products}
    assert set(by_product) == {"Gadget Pro", "Widget"}
    assert by_product["Gadget Pro"].revenue == 20.0
    assert by_product["Widget"].revenue == 50.0


def test_sku_identity_is_normalized_for_whitespace_and_case() -> None:
    # Doubt-review finding: "SKU1", " SKU1" and "sku1" are formatting noise
    # around the same SKU, not three different products.
    mapping = {**MAPPING, "SKU": "sku"}
    df = frame(
        [
            {"Date": "2020-01-10", "Qty": "4", "Price": "10.0", "Product": "Widget", "SKU": "SKU1"},
            {"Date": "2020-01-20", "Qty": "3", "Price": "10.0", "Product": "Widget", "SKU": " SKU1"},
            {"Date": "2020-01-31", "Qty": "2", "Price": "10.0", "Product": "Widget", "SKU": "sku1"},
        ]
    )
    period = period_for(df, mapping)

    products = compute_product_metrics(df, mapping, period)

    assert len(products.top_products) == 1
    assert products.top_products[0].units == 9  # 4 + 3 + 2, one product, not three


# --- edge cases -----------------------------------------------------------


def test_missing_product_name_mapping_raises() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "product_name"}
    df = frame([{"Date": "2020-01-31", "Qty": "1", "Price": "10.0"}])
    period = period_for(_pareto_scenario())

    with pytest.raises(RequiredColumnMissingError):
        compute_product_metrics(df, mapping, period)


def test_empty_dataframe_returns_empty_lists_and_zero_pareto() -> None:
    df = pd.DataFrame({"Date": [], "Qty": [], "Price": [], "Product": []})
    period = period_for(df)  # falls back to NOW, per 2A's select_period

    products = compute_product_metrics(df, MAPPING, period)

    assert (products.pareto.products_for_80pct_revenue, products.pareto.total_products) == (0, 0)
    # Was 0.0 (2A); with no product there is no concentration (2E).
    assert products.pareto.concentration_pct is None
    assert products.pareto.concentration_reason is not None
    assert products.top_products == []
    # Was []. An empty file has no previous month to compare with (2E).
    assert products.biggest_decliners is None
    assert products.biggest_decliners_reason is not None
    assert products.velocity == []


# --- product_metrics_for_run: reads cleaned.csv + cleaning_report.json -----


def test_product_metrics_for_run_reads_cleaned_csv_and_the_mapping(tmp_path: Path) -> None:
    run = create_run(tmp_path)
    (run.path / "cleaned.csv").write_text(
        "Date,Qty,Price,Product\n2020-01-31,5,10.0,Widget\n",
        encoding="utf-8",
    )
    report = CleaningReportContract(
        schema_version="1.0",
        generated_at=NOW,
        rows_in=1,
        rows_out=1,
        columns_in=4,
        columns_out=4,
        changes=[],
        warnings=[],
        column_mapping=MAPPING,
    )
    (run.path / "cleaning_report.json").write_text(report.model_dump_json(), encoding="utf-8")

    products = product_metrics_for_run(tmp_path, run.run_id, now=NOW)

    assert len(products.top_products) == 1
    assert products.top_products[0].product == "Widget"
