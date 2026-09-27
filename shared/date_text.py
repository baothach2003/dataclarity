"""Finding a day-month-year or month-day-year date in a cell, and writing it
so pandas reads it in a decided order (sessions 2E-j, 2E-o; split from
dates.py for file size). "05/01/2026" is 5 January or 1 May; the order is
stage 1's decision, applied here only to such a date - ISO and a month in
words are left to pandas as before, and the rest of the cell stays, a
dotted time written with colons ("11.45 PM" -> "11:45 PM").
"""

import re
from typing import NamedTuple

import numpy as np
import pandas as pd

from contracts.profile import DateOrder

# A day-month-year or month-day-year date anywhere in a cell: two numbers of
# one or two digits and a year of two or four, each separated by / . - or
# spaces - "05/01/2026", "Mon 5.1.26", "10:30 05/01/2026", "'05/01/2026"
# (anchored at the start, the pattern missed all but the first, and `dayfirst`
# stopped reaching them - 2E-j review cycle 1 #2). Never inside ISO or a time:
# no digit, colon, dot, slash or dash before it, no digit or colon after,
# nor a separator and a digit that do not begin a time ("10.30 05-01-2026" read
# "10.30 05" as the date - 2E-j review cycle 3 #3; "05-01-2026-10:30",
# "-09h07" and "-11.45 PM" keep their date - 2E-o Q5 #2, review cycle 2 #4).
# Groups: first number, separator, second number, separator, year. Only such
# a date can be read two ways; ISO, a month name or a serial number cannot.
SHAPED = re.compile(r"(?<![\d:./\-])(\d{1,2})(\s*[/.\-]\s*|\s+)(\d{1,2})(\s*[/.\-]\s*|\s+)"
                    r"(\d{4}|\d{2})(?![\d:]|[/.\-]\d(?!\d?(?::|h\d|\.\d{2})))")
# Every candidate in a cell, overlapping (a dotted time may overlap its date).
_CANDIDATES = re.compile("(?=(" + SHAPED.pattern + "))")
# A month in words: the cell's date is written in words ("05-JAN-26
# 10.30.00 AM"), so a numeric triple in it is a time (2E-o review cycle 1 #1).
_MONTH_NAME = re.compile(r"(?i)(?<![a-z])(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?"
                         r"|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?"
                         r"|dec(?:ember)?)(?![a-z])")
# A dotted time ("10.30", "10.05.30", "10.30h") - never one after a colon,
# which is a fraction of seconds ("10:30:45.12", review cycle 2 #1). Left
# beside an ISO date pandas read it as a date ("10.05.30 2026-01-05" was
# 2030-10-05); removed, it orphaned its "PM" (cycle 2 #3): written with colons.
_DOTTED_TIME = re.compile(r"(?<![\d.:])(\d{1,2})\.(\d{2})(?:\.(\d{2}))?h?(?![\d.:])")
_AM_PM = re.compile(r"\s*[AaPp]\.?\s?[Mm]\b")
# What may follow a two-digit year: only a colon time after a separator
# ("05/01/26-10:30"); ".01.26" after "10.30 05" is another date (review cycle 3
# #1).
_AFTER_SHORT_YEAR = re.compile(r"[/.\-]\d(?!\d?:)")
# A year-first date in the same cell ("2026-01-05 10.30.00", "2026/1/5"): the
# cell is not day-month-year, whatever else looks like one - a dotted time
# read as D.M.YY (2E-j review cycle 2 #2). Not a year closing another date
# ("03/11/2026-11.45 PM", 2E-o review cycle 2 #4).
_YEAR_FIRST = re.compile(r"(?<![\d/.\-])\d{4}\s*[/.\-]\s*\d{1,2}\s*[/.\-]\s*\d{1,2}(?!\d)")


def in_order_for_pandas(text: pd.Series, order: DateOrder) -> pd.Series:
    """The cells holding a day-month-year date rewritten so pandas reads them
    without a guess: a four-digit year as ISO ("2026-01-05 10:30"), a
    two-digit one month first (dateutil keeps its century rule); a cell
    `order` cannot hold is missing. Every other cell is untouched, so ISO is
    never reordered. Read per distinct value: a million rows hold a few
    thousand dates, and ISO also spares pandas its per-cell dateutil path
    (93 s against a few for a million DD/MM/YYYY cells, measured in 2E-j)."""
    codes, uniques = pd.factorize(text)
    distinct = np.array([_in_order(value, order) for value in uniques], dtype=object)
    read = pd.Series(distinct[codes] if len(distinct) else np.full(len(codes), None),
                     index=text.index, dtype="str")
    return read.mask(codes == -1)


class DateText(NamedTuple):
    """A day-month-year or month-day-year date found in a cell."""

    first: int
    second: int
    year: str  # as written: two digits or four
    start: int
    end: int
    text: str  # the date as written, trimmed
    dotted: bool  # both separators dots: may be a time ("10.30.00")


def day_month_year(value: str) -> DateText | None:
    """The day-month-year or month-day-year date in a cell, or None - also
    when the cell holds a year-first date, or a month in words (its date is
    in words, so a numeric triple is a time). Every candidate is found: a
    four-digit year wins; a dotted one loses to any other, and is refused
    before AM/PM - "10.05.30 05-01-2026" and "10.30.00 05/01/26" hold a
    dotted time, not a date of 2030 or 2000 (2E-o Q5 #3, review cycle 1
    #1)."""
    if _YEAR_FIRST.search(value) or _MONTH_NAME.search(value):
        return None
    found = [DateText(int(m.group(2)), int(m.group(4)), m.group(6), m.start(1), m.end(1),
                      m.group(1).strip(), "." in m.group(3) and "." in m.group(5))
             for m in _CANDIDATES.finditer(value)]
    found = [d for d in found if not (d.dotted and _AM_PM.match(value, d.end))
             and not (len(d.year) == 2 and _AFTER_SHORT_YEAR.match(value, d.end))
             # "1030" in "13 01 26 1030" is a time, not a year (review cycle 3 #3).
             and not (len(d.year) == 4 and not 1900 <= int(d.year) <= 2100)]
    better = [d for d in found if len(d.year) == 4] + [d for d in found if not d.dotted]
    if better:
        return better[0]
    # Two dotted candidates and nothing better ("09.15.00 05.01.26"): which is
    # the time cannot be told, and the leftmost won (review cycle 2 #5).
    return found[0] if len(found) == 1 else None


def _in_order(value: str, order: DateOrder) -> str | None:
    """The cell as pandas should read it in `order`: the date written ISO (a
    two-digit year month first) in its place; None when `order` cannot hold
    it; a cell with no such date unchanged."""
    date = day_month_year(value)
    if date is None:
        return value
    day, month = (date.first, date.second) if order == "day_first" else (date.second, date.first)
    if not 1 <= month <= 12:
        return None
    year = date.year
    written = f"{year}-{month:02d}-{day:02d}" if len(year) == 4 else f"{month}/{day}/{year}"
    # The rest of the cell stays (a time "10h30", "10 AM", an offset), a
    # dotted time written with colons, and a separator right after the date
    # a space: "2026-01-05.10:30:00" read as no date (2E-o Q5 #2, #3; review
    # cycles 1 and 2).
    after = value[date.end:]
    if after[:1] in ("/", ".", "-"):
        after = " " + after[1:]
    return (_DOTTED_TIME.sub(_colons, value[:date.start]) + written
            + _DOTTED_TIME.sub(_colons, after))


def _colons(match: re.Match[str]) -> str:
    return ":".join(part for part in match.groups() if part)
