"""Session 2E-j (Thach), stage 2, written before the change.

- The date order stage 1 recorded is the order stage 2 reads a date column
  that was not parsed in: the Australian shop's July and August.
- Placeholder dates (1900-01-01, 1970-01-01) and a day and month the order
  cannot hold are undated lines, counted with a reason that says so.
- A month-grain file (Thach, Q1 of 2E-h): every line on the 1st stands for
  its month, so the file's last month is the current month - by the
  elapsed-day rule it was dropped as "not over" and the report compared the
  two months before it (measured: 1,800 -> 1,800, the real change lost).
- metrics.json 14.0: Period.month_grain, and the same file can read other
  dates.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from contracts.metrics import MetricsContract
from shared.run_registry import create_run
from stages.analyze.assemble import SCHEMA_VERSION, analyze_run, assemble_metrics
from stages.analyze.period_selection import select_period
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, run_data

DAY_FIRST = OrderConfirmations(dates_day_first=True)


def australian_rows() -> list[dict]:
    """One sale of 100 a day, 1 July - 31 August 2026, written DD/MM/YYYY."""
    days = [date(2026, 7, 1) + timedelta(days=n) for n in range(62)]
    return [{"Date": day.strftime("%d/%m/%Y"), "Qty": "1", "Price": "100", "Product": "W",
             "Cust": "A"} for day in days]


def month_grain_rows() -> list[dict]:
    """24 months, 2024-01 to 2025-12, every line on the 1st: five products
    P0-P4 priced 10-14, three lines of 10 units each a month, so a month is
    30 x (10+11+12+13+14) = 1,800. In 2025-12 P4 is gone: 1,800 - 420 =
    1,380."""
    rows = []
    for index in range(24):
        year, month = 2024 + index // 12, index % 12 + 1
        for product in range(5):
            if index == 23 and product == 4:
                continue
            for line in range(3):
                rows.append({"Date": date(year, month, 1).isoformat(), "Qty": "10",
                             "Price": str(10.0 + product), "Product": f"P{product}",
                             "Cust": f"C{(index + line + product) % 10}"})
    return rows


def test_the_australian_shop_has_july_and_august() -> None:
    metrics = assemble_metrics(pd.DataFrame(australian_rows()), MAPPING, NOW, DAY_FIRST)

    assert (metrics.period.current, metrics.period.previous) == ("2026-08", "2026-07")
    assert [(m.period, m.revenue) for m in metrics.core.revenue_by_month] == [
        ("2026-07", 3100.0), ("2026-08", 3100.0)]
    assert metrics.core.undated_lines == 0


def test_stage_2_reads_the_order_stage_1_recorded(tmp_path: Path) -> None:
    """Through the files: the answer is none (the file proved day first), the
    order is in the report's date_order."""
    run = create_run(tmp_path)
    pd.DataFrame(australian_rows()).to_csv(run.path / "cleaned.csv", index=False)
    report = CleaningReportContract(
        schema_version="3.1", generated_at=NOW, rows_in=62, rows_out=62, columns_in=5,
        columns_out=5, changes=[], warnings=[], column_mapping=MAPPING,  # type: ignore[arg-type]  # plain strs for the Literals
        date_order="day_first")
    (run.path / "cleaning_report.json").write_text(report.model_dump_json(), encoding="utf-8")

    metrics = analyze_run(tmp_path, run.run_id, now=NOW)

    assert [m.period for m in metrics.core.revenue_by_month] == ["2026-07", "2026-08"]


def test_placeholder_dates_and_impossible_days_are_undated_with_a_reason() -> None:
    rows = [row | {"Date": cell} for row, cell in zip(
        australian_rows()[:3], ["1900-01-01", "01/13/2026", "1970-01-01 00:00:07"], strict=True)]

    metrics = assemble_metrics(pd.DataFrame(australian_rows() + rows), MAPPING, NOW, DAY_FIRST)

    assert metrics.core.undated_lines == 3
    reason = metrics.core.undated_lines_reason
    assert reason is not None
    assert "a placeholder date such as 1900-01-01 or 1970-01-01" in reason
    assert "a day and month the file's date order cannot hold" in reason


def test_a_month_grain_file_compares_its_last_month() -> None:
    metrics = assemble_metrics(pd.DataFrame(month_grain_rows()), MAPPING, NOW, None)

    assert metrics.period.month_grain is True
    assert (metrics.period.current, metrics.period.previous) == ("2025-12", "2025-11")
    assert (metrics.core.revenue_current, metrics.core.revenue_previous) == (1380.0, 1800.0)
    assert metrics.core.revenue_change_pct == pytest.approx((1380 / 1800 - 1) * 100)


