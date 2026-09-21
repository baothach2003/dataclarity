"""Shared column detectors for stage 1 (transforms, issue counts, sample rows).

`raw.csv` is read with every value as text (`stages/ingest/profiling.py`), so a
"numeric" or "date" column here is text that converts, not a typed column.

Nothing in this module changes data: every function returns a view, a mask or a
statistic. Counting an issue (`issue_counts.py`) and fixing it (`transforms.py`)
therefore use one definition, so a plan cannot report 12 negatives and fix 11.
"""

import re
from typing import Any, Literal

import numpy as np
import pandas as pd

# A column counts as numeric / date when more than this share of its non-missing
# values convert. Above half there is one dominant kind, and the rest is dirt.
MAJORITY_SHARE = 0.5
DEFAULT_IQR_K = 1.5  # AI_PIPELINE section 6
# Rows a "what kind of column is this?" probe reads before the caller decides
# to convert the whole column (SPECS section 11: stage 1 stays inside 3 s).
PROBE_ROWS = 500
DIGIT_PROBE_CELLS = 100  # non-missing cells looked at for a digit before a date probe

# Recognised written date formats, tried in order; the first match names the
# cell's format. Only the shapes a spreadsheet export produces are listed - a
# cell matching none is "other", never a guess.
_TIME_SUFFIX = re.compile(r"[T ]\d{1,2}:\d{2}(:\d{2})?(\.\d+)?Z?$")
_DATE_FORMATS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iso", re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")),
    ("slash", re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$")),
    ("slash_year_first", re.compile(r"^\d{4}/\d{1,2}/\d{1,2}$")),
    ("dash", re.compile(r"^\d{1,2}-\d{1,2}-\d{2,4}$")),
    ("dot", re.compile(r"^\d{1,2}\.\d{1,2}\.\d{2,4}$")),
    ("month_name", re.compile(r"^(\d{1,2} )?[A-Za-z]{3,9},? \d{1,2}?,? ?\d{4}$")),
    ("compact", re.compile(r"^\d{8}$")),
)
OTHER_DATE_FORMAT = "other"
# A UTC offset after a time of day, in the forms people write: "10:00+01:00",
# "10:00:00.250-0500", "10:00Z", "10:00 +10", "10:00 -5", "10:00 UTC", "10:00 GMT+2".
# The time in front is required, so the "-05" at the end of "2024-01-05" is
# never taken for an offset. Group 1 is the seconds and fraction, kept when the
# offset is cut off.
_UTC_OFFSET = re.compile(
    r"(?<=\d{2}:\d{2})((?::\d{2})?(?:\.\d+)?)"
    r"\s*(?:Z|UTC|GMT|(?:UTC|GMT)?[+-]\d{1,2}(?::?\d{2})?)$"
)
# Cells with no date in them. pandas reads "now" and "today" as the moment the run
# happens and "10:30" as 10:30 today, so the same file gave a different cleaned.csv
# on another day.
_NO_DATE_WORDS = frozenset({"now", "today"})
_TIME_ONLY = re.compile(r"\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?\s*(?:am|pm)?")
# A parsed year outside this range is not a date: pandas turns "Jan 5" into the
# year 1, and a date in 2150 or 1850 is a typo or a code in a sales file.
MIN_YEAR = 1900
MAX_YEAR = 2100
Offsets = Literal["utc", "wall_clock", "raise"]


def as_text(values: pd.Series) -> pd.Series:
    """Every non-missing cell as text; missing cells stay missing."""
    return values.astype("str")


def as_numbers(values: pd.Series) -> pd.Series:
    """The column as numbers; text that is not a number becomes NaN, so a
    missing cell and a non-numeric cell are indistinguishable here. Use
    `non_numeric_mask` when the difference matters.

    Only finite numbers count, as in profiling: "inf", "Infinity" and "1e999" are
    text here. Read as infinity they would turn a mean into infinity and an
    absolute value into infinity, and be written to cleaned.csv."""
    numbers = pd.to_numeric(as_text(values), errors="coerce")
    return numbers.where(np.isfinite(numbers))


