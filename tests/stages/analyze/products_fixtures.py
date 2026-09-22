"""Shared builders for the metrics_products tests (Pareto/top_products in
test_metrics_products.py; decliners/velocity in
test_metrics_products_declines_and_velocity.py)."""

from datetime import UTC, datetime

import pandas as pd

from stages.analyze.metrics_core import compute_core_metrics

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

# source column name -> canonical field. No transaction_type mapped by
# default: every row defaults to "out" (2A's convention), which keeps the
# Pareto/top-products/decliners fixtures free of an unrelated concern.
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name"}
MAPPING_WITH_TYPE = {**MAPPING, "Type": "transaction_type"}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def period_for(df: pd.DataFrame, mapping: dict[str, str] = MAPPING):
    period, _ = compute_core_metrics(df, mapping, now=NOW)
    return period
