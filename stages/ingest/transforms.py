"""The transform catalog: what each of the 16 cleaning actions does
(docs/AI_PIPELINE.md section 6). Which action is legal where, and in which
order a plan runs, is data in `transform_catalog.py`.

Every action is a pure function `apply(df, column, params) -> (df, entry)`: it
returns a new frame and the `ChangeLogEntry` that goes into
`cleaning_report.json` (docs/CONTRACTS.md section 5). The input frame is never
modified, and the row index is kept, so a dropped row stays visible as a gap.

Two rules hold for every action:

* An action that changes nothing still returns an entry, with
  `cells_affected: 0` and `rows_affected: 0` (decided by Thach in 1D). The
  report is then a complete record of what ran, not only of what happened.
* `cells_affected` counts cells whose value this action changed or removed;
  `rows_affected` counts rows it dropped or marked. One action fills one of
  the two, never both - which one is in the table below.

| action | cells_affected | rows_affected |
|---|---|---|
| impute_median / mean / mode / constant | missing cells filled | - |
| drop_rows_missing | - | rows dropped |
| drop_column | cells removed with the column | - |
| parse_datetime / cast_type | values converted | values flagged as failures |
| trim_whitespace / normalize_case | cells whose text changed | - |
| standardize_categories | cells given another label | - |
| fix_negative (abs) | negatives replaced | - |
| fix_negative (flag / drop) | - | rows flagged / dropped |
| remove_exact_duplicates | - | rows dropped |
| flag_duplicate_keys | - | rows marked |
| clip_outliers_iqr | values pulled to the fence | - |
| flag_only | - | - |

Columns are read as text (`profiling.py` reads every value as a string), so an
action writes a number or a timestamp only into the cells it changes; the
column widens to `object` when its dtype cannot hold the new value. A flag
column is added only when at least one cell is flagged, so a clean run leaves
no empty column in `cleaned.csv`.
"""

from collections.abc import Mapping
from typing import Any

import pandas as pd

from contracts.cleaning import TransformAction
from stages.ingest import column_kinds
from stages.ingest.changes import (
    FLAG_PREFIX,
    Params,
    Result,
    choice,
    convert,
    entry,
    flag,
    flag_column_name,
    is_missing,
    no_column,
    replace,
    required,
    series,
    show,
)
from stages.ingest.transform_catalog import CASE_MODES, CAST_TARGETS, NEGATIVE_STRATEGIES

__all__ = ["ACTIONS", "FLAG_PREFIX", "apply_action", "flag_column_name"]

BOOLEAN_TRUE = frozenset({"true", "t", "yes", "y", "1"})
BOOLEAN_FALSE = frozenset({"false", "f", "no", "n", "0"})


# --- missing values ---------------------------------------------------------


