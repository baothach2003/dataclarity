from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import CleaningReportContract
from shared.run_registry import create_run
from stages.analyze.metrics_core import (
    RequiredColumnMissingError,
    compute_core_metrics,
    core_metrics_for_run,
    select_period,
)

NOW = datetime(2026, 9, 19, 12, 0, tzinfo=UTC)

# source column name -> canonical field, deliberately not matching the
# canonical names, to prove metrics_core reads through the mapping rather
# than assuming a column is already named after its canonical field.
MAPPING = {
    "Date": "transaction_date",
    "Qty": "quantity",
    "Price": "unit_price",
    "Type": "transaction_type",
    "Cust": "customer",
}


def frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# --- period selection (docs/CONTRACTS.md section 6 worked example) ----------


def test_current_period_excludes_a_partial_latest_month() -> None:
    dates = pd.to_datetime(pd.Series(["2010-12-01", "2011-12-09"]))

    period = select_period(dates, NOW, dates)

    # data_end 2011-12-09: December has 31 days, 9 != 31, so December has not
    # fully elapsed and is excluded, exactly as docs/CONTRACTS.md section 6.
    assert (period.current, period.previous) == ("2011-11", "2011-10")
    assert (period.data_start, period.data_end) == (date(2010, 12, 1), date(2011, 12, 9))


def test_current_period_includes_the_latest_month_when_it_ends_on_its_last_day() -> None:
    dates = pd.to_datetime(pd.Series(["2011-11-01", "2011-11-30"]))

    period = select_period(dates, NOW, dates)

    assert (period.current, period.previous) == ("2011-11", "2011-10")


def test_january_rolls_the_previous_period_back_a_year() -> None:
    dates = pd.to_datetime(pd.Series(["2011-01-31"]))

    period = select_period(dates, NOW, dates)

    assert (period.current, period.previous) == ("2011-01", "2010-12")


def test_no_parseable_date_falls_back_to_now() -> None:
    dates = pd.to_datetime(pd.Series([None, None]))

    period = select_period(dates, NOW, dates)

    # NOW is 2026-09-19: September has 30 days, 19 != 30, so August is the
    # latest complete month relative to NOW.
    assert (period.current, period.previous) == ("2026-08", "2026-07")
    assert (period.data_start, period.data_end) == (date(2026, 9, 19), date(2026, 9, 19))


# --- compute_core_metrics: the hand-calculated scenario ---------------------


def _scenario() -> pd.DataFrame:
    return frame(
        [
            # previous period (2011-10): one sale, one customer
            {"Date": "2011-10-01", "Qty": "4", "Price": "8.0", "Type": "out", "Cust": "Carol"},
            # current period (2011-11): two sales + one return, two customers
            {"Date": "2011-11-05", "Qty": "3", "Price": "10.0", "Type": "out", "Cust": "Alice"},
            {"Date": "2011-11-20", "Qty": "2", "Price": "5.0", "Type": "out", "Cust": "Bob"},
            {"Date": "2011-11-30", "Qty": "-1", "Price": "10.0", "Type": "out", "Cust": "Alice"},
            # a restock: excluded from revenue/orders/customers entirely
            {"Date": "2011-11-10", "Qty": "5", "Price": "3.0", "Type": "in", "Cust": ""},
        ]
    )


