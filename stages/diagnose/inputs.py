"""What stage 3 reads, and the month vocabulary every step shares
(docs/AI_PIPELINE.md section 7.1).

Stage 3 reads three files from the run directory: `metrics.json` (stage 2's
output, which fixes the comparison period), `cleaned.csv` (row level, for
everything metrics.json does not already hold) and `cleaning_report.json` (the
column mapping). It recomputes figures that also exist in metrics.json and
must match them exactly - a dedicated test enforces that, because two stages
disagreeing on a definition would make the report contradict itself. This is
why the row-level definitions come from `shared/transactions.py` rather than
being restated here.
"""

import calendar
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from contracts.metrics import MetricsContract
from shared.run_registry import run_file
from shared.transactions import ParsedTransactions, parse_transactions

CLEANED_FILENAME = "cleaned.csv"
CLEANING_REPORT_FILENAME = "cleaning_report.json"
METRICS_FILENAME = "metrics.json"


@dataclass(frozen=True)
class RunData:
    """One run's rows, parsed, plus stage 2's own conclusions about them."""

    df: pd.DataFrame
    parsed: ParsedTransactions
    metrics: MetricsContract
    # "YYYY-MM" per row; the label of an unparseable date never matches a real
    # month, and such rows are excluded by `parsed.counted` anyway.
    months: pd.Series
    # Every calendar month fully covered by the file, ascending. See
    # `complete_months` for why "fully covered" and not "touched".
    complete_months: list[str]
    # Of those, the ones that actually contain a revenue-counted row. A month
    # can be complete by the calendar and hold nothing at all, and the two
    # must not be confused: a month with no rows is evidence of a gap, never
    # evidence of what "normal" looks like (3B doubt-review finding 2).
    months_with_rows: set[str]


def load_run(runs_root: Path, run_id: str) -> RunData:
    report = CleaningReportContract.model_validate_json(
        run_file(runs_root, run_id, CLEANING_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    metrics = MetricsContract.model_validate_json(
        run_file(runs_root, run_id, METRICS_FILENAME).read_text(encoding="utf-8")
    )
    frame = pd.read_csv(run_file(runs_root, run_id, CLEANED_FILENAME), dtype=str)
    return build_run_data(frame, report.column_mapping, metrics, report.confirmations)


def build_run_data(
    df: pd.DataFrame, column_mapping: dict[str, str], metrics: MetricsContract,
    confirmations: OrderConfirmations | None = None,
) -> RunData:
    """The pure half of `load_run`, so tests need no run directory.
    `confirmations` are cleaning_report.json's answers from Review, read
    exactly as stage 2 read them (2E-e2)."""
    parsed = parse_transactions(df, column_mapping, confirmations)
    months = parsed.dates.dt.to_period("M").astype(str)
    covered = complete_months(metrics.period.data_start, metrics.period.data_end)
    return RunData(
        df=df,
        parsed=parsed,
        metrics=metrics,
        months=months,
        complete_months=covered,
        months_with_rows=set(months[parsed.counted].unique()) & set(covered),
    )


def money_moved(data: RunData) -> float:
    """Sum of |amount| over the revenue-counted rows of both compared months:
    the scale floating-point residue is judged against. Row by row, exactly as
    stage 2 computes it, so the two stages call the same change "nothing"
    (2E doubt-review cycle 3: a gross that netted negative-price lines away
    let stage 3 headline a +0.00 change stage 2 had called nothing)."""
    period = data.metrics.period
    both = data.parsed.counted & data.months.isin([period.previous, period.current])
    return float(data.parsed.revenue_amounts[both].abs().sum())


def period_mask(data: RunData, month: str) -> pd.Series:
    """The revenue-counted rows of one month. Every step 5 lens starts here, so
    that "what is in this period" is decided once rather than per lens."""
    return data.parsed.counted & (data.months == month)


def complete_months(data_start: date, data_end: date) -> list[str]:
    """Calendar months the file covers from their first day to their last,
    ascending.

    Deliberately stricter than 2A's `select_period`, which asks only whether a
    month has *elapsed* by `data_end` (a shop whose first sale is on the 15th
    did not have half a March, it just opened mid-March - so March is a fair
    "current" period). A monthly baseline is a different question: a first
    month holding 16 days of data is a low point that never happened, and
    feeding it to an XmR chart widens the limits or fakes a signal. So a month
    counts here only if the file covers all of it.

    Session 3B's call, not written in DIAGNOSE_DESIGN; flagged for veto.
    """
    months: list[str] = []
    year, month = data_start.year, data_start.month
    while (year, month) <= (data_end.year, data_end.month):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        if first >= data_start and last <= data_end:
            months.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return months


def month_dates(year_month: str) -> pd.DatetimeIndex:
    """Every calendar date in a "YYYY-MM" month."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    return pd.date_range(
        date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1]), freq="D"
    )


def days_in_month(year_month: str) -> int:
    year, month = int(year_month[:4]), int(year_month[5:7])
    return calendar.monthrange(year, month)[1]


def shift_month(year_month: str, months: int) -> str:
    """"2011-11" shifted by a signed number of months."""
    year, month = int(year_month[:4]), int(year_month[5:7])
    index = year * 12 + (month - 1) + months
    return f"{index // 12:04d}-{index % 12 + 1:02d}"