def impute_median(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    numbers = column_kinds.as_numbers(series(df, column, "impute_median"))
    return _fill(df, column, params, "impute_median", numbers.median(), "median")


def impute_mean(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    numbers = column_kinds.as_numbers(series(df, column, "impute_mean"))
    return _fill(df, column, params, "impute_mean", numbers.mean(), "mean")


def impute_mode(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    # pandas returns the modes sorted, so a tie is broken alphabetically and
    # the same column always gives the same answer.
    modes = column_kinds.as_text(series(df, column, "impute_mode")).mode()
    value = None if modes.empty else str(modes.iloc[0])
    return _fill(df, column, params, "impute_mode", value, "mode")


def impute_constant(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    value = required(params, "value", "impute_constant")
    if is_missing(value):
        raise ValueError("impute_constant needs a value that is not missing")
    return _fill(df, column, params, "impute_constant", value, "value")


def drop_rows_missing(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    missing = series(df, column, "drop_rows_missing").isna()
    dropped = int(missing.sum())
    detail = f"dropped {dropped} rows with no {column}"
    return df[~missing], entry("drop_rows_missing", column, params, rows=dropped, detail=detail)


# --- structure --------------------------------------------------------------


def drop_column(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    cells = len(series(df, column, "drop_column"))
    detail = f"removed the column and its {cells} cells"
    logged = entry("drop_column", column, params, cells=cells, detail=detail)
    return df.drop(columns=[column]), logged


def remove_exact_duplicates(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    no_column(column, "remove_exact_duplicates")
    # keep="first": the first occurrence is the row that stays.
    duplicated = df.duplicated(keep="first")
    dropped = int(duplicated.sum())
    detail = f"dropped {dropped} rows identical to an earlier row"
    logged = entry("remove_exact_duplicates", None, params, rows=dropped, detail=detail)
    return df[~duplicated], logged


# --- text and categories ----------------------------------------------------


def trim_whitespace(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    values = series(df, column, "trim_whitespace")
    changed = column_kinds.whitespace_mask(values)
    stripped = column_kinds.as_text(values).str.strip()
    detail = f"stripped surrounding whitespace from {int(changed.sum())} cells"
    return replace(df, column, params, "trim_whitespace", stripped, changed, detail)


def normalize_case(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    mode = choice(params, "mode", "normalize_case", CASE_MODES)
    values = series(df, column, "normalize_case")
    text = column_kinds.as_text(values)
    cased = {"title": text.str.title, "lower": text.str.lower, "upper": text.str.upper}[mode]()
    changed = values.notna() & text.ne(cased)
    detail = f"rewrote {int(changed.sum())} cells in {mode} case"
    return replace(df, column, params, "normalize_case", cased, changed, detail)


def standardize_categories(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    mapping = required(params, "mapping", "standardize_categories")
    if not isinstance(mapping, Mapping) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in mapping.items()
    ):
        raise ValueError("standardize_categories needs a mapping of text to text")
    values = series(df, column, "standardize_categories")
    text = column_kinds.as_text(values)
    # map() blanks every value the mapping does not name; where() puts them back.
    mapped = text.map(dict(mapping))
    merged = mapped.where(mapped.notna(), text)
    changed = values.notna() & text.ne(merged)
    detail = f"merged {int(changed.sum())} cells into {len(set(mapping.values()))} labels"
    return replace(df, column, params, "standardize_categories", merged, changed, detail)


# --- types ------------------------------------------------------------------


def parse_datetime(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    date_format = params.get("format")
    if date_format is not None and not isinstance(date_format, str):
        raise ValueError("parse_datetime needs format to be text")
    values = series(df, column, "parse_datetime")
    # No UTC fallback: this writes the dates into the data (see as_dates).
    parsed = column_kinds.as_dates(
        values, date_format, bool(params.get("dayfirst", False)), utc_fallback=False)
    shape = f"as {date_format}" if date_format else "per cell"
    return convert(df, column, params, "parse_datetime", parsed, "invalid_date",
                    "parsed {done} of {present} values " + shape)


def cast_type(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    target = choice(params, "target", "cast_type", CAST_TARGETS)
    values = series(df, column, "cast_type")
    return convert(df, column, params, "cast_type", _cast(values, target), "cast_failed",
                    "cast {done} of {present} values to " + target)


def _cast(values: pd.Series, target: str) -> pd.Series:
    """The column in the target type, with every value that does not convert
    left missing - never rounded, never coerced into a stand-in value."""
    if target == "string":
        return column_kinds.as_text(values)
    if target == "boolean":
        folded = column_kinds.as_text(values).str.strip().str.casefold()
        true, false = folded.isin(BOOLEAN_TRUE), folded.isin(BOOLEAN_FALSE)
        return pd.Series(True, index=values.index).where(true).mask(false, False).astype("boolean")
    numbers = column_kinds.as_numbers(values)
    if target == "float":
        return numbers
    # "integer": 3.7 is a failure, not a 4. Only whole numbers convert, and only
    # those an int64 can hold: "1e30" is whole but astype would raise, so it is
    # a flagged failure like any other cell that does not convert.
    whole = numbers.notna() & (numbers % 1 == 0) & (numbers >= -(2.0**63)) & (numbers < 2.0**63)
    return numbers.where(whole).astype("Int64")


# --- numbers ----------------------------------------------------------------


def fix_negative(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    strategy = choice(params, "strategy", "fix_negative", NEGATIVE_STRATEGIES, default="flag")
    values = series(df, column, "fix_negative")
    numbers = column_kinds.as_numbers(values)
    negative = numbers < 0  # a missing or non-numeric cell is never negative
    found = int(negative.sum())
    if strategy == "abs":
        detail = f"replaced {found} negative values with their absolute value"
        return replace(df, column, params, "fix_negative", numbers.abs(), negative, detail)
    if strategy == "drop":
        detail = f"dropped {found} rows with a negative {column}"
        logged = entry("fix_negative", column, params, rows=found, detail=detail)
        return df[~negative], logged
    return flag(df, column, params, "fix_negative", negative, "negative",
                 f"flagged {found} negative values")


def clip_outliers_iqr(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    k = params.get("k", column_kinds.DEFAULT_IQR_K)
    if isinstance(k, bool) or not isinstance(k, int | float) or k < 0:
        raise ValueError("clip_outliers_iqr needs k to be a number that is not negative")
    values = series(df, column, "clip_outliers_iqr")
    bounds = column_kinds.iqr_bounds(values, float(k))
    if bounds is None:
        return df, entry("clip_outliers_iqr", column, params,
                          detail="the column holds no numbers; nothing clipped")
    low, high = bounds
    outside = column_kinds.outlier_mask(values, float(k))
    clipped = column_kinds.as_numbers(values).clip(low, high)
    detail = f"clipped {int(outside.sum())} values into [{low}, {high}] (k={k})"
    return replace(df, column, params, "clip_outliers_iqr", clipped, outside, detail)


# --- flags ------------------------------------------------------------------


def flag_duplicate_keys(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    no_column(column, "flag_duplicate_keys")
    keys = required(params, "keys", "flag_duplicate_keys")
    if not isinstance(keys, list) or not keys or not all(isinstance(key, str) for key in keys):
        raise ValueError("flag_duplicate_keys needs a non-empty list of column names")
    unknown = [key for key in keys if key not in df.columns]
    if unknown:
        raise ValueError(f"flag_duplicate_keys: no such column: {unknown}")
    # keep=False marks every row of a repeated key, not only the later ones:
    # the plan flags a collision, it does not pick a winner.
    marked = df.duplicated(subset=keys, keep=False)
    detail = f"marked {int(marked.sum())} rows sharing a {', '.join(keys)} key"
    return flag(df, None, params, "flag_duplicate_keys", marked, "duplicate_key", detail)


def flag_only(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    series(df, column, "flag_only")  # the column has to exist to be reported on
    note = params.get("note", "")
    if not isinstance(note, str):
        raise ValueError("flag_only needs note to be text")
    return df, entry("flag_only", column, params, detail=note or "recorded; nothing changed")


ACTIONS: dict[TransformAction, Any] = {
    "impute_median": impute_median,
    "impute_mean": impute_mean,
    "impute_mode": impute_mode,
    "impute_constant": impute_constant,
    "drop_rows_missing": drop_rows_missing,
    "drop_column": drop_column,
    "parse_datetime": parse_datetime,
    "cast_type": cast_type,
    "trim_whitespace": trim_whitespace,
    "normalize_case": normalize_case,
    "standardize_categories": standardize_categories,
    "fix_negative": fix_negative,
    "remove_exact_duplicates": remove_exact_duplicates,
    "flag_duplicate_keys": flag_duplicate_keys,
    "clip_outliers_iqr": clip_outliers_iqr,
    "flag_only": flag_only,
}


def apply_action(
    action: TransformAction, df: pd.DataFrame, column: str | None, params: Params
) -> Result:
    """Run one catalog action. An action outside the catalog is refused here as
    well as by the contract's own type (AI_PIPELINE design principle 2)."""
    if action not in ACTIONS:
        raise ValueError(f"{action} is not in the transform catalog")
    return ACTIONS[action](df, column, params)


# --- imputation, shared by the four impute actions --------------------------


def _fill(
    df: pd.DataFrame,
    column: str | None,
    params: Params,
    action: TransformAction,
    value: Any,
    source: str,
) -> Result:
    """Every imputation: put `value` in the column's missing cells. A column
    with nothing to compute the value from (all null, or no numbers) is
    reported as untouched rather than filled with a guess."""
    values = series(df, column, action)
    if is_missing(value):
        return df, entry(action, column, params, detail=f"no {source} available; nothing filled")
    missing = values.isna()
    filled = int(missing.sum())
    detail = f"filled {filled} missing cells with {show(value)}"
    return replace(df, column, params, action, _constant(values, value), missing, detail)


def _constant(values: pd.Series, value: Any) -> pd.Series:
    return pd.Series([value] * len(values), index=values.index, dtype=object)