def test_a_daily_file_is_not_month_grain() -> None:
    data = run_data(australian_rows(), confirmations=DAY_FIRST)

    assert data.metrics.period.month_grain is False


def test_a_daily_file_ending_on_the_first_still_drops_its_last_month() -> None:
    """The elapsed-day rule holds wherever a line carries a real day: a file
    ending on 1 September has one day of September."""
    rows = australian_rows() + [{"Date": "01/09/2026", "Qty": "1", "Price": "100",
                                 "Product": "W", "Cust": "A"}]

    metrics = assemble_metrics(pd.DataFrame(rows), MAPPING, NOW, DAY_FIRST)

    assert metrics.period.current == "2026-08"


def test_metrics_json_is_14_or_the_current_one() -> None:
    assert SCHEMA_VERSION == "15.0"
    assert MetricsContract.supported_major == 15


def test_the_receipt_check_by_date_says_the_date_is_a_month() -> None:
    """"The invoice day" (Q1): with no customer the order-id check reads the
    date only, and in a month-grain file the date is the month - a monthly
    batch code passes it. The reason says so; the receipt question decides."""
    rows = [row | {"Inv": f"{row['Date']}-{n % 3}"} for n, row in enumerate(month_grain_rows())]
    mapping = {k: v for k, v in MAPPING.items() if v != "customer"} | {"Inv": "order_id"}

    metrics = assemble_metrics(pd.DataFrame(rows), mapping, NOW, None)

    assert metrics.core.orders_basis == "lines"
    reason = metrics.core.orders_basis_reason
    assert reason is not None and "the file records months, not days" in reason


def test_a_month_grain_month_not_over_is_not_compared() -> None:
    """A monthly report pulled on 19 September holds September's month to
    date on the 1st: compared as a whole month it read -36.7% (review cycle
    1 #1). Until the run's clock is past it, August is the current month."""
    rows = [{"Date": date(2025 + n // 12, n % 12 + 1, 1).isoformat(), "Qty": "10", "Price": "10",
             "Product": "P0", "Cust": f"C{n % 5}"} for n in range(20)]  # 2025-01 .. 2026-08
    rows += [{"Date": "2026-09-01", "Qty": "6", "Price": "10", "Product": "P0", "Cust": "C0"}]

    metrics = assemble_metrics(pd.DataFrame(rows), MAPPING, NOW, None)  # NOW: 2026-09-19

    assert metrics.period.month_grain is True
    assert (metrics.period.current, metrics.period.previous) == ("2026-08", "2026-07")


def test_month_grain_is_judged_on_the_counted_lines() -> None:
    """Thach's words: every COUNTED line on the 1st. A line whose price does
    not parse, dated the 15th, no longer hides the grain (review cycle 1 #6)."""
    rows = month_grain_rows() + [{"Date": "2025-12-15", "Qty": "1", "Price": "",
                                  "Product": "P0", "Cust": "C0"}]

    metrics = assemble_metrics(pd.DataFrame(rows), MAPPING, NOW, None)

    assert metrics.period.month_grain is True
    assert metrics.period.current == "2025-12"


def test_the_current_month_holds_a_sale() -> None:
    """A later stock-in row made an empty month current: 1,200 -> 0, -100%
    (2E-j review cycle 2 #1). The last month with a sale line is current."""
    rows = [{"Date": date(2025 + n // 12, n % 12 + 1, 1).isoformat(), "Qty": "10", "Price": "10",
             "Product": "P0", "Cust": f"C{n % 5}", "Type": "sale"} for n in range(15)]  # 2025-01 .. 2026-03
    rows.append({"Date": "2026-04-01", "Qty": "50", "Price": "10", "Product": "P0", "Cust": "",
                 "Type": "in"})
    mapping = MAPPING | {"Type": "transaction_type"}

    metrics = assemble_metrics(pd.DataFrame(rows), mapping, NOW, None)

    assert metrics.period.month_grain is True
    assert (metrics.period.current, metrics.core.revenue_current) == ("2026-03", 100.0)


@pytest.mark.parametrize(("clock", "current"), [
    ("2026-04-01 05:00", "2026-02"),   # March is over in UTC, not yet in Honolulu
    ("2026-04-01 13:00", "2026-03"),   # over on every clock
])
def test_the_last_month_is_over_on_every_clock(clock: str, current: str) -> None:
    """`now` is UTC, the dates the shop's own: a month-to-date row must not be
    compared as a whole month anywhere (2E-j review cycle 2 #5)."""
    months = pd.Series(pd.to_datetime([f"2026-{m:02d}-01" for m in (1, 2, 3)]))
    now = pd.Timestamp(clock, tz="UTC").to_pydatetime()

    period = select_period(months, now, months, grain=True)

    assert period.current == current
