"""Stage 1's reading of the raw file's lines without dates - for its searches,
which read no period: walk-in placeholders (customer_placeholders.py) and
lines that may not be products (non_product_lines.py). Its own module so
neither search imports the other (2E-r F6)."""

from typing import NamedTuple

import numpy as np
import pandas as pd

from shared.transactions import line_numbers, require_column


class UndatedLines(NamedTuple):
    """`parse_transactions`' counted and sale lines without reading a date -
    for stage 1's searches, which read no period: walk-in placeholders (2E-k
    doubt-review cycle 2 F5: day-first dates cost ~20 s at 650,000 rows) and
    lines that may not be products (2E-d2). Nothing is classed yet at stage
    1, so every line of a counted type counts."""

    counted: pd.Series
    sale: pd.Series
    amounts: pd.Series


def undated_lines(df: pd.DataFrame, column_mapping: dict[str, str]) -> UndatedLines:
    """Raises RequiredColumnMissingError if quantity or unit_price has no
    mapped column."""
    reverse = {field: source for source, field in column_mapping.items()}
    quantity_col = require_column(reverse, "quantity")
    price_col = require_column(reverse, "unit_price")
    quantities, prices, counts_as_sale = line_numbers(df, reverse, quantity_col, price_col)
    counted = np.isfinite(quantities) & np.isfinite(prices) & counts_as_sale
    amounts = quantities * prices
    return UndatedLines(counted, counted & (quantities > 0) & (amounts > 0), amounts)