def test_core_metrics_hand_calculated() -> None:
    period, core = compute_core_metrics(_scenario(), MAPPING, now=NOW)

    assert (period.current, period.previous) == ("2011-11", "2011-10")
    assert (period.data_start, period.data_end) == (date(2011, 10, 1), date(2011, 11, 30))

    # current: 3*10 + 2*5 + (-1)*10 = 30 + 10 - 10 = 30
    assert core.revenue_current == 30.0
    # 2E: an order is a sale row, so the return line is not one - 2 orders
    # (was 3). AOV is NET revenue over orders: 30 / 2 = 15.0 (was 30 / 3 =
    # 10.0). Return rate is return lines over orders: 1 / 2 = 0.5 (was 1 / 3).
    assert core.orders_current == 2
    assert core.active_customers_current == 2  # Alice, Bob
    assert core.aov_current == 15.0
    assert core.return_rate_current == pytest.approx(0.5)

    # previous: 4 * 8.0
    assert core.revenue_previous == 32.0
    assert core.orders_previous == 1
    assert core.active_customers_previous == 1  # Carol
    assert core.aov_previous == 32.0
    assert core.return_rate_previous == 0.0

    assert core.revenue_change_pct == pytest.approx(-6.25)  # (30 - 32) / 32 * 100

    assert [(m.period, m.revenue) for m in core.revenue_by_month] == [
        ("2011-10", 32.0),
        ("2011-11", 30.0),  # the restock (Nov 10) never enters this sum
    ]


# --- edge cases ---------------------------------------------------------


def test_zero_orders_in_the_previous_period_uses_the_zero_denominator_convention() -> None:
    df = frame([{"Date": "2011-11-30", "Qty": "2", "Price": "10.0", "Type": "out", "Cust": "Alice"}])

    period, core = compute_core_metrics(df, MAPPING, now=NOW)

    assert (period.current, period.previous) == ("2011-11", "2011-10")
    assert core.revenue_current == 20.0
    assert core.revenue_previous == 0.0
    assert core.orders_previous == 0
    # Were 0.0 under 2A's zero-denominator rule; October has no orders, so
    # there is no per-order figure (2E, superseding 2A).
    assert (core.aov_previous, core.return_rate_previous) == (None, None)
    assert "no orders in 2011-10" in core.aov_previous_reason
    # Was 0.0 ("revenue_previous == 0 -> 0.0 always", 2A), which read as
    # "nothing moved" on a month that went 0 -> 20. Since 2E October holds no
    # sale, so it is no base: unavailable, and the reason says so.
    assert core.revenue_change_pct is None
    assert "no sales in 2011-10" in core.revenue_change_pct_reason


def test_zero_orders_in_the_current_period_when_the_latest_month_is_partial() -> None:
    # data_end 2011-11-15 is not month-end, so current is October, which has
    # no data at all; the one row lands in revenue_by_month but in neither
    # the current nor the previous bucket.
    df = frame([{"Date": "2011-11-15", "Qty": "2", "Price": "10.0", "Type": "out", "Cust": "Alice"}])

    period, core = compute_core_metrics(df, MAPPING, now=NOW)

    assert (period.current, period.previous) == ("2011-10", "2011-09")
    assert core.revenue_current == 0.0
    assert core.orders_current == 0
    # Were 0.0 (2A); October has no orders (2E).
    assert (core.aov_current, core.return_rate_current) == (None, None)
    assert "no orders in 2011-10" in core.return_rate_current_reason
    assert core.revenue_previous == 0.0
    # Was 0.0; September holds no sale, so no comparison exists (2E).
    assert core.revenue_change_pct is None
    assert "no sales in 2011-09" in core.revenue_change_pct_reason
    assert [(m.period, m.revenue) for m in core.revenue_by_month] == [("2011-11", 20.0)]


def test_empty_dataframe_falls_back_to_now_and_reports_all_zeros() -> None:
    df = pd.DataFrame({"Date": [], "Qty": [], "Price": [], "Type": [], "Cust": []})

    period, core = compute_core_metrics(df, MAPPING, now=NOW)

    assert (period.current, period.previous) == ("2026-08", "2026-07")
    assert (period.data_start, period.data_end) == (date(2026, 9, 19), date(2026, 9, 19))
    assert core.revenue_current == core.revenue_previous == 0.0
    assert core.orders_current == core.orders_previous == 0
    assert core.active_customers_current == core.active_customers_previous == 0
    # Were 0.0 (2A); no orders in either month (2E).
    assert core.aov_current is None and core.aov_previous is None
    assert core.return_rate_current is None and core.return_rate_previous is None
    # Was 0.0; an empty file has no previous month to compare with (2E).
    assert core.revenue_change_pct is None
    assert core.revenue_change_pct_reason is not None
    assert core.revenue_by_month == []


