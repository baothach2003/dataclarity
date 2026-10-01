"""Which months stage 2 compares (docs/CONTRACTS.md section 6), split out of
metrics_core.py in 2E-j for file size; metrics_core re-exports
`select_period`.
"""

import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from contracts.metrics import Period
from shared.periods import previous_coverage


def select_period(dates: pd.Series, now: datetime, counted_dates: pd.Series, *,
                  grain: bool = False) -> Period:
    """`current` is the latest calendar month fully elapsed by the data's
    last date (docs/CONTRACTS.md section 6's worked example: data_end
    2011-12-09 -> current 2011-11, the partial December excluded); `previous`
    is the month before it. Whether an earlier month has any data of its own
    does not matter for the choice, only whether that month's own last day has
    passed. Falls back to `now`'s month when the data holds no parseable date
    at all.

    Whether `previous` is a base to compare with is decided separately, over
    the SALE rows' dates (`counted_dates`; required, because neither a
    stock-in row nor a refund line may complete the month), by the definition
    stage 3 shares (shared/periods.py, 2E).

    In a month-grain file (`grain`: every counted line at midnight on the
    1st, or on the last day of its month - shared/date_evidence.month_grain;
    2E-j, 2E-o) such a line stands for its month, so no day says whether the last month is over: by the
    elapsed-day rule it was always dropped, and the report compared the two
    months before it. The file's last month with a SALE line is the current
    month once it has ended on every clock - `now` is UTC and the dates are
    the shop's, so 12 hours past its end in UTC: a monthly report pulled
    mid-month holds a month-to-date row, which compared as a whole month read
    -36.7% (2E-j review cycle 1 #1, cycle 2 #5). A sale month, not the last
    dated line: a later stock-in or template row made an empty month current
    (-100%, cycle 2 #1). The caller passes the run's upload as `now` (2E-u6):
    one pulled mid-month compares the month before however late it is
    analysed, and one uploaded within 12 hours after a month ends compares
    the month before too, for good - the safe side (a known limit)."""
    valid = dates.dropna()
    if valid.empty:
        data_start = data_end = now.date()
    else:
        data_start = valid.min().date()
        data_end = valid.max().date()

    sold = counted_dates.dropna()
    if grain and not sold.empty:
        last = (sold.max().year, sold.max().month)
        clock = now - timedelta(hours=12)
        current = last if last < (clock.year, clock.month) else _month_before(*last)
    else:
        current = _last_complete_month(data_end)
    previous = _format_year_month(_month_before(*current))
    coverage = previous_coverage(counted_dates, previous, month_grain=grain)
    return Period(
        current=_format_year_month(current),
        previous=previous,
        data_start=data_start,
        data_end=data_end,
        previous_complete=coverage.complete,
        previous_incomplete_reason=coverage.reason,
        month_grain=grain,
    )


def _last_complete_month(data_end: date) -> tuple[int, int]:
    year, month = data_end.year, data_end.month
    if data_end.day < calendar.monthrange(year, month)[1]:
        return _month_before(year, month)
    return year, month


def _month_before(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _format_year_month(year_month: tuple[int, int]) -> str:
    year, month = year_month
    return f"{year:04d}-{month:02d}"