def as_dates(
    values: pd.Series,
    date_format: str | None = None,
    dayfirst: bool = False,
    offsets: Offsets = "utc",
) -> pd.Series:
    """The column as timestamps; anything unparseable becomes NaT.

    With no `date_format`, pandas parses each cell on its own ("mixed"), which
    is what a column of several formats needs. `dayfirst` then also decides
    "2024-01-05", so it is the caller's (the user's) choice, not a guess.

    Cells written with different UTC offsets cannot share one dtype, so
    `offsets` says what to do with them:

    * "utc" (the default, for detectors: is this a date? which cells are not?)
      reads every cell as UTC. Only whether a cell parses matters there.
    * "wall_clock" (for what writes dates into the data) drops the offset and
      keeps the date and time as written. Reading "2024-01-06 01:00+10:00" as UTC
      would move it to 2024-01-05, and a report by day needs the store's own
      date (decided by Thach in 1F). The result is never time-zone aware.
    * "raise" lets pandas' error through.
    """
    text = _dated_cells(as_text(values))
    if date_format is not None:
        options: dict[str, Any] = {"format": date_format}
    else:
        options = {"format": "mixed", "dayfirst": dayfirst}
    try:
        parsed = pd.to_datetime(text, errors="coerce", **options)
    except ValueError:
        # errors="coerce" does not cover mixed offsets. A malformed format fails
        # again below, with its own message, so nothing is hidden by the retry.
        if offsets == "raise":
            raise
        if offsets == "wall_clock":
            parsed = _wall_clock(text, date_format, options)
        else:
            parsed = pd.to_datetime(text, errors="coerce", utc=True, **options)
    if offsets == "wall_clock" and parsed.dt.tz is not None:
        parsed = parsed.dt.tz_localize(None)  # one shared offset: same rule, zone dropped
    return parsed.where(parsed.dt.year.between(MIN_YEAR, MAX_YEAR))


def _dated_cells(text: pd.Series) -> pd.Series:
    """The text with the cells that have no date in them made missing, so pandas
    never invents one for them."""
    folded = text.str.strip().str.casefold()
    return text.mask(folded.isin(_NO_DATE_WORDS) | folded.str.fullmatch(_TIME_ONLY, na=False))


def _wall_clock(text: pd.Series, date_format: str | None, options: dict[str, Any]) -> pd.Series:
    """The same cells with their offsets cut off, parsed as plain date-times. A
    format with an offset directive loses it too, or nothing would match."""
    stripped = text.str.replace(_UTC_OFFSET, r"\1", regex=True)
    if date_format is not None:
        options = {"format": re.sub(r"\s*%z", "", date_format)}
    return pd.to_datetime(stripped, errors="coerce", **options)


def has_utc_offset(values: pd.Series) -> bool:
    """Whether any cell is written with a UTC offset ("+01:00", "-0500", "Z")."""
    text = as_text(values)
    # A cell that has an offset is a cell the strip changes (str.contains would
    # warn about the capture group).
    return bool((text.str.replace(_UTC_OFFSET, r"\1", regex=True).ne(text) & text.notna()).any())


def present_mask(values: pd.Series) -> pd.Series:
    return values.notna()


def numeric_mask(values: pd.Series) -> pd.Series:
    """Cells holding a number."""
    return as_numbers(values).notna()


def non_numeric_mask(values: pd.Series) -> pd.Series:
    """Cells holding something that is neither missing nor a number."""
    return present_mask(values) & ~numeric_mask(values)


def date_mask(values: pd.Series, dayfirst: bool = False) -> pd.Series:
    return as_dates(values, dayfirst=dayfirst).notna()


def invalid_date_mask(values: pd.Series, dayfirst: bool = False) -> pd.Series:
    """Cells holding something that is neither missing nor a date."""
    return present_mask(values) & ~date_mask(values, dayfirst=dayfirst)


def whitespace_mask(values: pd.Series) -> pd.Series:
    """Cells with leading or trailing whitespace (issue code
    `trailing_whitespace`, fixed by `trim_whitespace`, which strips both)."""
    text = as_text(values)
    return present_mask(values) & text.ne(text.str.strip())