def test_unmapped_transaction_type_counts_every_row_as_a_sale() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "transaction_type"}
    df = frame([{"Date": "2011-11-30", "Qty": "2", "Price": "10.0", "Cust": "Alice"}])

    _, core = compute_core_metrics(df, mapping, now=NOW)

    assert core.revenue_current == 20.0
    assert core.orders_current == 1


def test_unmapped_customer_reports_zero_active_customers() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "customer"}
    df = frame([{"Date": "2011-11-30", "Qty": "2", "Price": "10.0", "Type": "out"}])

    _, core = compute_core_metrics(df, mapping, now=NOW)

    assert core.active_customers_current == 0


def test_in_type_detection_is_case_and_whitespace_insensitive() -> None:
    df = frame(
        [
            {"Date": "2011-11-30", "Qty": "2", "Price": "10.0", "Type": " In ", "Cust": "Alice"},
            {"Date": "2011-11-30", "Qty": "3", "Price": "10.0", "Type": "OUT", "Cust": "Bob"},
        ]
    )

    _, core = compute_core_metrics(df, MAPPING, now=NOW)

    assert core.orders_current == 1  # only the OUT row counts
    assert core.revenue_current == 30.0  # 3 * 10.0


def test_unrecognized_type_value_defaults_to_counted_as_a_sale() -> None:
    df = frame([{"Date": "2011-11-30", "Qty": "2", "Price": "10.0", "Type": "transfer", "Cust": "Alice"}])

    _, core = compute_core_metrics(df, MAPPING, now=NOW)

    assert core.orders_current == 1
    assert core.revenue_current == 20.0


def test_unparseable_rows_are_excluded_not_guessed_at() -> None:
    df = frame(
        [
            {"Date": "not a date", "Qty": "2", "Price": "10.0", "Type": "out", "Cust": "Alice"},
            {"Date": "2011-11-30", "Qty": "not a number", "Price": "10.0", "Type": "out", "Cust": "Bob"},
            {"Date": "2011-11-30", "Qty": "2", "Price": "not a number", "Type": "out", "Cust": "Carol"},
            {"Date": "2011-11-30", "Qty": "1", "Price": "10.0", "Type": "out", "Cust": "Dana"},
        ]
    )

    _, core = compute_core_metrics(df, MAPPING, now=NOW)

    assert core.orders_current == 1  # only Dana's row parses cleanly on every field
    assert core.revenue_current == 10.0


@pytest.mark.parametrize("missing", ["transaction_date", "quantity", "unit_price"])
def test_a_required_column_not_mapped_raises(missing: str) -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != missing}
    df = frame([{"Date": "2011-11-30", "Qty": "2", "Price": "10.0", "Type": "out", "Cust": "Alice"}])

    with pytest.raises(RequiredColumnMissingError):
        compute_core_metrics(df, mapping, now=NOW)


# --- core_metrics_for_run: reads cleaned.csv + cleaning_report.json ---------


def test_core_metrics_for_run_reads_cleaned_csv_and_the_mapping(tmp_path: Path) -> None:
    run = create_run(tmp_path)
    (run.path / "cleaned.csv").write_text(
        "Date,Qty,Price,Type,Cust\n2011-11-30,2,10.0,out,Alice\n",
        encoding="utf-8",
    )
    report = CleaningReportContract(
        schema_version="2.0",  # 2E-e: order_id widened the enum (major)
        generated_at=NOW,
        rows_in=1,
        rows_out=1,
        columns_in=5,
        columns_out=5,
        changes=[],
        warnings=[],
        column_mapping=MAPPING,
    )
    (run.path / "cleaning_report.json").write_text(report.model_dump_json(), encoding="utf-8")

    period, core = core_metrics_for_run(tmp_path, run.run_id, now=NOW)

    assert period.current == "2011-11"
    assert core.revenue_current == 20.0
    assert core.orders_current == 1
