"""Stage 1 profiling: raw.csv -> profile.json (docs/CONTRACTS.md section 2).

Pure pandas + standard library. The file is read once, every value as raw
text: sample and top values show exactly what is in the file ("0012",
"12.50"), and numeric statistics come from converting fully numeric columns.
"""

import csv
import io
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from contracts.profile import (
    MAX_TOP_VALUES,
    ColumnProfile,
    DatasetStats,
    ProfileContract,
    TopValue,
)
from shared.run_registry import run_file
from stages.ingest.contract_files import write_contract

# pandas 3.0 read_csv defaults, listed here so the definition of "missing" is
# ours and cannot drift with a pandas upgrade (decided by Thach in 1B).
NA_TOKENS = [
    "", "#N/A", "#N/A N/A", "#NA", "-1.#IND", "-1.#QNAN", "-NaN", "-nan",
    "1.#IND", "1.#QNAN", "<NA>", "N/A", "NA", "NULL", "NaN", "None", "n/a",
    "nan", "null",
]
DELIMITER_CANDIDATES = ",;\t|"
SAMPLE_VALUES_PER_COLUMN = 5  # evenly spaced rows (decided by Thach in 1B)
SCHEMA_VERSION = "1.0"  # CONTRACTS.md section 1
RAW_FILENAME = "raw.csv"  # CONTRACTS.md section 1
PROFILE_FILENAME = "profile.json"

_SNIFF_CHARS = 64 * 1024
_NUMERIC_PROBE = 200
_UTF16_BOMS = (b"\xff\xfe", b"\xfe\xff")


class ProfilingError(Exception):
    """A file profiling cannot read. `code` is the SPECS section 10 code the
    caller reports; the stage does not know about HTTP."""

    code = "PARSE_FAILED"


class EmptyCsvError(ProfilingError):
    code = "EMPTY_FILE"


class CsvParseError(ProfilingError):
    code = "PARSE_FAILED"


@dataclass(frozen=True)
class ParsedCsv:
    frame: pd.DataFrame  # every column as text; missing values are NaN
    encoding: str
    delimiter: str


def read_csv_text(raw: bytes) -> ParsedCsv:
    text, encoding = _decode(raw)
    delimiter = _sniff_delimiter(text)
    try:
        frame = pd.read_csv(
            io.StringIO(text),
            sep=delimiter,
            dtype=str,
            keep_default_na=False,
            na_values=NA_TOKENS,
        )
    except pd.errors.EmptyDataError as error:
        raise EmptyCsvError("The file has no header and no rows.") from error
    except pd.errors.ParserError as error:
        raise CsvParseError(f"The file could not be parsed as CSV: {error}") from error
    if len(frame.index) == 0:
        # SPECS section 10: a header-only file is rejected like an empty one.
        raise EmptyCsvError("The file has a header row but no data rows.")
    return ParsedCsv(frame=frame, encoding=encoding, delimiter=delimiter)


def _decode(raw: bytes) -> tuple[str, str]:
    if raw.startswith(_UTF16_BOMS):
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError as error:
            raise CsvParseError("The file has a UTF-16 mark but is not valid UTF-16.") from error
    try:
        # utf-8-sig strips a BOM that would otherwise stick to the first
        # column name; the encoding is still reported as plain UTF-8.
        return raw.decode("utf-8-sig"), "utf-8"
    except UnicodeDecodeError:
        # SPECS section 10: latin-1 fallback. It decodes any byte sequence, so
        # 1A's cheaper NUL-byte check is what keeps binary files out.
        return raw.decode("latin-1"), "latin-1"


def _sniff_delimiter(text: str) -> str:
    sample = text[:_SNIFF_CHARS]
    if len(text) > _SNIFF_CHARS and "\n" in sample:
        sample = sample[: sample.rindex("\n")]  # never sniff a cut-off line
    try:
        return csv.Sniffer().sniff(sample, delimiters=DELIMITER_CANDIDATES).delimiter
    except csv.Error:
        header = sample.split("\n", 1)[0]
        if not any(candidate in header for candidate in DELIMITER_CANDIDATES):
            return ","  # a single-column file has no delimiter to find
        raise CsvParseError("The column delimiter could not be determined.") from None