def share(mask: pd.Series, values: pd.Series) -> float:
    """The share of the non-missing cells that `mask` selects; 0.0 when the
    column holds nothing (no non-missing cell can then be anything)."""
    present = int(present_mask(values).sum())
    return int((mask & present_mask(values)).sum()) / present if present else 0.0


def is_mostly_numeric(values: pd.Series) -> bool:
    return share(numeric_mask(values), values) > MAJORITY_SHARE


def is_mostly_dates(values: pd.Series, dayfirst: bool = False) -> bool:
    return share(date_mask(values, dayfirst=dayfirst), values) > MAJORITY_SHARE


def probably_numeric(values: pd.Series, probe: int = PROBE_ROWS) -> bool:
    """A cheap majority test over the head of a column, for deciding which of
    many columns are worth converting in full. Same trade-off as profiling's
    numeric probe: a column that only turns numeric further down is missed."""
    return is_mostly_numeric(values.head(probe))


def probably_dates(values: pd.Series, probe: int = PROBE_ROWS) -> bool:
    """A cheap majority test over the head of a column. A date has a digit in it,
    so a column whose first cells hold none is not tried: converting 500 words on
    pandas' slow date path costs about 5 ms, per column, and a wide file has
    hundreds of columns."""
    head = values.head(probe)
    first_cells = head.dropna().head(DIGIT_PROBE_CELLS)
    if not first_cells.str.contains(r"\d", na=False).any():
        return False
    return is_mostly_dates(head)


def iqr_bounds(values: pd.Series, k: float = DEFAULT_IQR_K) -> tuple[float, float] | None:
    """[Q1 - k*IQR, Q3 + k*IQR] over the column's numbers, or None when it holds
    none. A column of one repeated value has IQR 0 and therefore bounds that
    equal that value: nothing outside it is normal there."""
    numbers = as_numbers(values).dropna()
    if numbers.empty:
        return None
    q1 = float(numbers.quantile(0.25))
    q3 = float(numbers.quantile(0.75))
    return q1 - k * (q3 - q1), q3 + k * (q3 - q1)


def outlier_mask(values: pd.Series, k: float = DEFAULT_IQR_K) -> pd.Series:
    """Numbers outside the IQR fence. Non-numeric and missing cells are never
    outliers: they are a different issue with a different fix."""
    bounds = iqr_bounds(values, k)
    if bounds is None:
        return pd.Series(False, index=values.index)
    numbers = as_numbers(values)
    return (numbers < bounds[0]) | (numbers > bounds[1])


def dominant_spelling(values: pd.Series) -> dict[str, str]:
    """For every case-folded label, the spelling that occurs most often (ties
    broken alphabetically, so the answer never depends on row order). The key
    is the folded label, which is what `inconsistent_case` groups by."""
    counts = as_text(values).dropna().value_counts()
    best: dict[str, tuple[int, str]] = {}
    for spelling, count in sorted((str(v), int(c)) for v, c in counts.items()):
        key = spelling.casefold()
        if key not in best or count > best[key][0]:
            best[key] = (count, spelling)
    return {key: spelling for key, (_, spelling) in best.items()}


def case_variant_mask(values: pd.Series) -> pd.Series:
    """Cells spelled differently from the dominant spelling of their label
    (issue code `inconsistent_case`): "cafe" among nine "Cafe" is one cell."""
    text = as_text(values)
    dominant = dominant_spelling(values)
    folded = text.str.casefold()
    expected = folded.map(dominant)
    return present_mask(values) & text.ne(expected)


def date_format_labels(values: pd.Series) -> pd.Series:
    """The written format of every cell that parses as a date: one of the
    `_DATE_FORMATS` names or "other". Cells that are not dates are NaN, so
    `value_counts()` over the result counts only real dates."""
    text = as_text(values).where(date_mask(values))
    stripped = text.str.strip().str.replace(_TIME_SUFFIX, "", regex=True)

    def label(value: object) -> object:
        if not isinstance(value, str):
            return value  # missing, or not a date
        for name, pattern in _DATE_FORMATS:
            if pattern.match(value):
                return name
        return OTHER_DATE_FORMAT

    return stripped.map(label)
