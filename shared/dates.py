"""Reading a date cell: one rule for every stage (Thach, session 2E-h).

Stage 1 decided in 1F how a written date becomes a date: a UTC offset is
dropped and the date and time are kept as written - read as UTC,
"2024-01-06 01:00+10:00" moved to 2024-01-05, and a report by day needs the
store's own date - and "now", "today", a bare time and a year outside
1900-2100 are no dates at all. Until 2E-h that rule lived in stage 1's
column_kinds and held only when the cleaning plan happened to parse the date
column: stage 2 and stage 3 read every date through `parse_transactions` as
UTC, so a +10:00 shop's current month, the sign of its change and its closed
weekday all moved (2E-f doubt-review cycle 4 F3). Now both read it here.
Stage 1 imports it (a stage may import shared/); its detectors keep the "utc"
mode, where only whether a cell parses matters.
"""

import re
from typing import Any, Literal

import pandas as pd

# A UTC offset after a time of day, in the forms people write: "10:00+01:00",
# "10:00:00.250-0500", "10:00Z", "10:00 +10", "10:00 -5", "10:00 UTC", "10:00 GMT+2".
# The time in front is required, so the "-05" at the end of "2024-01-05" is
# never taken for an offset. Group 1 is the seconds and fraction, kept when the
# offset is cut off.
UTC_OFFSET = re.compile(
    r"(?<=\d{2}:\d{2})((?::\d{2})?(?:\.\d+)?)"
    r"\s*(?:Z|UTC|GMT|(?:UTC|GMT)?[+-]\d{1,2}(?::?\d{2})?)$"
)
# Cells with no date in them. pandas reads "now" and "today" as the moment the run
# happens and "10:30" as 10:30 today, so the same file gave a different cleaned.csv
# on another day.
_NO_DATE_WORDS = frozenset({"now", "today"})
# pandas takes the run day's date for any cell that STARTS with a time,
# whatever follows: "10:30", "10:30Z", "10:30 a.m.", "10:30," were today, and
# "14:32 12 Aug" took this year - one such cell moved a whole report into the
# month of the run (2E-h doubt-review F2, cycle 2 F1, cycle 3 F1). Such a cell
# is a date only when it carries a year. A year is 1800-2199 standing alone,
# never the digits of an offset ("+1000").
_STARTS_WITH_TIME = re.compile(r"\s*\d{1,2}:\d{2}")
_YEAR = re.compile(r"(?<![+\-\d])(?:1[89]|2[01])\d{2}(?!\d)")
# A parsed year outside this range is not a date: pandas turns "Jan 5" into the
# year 1, and a date in 2150 or 1850 is a typo or a code in a sales file.
MIN_YEAR = 1900
MAX_YEAR = 2100
# A cell that may end in a zone the offset pattern did not strip: a "z", a
# zone name, or a sign and hours at its end.
_ZONE_HINT = re.compile(r"(?i)(?:z|utc|gmt|[+-]\d{1,2}(?::?\d{2})?)\s*$")
# The offset `_wall_clock` cuts off: UTC_OFFSET's forms, and also after a
# one-digit hour, after "AM"/"PM", and a lowercase zone - .NET writes
# "1/6/2024 9:15:02 AM -05:00", and a column of it across a daylight-saving
# change was read one cell at a time, ~280 s per read at 650,000 rows (2E-h
# doubt-review cycle 3 F4). UTC_OFFSET itself stays as stage 1's change log
# reads it (session 2E-j). Group 1 (seconds, fraction, AM/PM) is kept.
_ANY_OFFSET = re.compile(
    r"(?<=\d:\d{2})((?::\d{2})?(?:[.,]\d+)?(?:\s*[AaPp]\.?\s?[Mm]\.?)?)"
    r"\s*(?:[Zz]|UTC|GMT|utc|gmt|(?:UTC|GMT|utc|gmt)?[+-]\d{1,2}(?::?\d{2})?)$")
Offsets = Literal["utc", "wall_clock", "raise"]


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
    * "wall_clock" (for what writes or reads dates as data) drops the offset
      and keeps the date and time as written. Reading "2024-01-06 01:00+10:00"
      as UTC would move it to 2024-01-05, and a report by day needs the store's
      own date (decided by Thach in 1F). The result is never time-zone aware.
    * "raise" lets pandas' error through.
    """
    # Moved unchanged from stage 1's column_kinds (1F), so stage 1 behaves
    # exactly as before; `values.astype("str")` keeps missing cells missing.
    text = _dated_cells(values.astype("str"))
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
    timed_only = (folded.str.match(_STARTS_WITH_TIME, na=False)
                  & ~folded.str.contains(_YEAR, na=False))
    return text.mask(folded.isin(_NO_DATE_WORDS) | timed_only)


def _wall_clock(text: pd.Series, date_format: str | None, options: dict[str, Any]) -> pd.Series:
    """The same cells with their offsets cut off, parsed as plain date-times. A
    format with an offset directive loses it too, or nothing would match."""
    stripped = text.str.replace(_ANY_OFFSET, r"\1", regex=True)
    if date_format is not None:
        options = {"format": re.sub(r"\s*%z", "", date_format)}
    try:
        return pd.to_datetime(stripped, errors="coerce", **options)
    except ValueError:
        # A malformed explicit format must still fail, with its own message:
        # stage 1 refuses such a plan by this very call.
        if date_format is not None:
            raise
        # Offsets the pattern does not see - after "AM", after a one-digit
        # hour, a lowercase "z" - still mix zones, and pandas raised: stage 1's
        # check and stages 2 and 3 failed on a file the UTC reader had read
        # (2E-h doubt-review F1). Each distinct cell is read on its own, and
        # keeps the clock written in it.
        return _each_on_its_own_clock(stripped, options)


def _each_on_its_own_clock(text: pd.Series, options: dict[str, Any]) -> pd.Series:
    """Only the cells that may carry a zone are read one by one: sending the
    whole column through a scalar parse because of one stray cell was 290-360
    times slower (2E-h doubt-review cycle 2 F4). The hint is loose - a date
    ending "-05" is read alone too, harmlessly - and if a zone still slips
    past it, every distinct cell is read alone."""
    zoned = text.str.contains(_ZONE_HINT, na=False)
    try:
        plain = pd.to_datetime(text.where(~zoned), errors="coerce", **options)
    except ValueError:
        zoned = text.notna()
        plain = pd.Series(pd.NaT, index=text.index, dtype="datetime64[us]")
    # A zone the hint cannot see ("Sat Jan 06 01:00:00 +0000 2024") comes back
    # zone-aware; merged with the cells read alone it was no longer a date
    # column, and the reader crashed (cycle 3 F2). The written clock is kept.
    if plain.dt.tz is not None:
        plain = plain.dt.tz_localize(None)
    single = {key: value for key, value in options.items() if value != "mixed"}
    read: dict[str, pd.Timestamp] = {}
    for value in text[zoned].unique():
        try:
            stamp = pd.to_datetime(value, **single)
        except (ValueError, TypeError, OverflowError):
            stamp = pd.NaT
        if stamp is not pd.NaT and stamp.tzinfo is not None:
            stamp = stamp.tz_localize(None)
        # The year bound, here too: "9999-12-31" or "Aug 5" (the year 1) read
        # alone overflowed the column and crashed (cycle 3 F3).
        if stamp is not pd.NaT and not MIN_YEAR <= stamp.year <= MAX_YEAR:
            stamp = pd.NaT
        read[value] = stamp
    alone = pd.to_datetime(text[zoned].map(read), errors="coerce")
    return plain.where(~zoned, alone.reindex(text.index))
