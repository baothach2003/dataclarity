"""Stage 2 Analyze - assembles metrics.json (docs/CONTRACTS.md section 6)
from the `period`/`core`/`customers`/`products`/`by_dimension` blocks and
writes it to runs/<run_id>/. Pure pandas; no AI call anywhere in this stage
(docs/adr/0002-pandas-computes-ai-interprets.md): no retry budget, no AI
client involved, unlike stage 1.
"""

import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract
from contracts.metrics import MetricsContract
from shared.run_registry import run_file
from stages.analyze.metrics_core import CLEANED_FILENAME, CLEANING_REPORT_FILENAME, compute_core_metrics
from stages.analyze.metrics_customers import compute_customer_metrics
from stages.analyze.metrics_dimensions import compute_dimension_metrics
from stages.analyze.metrics_products import compute_product_metrics

SCHEMA_VERSION = "1.0"
METRICS_FILENAME = "metrics.json"


def assemble_metrics(
    df: pd.DataFrame, column_mapping: dict[str, str], now: datetime | None = None
) -> MetricsContract:
    """Pure computation: calls all four blocks' builders and validates the
    combined result against contracts/metrics.py. Writes nothing. `now` is
    resolved once here (not left to each block to resolve separately) so
    `generated_at` and every block's own fallback timestamp agree."""
    now = now or datetime.now(UTC)
    period, core = compute_core_metrics(df, column_mapping, now)
    customers = compute_customer_metrics(df, column_mapping, period)
    products = compute_product_metrics(df, column_mapping, period)
    by_dimension = compute_dimension_metrics(df, column_mapping, period, core)

    return MetricsContract(
        schema_version=SCHEMA_VERSION,
        generated_at=now,
        period=period,
        core=core,
        customers=customers,
        products=products,
        by_dimension=by_dimension,
    )


def analyze_run(runs_root: Path, run_id: str, now: datetime | None = None) -> MetricsContract:
    """Read runs/<run_id>/cleaned.csv and cleaning_report.json, assemble
    metrics.json and write it atomically. Re-running overwrites only this
    stage's own output (docs/CONTRACTS.md section 1: a stage never edits a
    file it did not write)."""
    report = CleaningReportContract.model_validate_json(
        run_file(runs_root, run_id, CLEANING_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    frame = pd.read_csv(run_file(runs_root, run_id, CLEANED_FILENAME), dtype=str)
    metrics = assemble_metrics(frame, report.column_mapping, now)
    _write_atomically(
        run_file(runs_root, run_id, METRICS_FILENAME), metrics.model_dump_json(indent=2).encode("utf-8")
    )
    return metrics


def _write_atomically(target: Path, data: bytes) -> None:
    """A later reader sees the previous metrics.json or the complete new
    one, never half of it (same technique as
    stages/ingest/contract_files.py's write_contract; not imported from
    there since it is a different stage, CLAUDE.md 3.1 - and only one file
    is ever written here, so that helper's multi-file rollback is more than
    this needs)."""
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix=".stage-", suffix=".tmp")
    temp = Path(temp_name)
    try:
        with os.fdopen(handle, "wb") as out:
            out.write(data)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp, target)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
