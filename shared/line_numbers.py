"""A line's numbers as every stage reads them - quantity, unit price, and
whether its transaction type says "in" - and the error for a canonical field
with no mapped column. Split from `shared/transactions.py` in 2E-t2 so the
line taxonomy's classifier (`shared/line_taxonomy.py`), which
`parse_transactions` calls, can read them without an import cycle;
`shared/transactions.py` re-exports every name, one definition."""

from typing import NamedTuple

import numpy as np
import pandas as pd

from shared.text import identifier_text


class RequiredColumnMissingError(ValueError):
    """cleaned.csv has no column mapped to a canonical field a stage needs.
    transaction_date and quantity are stage 1 required fields, so raising for
    them is defensive; unit_price is not required by stage 1
    (docs/AI_PIPELINE.md section 11), so it is the realistic case.

    `canonical_field` is structured (not just the message text) so a caller
    outside the stage - the API endpoints - can report which field is missing
    without parsing a sentence."""

    def __init__(self, canonical_field: str) -> None:
        self.canonical_field = canonical_field
        super().__init__(
            f"cleaned.csv has no column mapped to '{canonical_field}'; "
            "metrics cannot be computed without it"
        )


class LineClassColumnsError(ValueError):
    """cleaned.csv's line-taxonomy columns (`line_class`, `class_source`,
    `suggested_class`) are not what stage 1 writes: a value outside their
    closed lists, or some of the three without the others. Stage 1 renames a
    source column of those names (2E-t1), so this is a file changed after
    cleaning - refused with a message the API shows (2E-t2 review 1 #10)."""

    def __init__(self, problem: str) -> None:
        self.problem = problem
        super().__init__(f"cleaned.csv's line classes cannot be read: {problem}; re-upload the file")


def line_numbers(df: pd.DataFrame, reverse: dict[str, str], quantity_col: str,
             price_col: str) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Quantities, prices, and whether each row counts towards revenue by its
    transaction type (not an explicit "in") - read by `parse_transactions`
    and, without dates, by stage 1's walk-in placeholder search (2E-k)."""
    quantities = pd.to_numeric(df[quantity_col], errors="coerce")
    prices = pd.to_numeric(df[price_col], errors="coerce")
    type_col = reverse.get("transaction_type")
    if type_col is None:
        counts_as_sale = pd.Series(True, index=df.index)
    else:
        # astype(object): an empty or all-missing column can read back as
        # float64, and .str only works on an object/string dtype. NaN (a
        # per-row missing type) compares False to "in", so it also defaults
        # to "out", matching the column-level default.
        counts_as_sale = ~is_stock_in(df[type_col])
    return quantities, prices, counts_as_sale


def require_column(reverse: dict[str, str], canonical_field: str) -> str:
    column = reverse.get(canonical_field)
    if column is None:
        raise RequiredColumnMissingError(canonical_field)
    return column


def is_stock_in(values: pd.Series) -> pd.Series:
    """Where a transaction_type cell says "in", read as revenue scope has
    always read it (2A) - one reading for revenue scope and stage 2's
    stock-in lines (2E-g) - through `identifier_text` (2E-i: "IN" with a
    zero-width space was a sale). NaN is not "in"."""
    return identifier_text(values).str.lower().eq("in")


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
