"""The two actions that convert a column's type: `parse_datetime` and
`cast_type` (docs/AI_PIPELINE.md section 6).

Split out of `transforms.py`, which re-exports both, so it stays under the
300-line guideline (CLAUDE.md section 5). Both follow the rule the rest of the
catalog does: a value that does not convert is left missing and flagged, never
silently coerced (`changes.convert`).
"""

import pandas as pd

from stages.ingest import column_kinds
from stages.ingest.changes import Params, Result, choice, convert, series
from stages.ingest.transform_catalog import CAST_TARGETS

BOOLEAN_TRUE = frozenset({"true", "t", "yes", "y", "1"})


BOOLEAN_FALSE = frozenset({"false", "f", "no", "n", "0"})


def parse_datetime(df: pd.DataFrame, column: str | None, params: Params) -> Result:
    date_format = params.get("format")
    if date_format is not None and not isinstance(date_format, str):
        raise ValueError("parse_datetime needs format to be text")
    values = series(df, column, "parse_datetime")
    # This writes the dates into the data, so an offset is dropped rather than
    # read as UTC: the date stays the one the file says (see as_dates).
    parsed = column_kinds.as_dates(
        values, date_format, bool(params.get("dayfirst", False)), offsets="wall_clock")
    shape = f"as {date_format}" if date_format else "per cell"
    if column_kinds.has_utc_offset(values) and _reads_offsets(date_format):
        shape += "; UTC offsets dropped, dates kept as written"
    return convert(df, column, params, "parse_datetime", parsed, "invalid_date",
                    "parsed {done} of {present} values " + shape)


def _reads_offsets(date_format: str | None) -> bool:
    """Whether the offsets in the cells were read and dropped. A format without an
    offset directive does not read them: such a cell fails to match and is flagged
    like any other cell that does not."""
    return date_format is None or date_format == "ISO8601" or "%z" in date_format


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
