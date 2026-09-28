"""cleaned.csv's text (session 1D; split from `cleaning.py` in 2E-t3): the
frame as the file holds it, and the mapped columns read back as stages 2 and
3 read them - which execute classifies the lines on, and Review's whole-file
summary too."""

import io

import pandas as pd


def cleaned_csv_text(frame: pd.DataFrame) -> str:
    """The frame as the text of `cleaned.csv`: UTF-8 friendly, "\\n" line ends,
    the source column names, and dates in ISO 8601 (a date with no time as
    2024-01-05, otherwise 2024-01-05T10:30:00). Written here rather than left to
    pandas so the format is fixed and a test can check it by eye."""
    out = frame.copy(deep=False)  # only whole columns are replaced below
    for name in out.columns:
        if pd.api.types.is_datetime64_any_dtype(out[name]):
            out[name] = iso_dates(out[name])
    return out.to_csv(index=False, lineterminator="\n")


def iso_dates(values: pd.Series) -> pd.Series:
    """A datetime column as ISO 8601 text; the preview shows dates the same way."""
    present = values.dropna()
    if not present.empty and present.dt.microsecond.any():
        pattern = "%Y-%m-%dT%H:%M:%S.%f"
    elif not present.empty and (present.dt.hour | present.dt.minute | present.dt.second).any():
        pattern = "%Y-%m-%dT%H:%M:%S"
    else:
        pattern = "%Y-%m-%d"
    return values.dt.strftime(pattern)  # a missing date stays missing


def as_read(cleaned: pd.DataFrame, mapping: dict[str, str]) -> pd.DataFrame:
    """The mapped columns as stages 2 and 3 will read them - the text
    cleaned.csv holds, read back as text."""
    read = [source for source in mapping if source in cleaned.columns]
    return pd.read_csv(io.StringIO(cleaned_csv_text(cleaned[read])), dtype=str)