def profile_column(name: str, values: pd.Series) -> ColumnProfile:
    """Statistics for one text column; `values` holds NaN for missing cells."""
    rows = len(values)
    missing = values.isna()
    present = values[~missing]
    null_count = int(missing.sum())
    numbers = _as_numbers(values, present)
    stats: dict[str, float | None]
    if numbers is None:
        stats = dict.fromkeys(("min", "max", "mean", "median", "q1", "q3"))
    else:
        found = numbers.dropna()
        stats = {
            "min": float(found.min()),
            "max": float(found.max()),
            "mean": float(found.mean()),
            # pandas' default linear interpolation for the median and quartiles.
            "median": float(found.median()),
            "q1": float(found.quantile(0.25)),
            "q3": float(found.quantile(0.75)),
        }
    counts = present.value_counts()  # one count per distinct raw text value
    return ColumnProfile(
        name=str(name),
        dtype="str" if numbers is None else str(numbers.dtype),
        null_count=null_count,
        null_pct=null_count / rows * 100 if rows else 0.0,
        # Raw text: "8.5" and "8.50" are two spellings of one number.
        unique_count=len(counts),
        **stats,
        top_values=_top_values(counts),
        sample_values=_sample_values(values),
    )


def _as_numbers(values: pd.Series, present: pd.Series) -> pd.Series | None:
    """The column as numbers when it has at least one value and every
    non-missing value is a finite number; otherwise None (a text column)."""
    if present.empty:
        return None
    # Cheap early answer for text columns: one non-number among the first
    # values already decides it, without converting the whole column (SPECS
    # section 11: profiling a 50MB file under 3 s). Same result, less work.
    if pd.to_numeric(present.iloc[:_NUMERIC_PROBE], errors="coerce").isna().any():
        return None
    # Converting the whole column keeps pandas' own typing: int64 when complete,
    # float64 when there are gaps.
    numbers = pd.to_numeric(values, errors="coerce")
    if numbers.isna().sum() != len(values) - len(present):
        return None  # a value further down is not a number: mixed types
    if not np.isfinite(numbers.dropna().to_numpy(dtype=float)).all():
        return None  # "inf" cannot round-trip through JSON
    return numbers


def _top_values(counts: pd.Series) -> list[TopValue]:
    """Top values by count, ties broken by value so the order never depends on
    pandas internals. Only values tied with the 10th place or above are
    sorted, not every distinct value of a high-cardinality column."""
    if counts.empty:
        return []
    cutoff = counts.iloc[min(MAX_TOP_VALUES, len(counts)) - 1]
    contenders = sorted(
        ((str(value), int(count)) for value, count in counts[counts >= cutoff].items()),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return [TopValue(value=v, count=c) for v, c in contenders[:MAX_TOP_VALUES]]


def _sample_values(values: pd.Series) -> list[str | None]:
    last = len(values) - 1
    positions = sorted({i * last // (SAMPLE_VALUES_PER_COLUMN - 1)
                        for i in range(SAMPLE_VALUES_PER_COLUMN)}) if last >= 0 else []
    return [None if pd.isna(v) else str(v) for v in values.iloc[positions]]


def profile_csv(raw: bytes, now: datetime | None = None) -> ProfileContract:
    parsed = read_csv_text(raw)
    frame = parsed.frame
    rows, columns = frame.shape
    missing = int(frame.isna().sum().sum())
    return ProfileContract(
        schema_version=SCHEMA_VERSION,
        generated_at=now or datetime.now(UTC),
        dataset=DatasetStats(
            rows=rows,
            columns=columns,
            # Exact-row duplicates of an earlier row; equal missing cells match.
            duplicate_rows=int(frame.duplicated().sum()),
            missing_cells_pct=missing / (rows * columns) * 100,
            encoding_used=parsed.encoding,
            delimiter=parsed.delimiter,
        ),
        columns=[profile_column(str(name), frame[name]) for name in frame.columns],
    )


def profile_run(runs_root: Path, run_id: str, now: datetime | None = None) -> ProfileContract:
    """Profile runs/<run_id>/raw.csv and write runs/<run_id>/profile.json."""
    profile = profile_csv(run_file(runs_root, run_id, RAW_FILENAME).read_bytes(), now)
    write_contract(run_file(runs_root, run_id, PROFILE_FILENAME), profile)
    return profile
