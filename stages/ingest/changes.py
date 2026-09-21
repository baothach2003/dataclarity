"""The mechanics every transform shares: reading a param, writing cells, adding
a flag column, and recording what happened as a `ChangeLogEntry`.

Split out of `transforms.py` so that module reads as the catalog it is: what
each of the 16 actions does, one function each. Nothing here knows about a
particular action.
"""

import math
from collections.abc import Mapping
from typing import Any

import pandas as pd

from contracts.cleaning import ChangeLogEntry, TransformAction

Params = Mapping[str, Any]
Result = tuple[pd.DataFrame, ChangeLogEntry]

# Flag columns carry a prefix so `cleaning.py` and the frontend can tell them
# from the file's own columns, whatever the file calls its columns.
FLAG_PREFIX = "__flag_"


def flag_column_name(kind: str, column: str | None = None) -> str:
    """`__flag_negative__Unit Price`, or `__flag_duplicate_key` for a
    dataset-wide flag."""
    return f"{FLAG_PREFIX}{kind}" + (f"__{column}" if column is not None else "")


# --- reading the plan's params ----------------------------------------------


def series(df: pd.DataFrame, column: str | None, action: TransformAction) -> pd.Series:
    if column is None:
        raise ValueError(f"{action} needs a column")
    if column not in df.columns:
        raise ValueError(f"{action}: no such column: {column!r}")
    return df[column]


def no_column(column: str | None, action: TransformAction) -> None:
    if column is not None:
        raise ValueError(f"{action} applies to the dataset, not to column {column!r}")


def required(params: Params, name: str, action: TransformAction) -> Any:
    if name not in params:
        raise ValueError(f"{action} needs a {name} param")
    return params[name]


def choice(
    params: Params,
    name: str,
    action: TransformAction,
    allowed: frozenset[str],
    default: str | None = None,
) -> str:
    value = params.get(name, default) if default is not None else required(params, name, action)
    if value not in allowed:
        raise ValueError(f"{action} needs {name} to be one of {sorted(allowed)}, got {value!r}")
    return str(value)


def is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def show(value: Any) -> str:
    """A computed value as the change log shows it. A mean is a full-precision
    float; six significant digits is what a person can read and compare."""
    return format(value, "g") if isinstance(value, float) else str(value)


# --- recording a change -----------------------------------------------------


def entry(
    action: TransformAction,
    column: str | None,
    params: Params,
    cells: int = 0,
    rows: int = 0,
    detail: str = "",
) -> ChangeLogEntry:
    return ChangeLogEntry(action=action, column=column, cells_affected=cells,
                          rows_affected=rows, params=dict(params), detail=detail)


def replace(
    df: pd.DataFrame,
    column: str | None,
    params: Params,
    action: TransformAction,
    new_values: pd.Series,
    changed: pd.Series,
    detail: str,
) -> Result:
    """Write `new_values` into the cells `changed` marks. A column where
    nothing is marked is left exactly as it was, dtype included, and the entry
    records that the action ran and changed nothing."""
    cells = int(changed.sum())
    if cells == 0:
        return df, entry(action, column, params, detail=detail)
    result = df.copy(deep=False)  # copy-on-write: only the column assigned below is new
    result[column] = set_cells(df[column], changed, new_values[changed])
    return result, entry(action, column, params, cells=cells, detail=detail)


def set_cells(values: pd.Series, changed: pd.Series, new_values: pd.Series) -> pd.Series:
    updated = values.copy()
    try:
        updated.loc[changed] = new_values
    except TypeError:
        # pandas 3 refuses a value its dtype cannot hold instead of widening
        # silently. Widening to object keeps the column's untouched text next
        # to the number or timestamp this action wrote.
        updated = values.astype(object)
        updated.loc[changed] = new_values
    return updated


def convert(
    df: pd.DataFrame,
    column: str | None,
    params: Params,
    action: TransformAction,
    converted: pd.Series,
    flag_kind: str,
    detail_template: str,
) -> Result:
    """parse_datetime and cast_type: the whole column becomes the new type, and
    every value that did not convert is left missing and flagged, so a failure
    is visible in `cleaned.csv` instead of silently coerced."""
    values = series(df, column, action)
    present = values.notna()
    failed = present & converted.isna()
    done = int((present & converted.notna()).sum())
    detail = detail_template.format(done=done, present=int(present.sum()))
    result = df.copy(deep=False)
    result[column] = converted
    result, flag_detail = mark(result, column, failed, flag_kind)
    return result, entry(action, column, params, cells=done, rows=int(failed.sum()),
                         detail=detail + flag_detail)


def flag(
    df: pd.DataFrame,
    column: str | None,
    params: Params,
    action: TransformAction,
    marked: pd.Series,
    flag_kind: str,
    detail: str,
) -> Result:
    """Actions that only mark rows: the data is untouched."""
    result, flag_detail = mark(df, column, marked, flag_kind)
    return result, entry(action, column, params, rows=int(marked.sum()),
                         detail=detail + flag_detail)


def _free_name(df: pd.DataFrame, name: str) -> str:
    """`name`, or `name_2`, `name_3`... when the frame already has a column of that
    name. A source column called `__flag_...` (a cleaned.csv uploaded again has
    them) must never be overwritten by a flag."""
    if name not in df.columns:
        return name
    number = 2
    while f"{name}_{number}" in df.columns:
        number += 1
    return f"{name}_{number}"


def mark(
    df: pd.DataFrame, column: str | None, marked: pd.Series, flag_kind: str
) -> tuple[pd.DataFrame, str]:
    """Add the boolean flag column, but only when something is marked: an
    all-False column would be a column of noise in every clean file."""
    if not marked.any():
        return df, ""
    name = _free_name(df, flag_column_name(flag_kind, column))
    result = df.copy(deep=False)
    result[name] = marked
    return result, f"; flagged in {name}"
