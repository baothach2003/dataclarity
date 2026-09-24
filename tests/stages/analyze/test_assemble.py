from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningReportContract
from contracts.metrics import MetricsContract
from shared.run_registry import create_run
from stages.analyze.assemble import analyze_run, assemble_metrics
from stages.analyze.metrics_core import RequiredColumnMissingError

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

MAPPING = {
    "Date": "transaction_date",
    "Qty": "quantity",
    "Price": "unit_price",
    "Product": "product_name",
    "Cat": "category",
    "Cust": "customer",
}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _scenario() -> pd.DataFrame:
    return frame(
        [
            {"Date": "2020-01-10", "Qty": "3", "Price": "10.0", "Product": "Widget", "Cat": "A", "Cust": "Alice"},
            {"Date": "2020-01-31", "Qty": "7", "Price": "10.0", "Product": "Gadget", "Cat": "B", "Cust": "Bob"},
            {"Date": "2019-12-10", "Qty": "5", "Price": "10.0", "Product": "Widget", "Cat": "A", "Cust": "Alice"},
        ]
    )


def test_assemble_metrics_validates_against_the_full_contract() -> None:
    df = _scenario()

    metrics = assemble_metrics(df, MAPPING, now=NOW)

    # model_dump_json + model_validate_json is the same round trip a reader
    # of the written file goes through; proves every block's types agree
    # with contracts/metrics.py, not just this in-memory object's own class.
    reparsed = MetricsContract.model_validate_json(metrics.model_dump_json())
    assert reparsed == metrics

    assert metrics.schema_version == "5.0"  # 2E, 2E-c, 2E-c2, 2E-e: meanings changed
    assert metrics.generated_at == NOW
    assert (metrics.period.current, metrics.period.previous) == ("2020-01", "2019-12")

    # Every block was computed from the SAME period - no drift between them.
    assert metrics.customers.rfm_reference_date == metrics.period.data_end + timedelta(days=1)
    assert {p.product for p in metrics.products.top_products} == {"Widget", "Gadget"}
    assert {c.name for c in metrics.by_dimension.category} == {"A", "B"}
    assert metrics.by_dimension.country == []


def test_missing_unit_price_mapping_propagates() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "unit_price"}
    df = frame([{"Date": "2020-01-31", "Qty": "1", "Product": "Widget"}])

    with pytest.raises(RequiredColumnMissingError):
        assemble_metrics(df, mapping, now=NOW)


def _run_with_cleaned_csv(tmp_path: Path) -> str:
    run = create_run(tmp_path)
    (run.path / "cleaned.csv").write_text(
        "Date,Qty,Price,Product,Cat,Cust\n"
        "2020-01-10,3,10.0,Widget,A,Alice\n"
        "2020-01-31,7,10.0,Gadget,B,Bob\n",
        encoding="utf-8",
    )
    report = CleaningReportContract(
        schema_version="2.0",  # 2E-e: order_id widened the enum (major)
        generated_at=NOW,
        rows_in=2,
        rows_out=2,
        columns_in=6,
        columns_out=6,
        changes=[],
        warnings=[],
        column_mapping=MAPPING,
    )
    (run.path / "cleaning_report.json").write_text(report.model_dump_json(), encoding="utf-8")
    return run.run_id


def test_analyze_run_writes_metrics_json(tmp_path: Path) -> None:
    run_id = _run_with_cleaned_csv(tmp_path)

    returned = analyze_run(tmp_path, run_id, now=NOW)

    written = tmp_path / run_id / "metrics.json"
    assert MetricsContract.model_validate_json(written.read_text(encoding="utf-8")) == returned
    assert returned.period.current == "2020-01"


def test_rerun_replaces_its_own_output(tmp_path: Path) -> None:
    run_id = _run_with_cleaned_csv(tmp_path)
    analyze_run(tmp_path, run_id, now=NOW)

    later = datetime(2026, 9, 20, 8, 0, tzinfo=UTC)
    analyze_run(tmp_path, run_id, now=later)

    reread = MetricsContract.model_validate_json(
        (tmp_path / run_id / "metrics.json").read_text(encoding="utf-8")
    )
    assert reread.generated_at == later
