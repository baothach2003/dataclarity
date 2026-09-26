"""Session 2E-e2 doubt-review cycle 2, written before the fixes.

- F3 (FABRICATE): the user's "No, a batch code" is honoured whatever the
  customer column holds - a plan that imputes it must not silence the answer.
- F4 (FABRICATE): a customer column that never names two different customers
  ("Walk-in" on every line) gives the check no customer to read: the order id
  is checked by date only, exactly as with no column.
- F5/F6: stage 1 says "not measured" (None), not 0, when no sale line parses
  on the raw file or blank ids make the raw file count lines - a fill the
  cleaning may still let happen. A 2.0 schema_inference.json measured nothing.
- F10 is in tests/backend/test_api_2ee2.py.
"""

from datetime import UTC, datetime

import pandas as pd

from contracts.cleaning import OrderConfirmations
from contracts.profile import SchemaInferenceContract
from shared.order_checks import order_checks
from shared.transactions import parse_transactions

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Inv": "order_id", "Cust": "customer"}


def _batches(customer: str | None) -> pd.DataFrame:
    """One Z-report code a day, walk-in lines only."""
    return pd.DataFrame({"Date": ["2026-08-03"] * 3 + ["2026-08-04"] * 3, "Qty": "1",
                         "Price": "10", "Inv": ["Z-0803"] * 3 + ["Z-0804"] * 3,
                         "Cust": customer})


def test_a_no_is_honoured_even_when_the_column_names_someone() -> None:
    """Asked because the raw column was blank; the plan imputed it, and the
    cleaned file names two customers ("Unknown" and a real one)."""
    df = _batches("Unknown")
    df.loc[0, "Cust"] = "Ann"

    parsed = parse_transactions(df, MAPPING, OrderConfirmations(order_id_is_receipt=False))

    assert parsed.orders_basis == "lines"
    assert parsed.orders_basis_reason == (
        "the order id column was marked in Review as not a receipt number (a batch or day "
        "code), so the figures count lines")


def test_one_placeholder_customer_on_every_line_is_no_customer_to_check_by() -> None:
    unanswered = parse_transactions(_batches("Walk-in"), MAPPING)
    confirmed = parse_transactions(_batches("Walk-in"), MAPPING,
                                   OrderConfirmations(order_id_is_receipt=True))

    assert unanswered.orders_basis == "lines"
    assert unanswered.orders_basis_reason == (
        "the order id column could be checked by date only (one customer is on most "
        "receipts), and it was not confirmed in Review as a receipt number, so the figures "
        "count lines")  # per receipt since 2E-k
    assert confirmed.orders_basis == "order_id"


def test_two_customers_are_enough_for_the_check() -> None:
    df = _batches("Ann")
    df.loc[3:, "Cust"] = "Bob"

    assert parse_transactions(df, MAPPING).orders_basis == "order_id"


def _header_style() -> pd.DataFrame:
    return pd.DataFrame([("2026-08-03", "1", "10", "R1", "Ann"), ("2026-08-03", "1", "40", "R1", None),
                         ("2026-08-04", "1", "30", "R2", "Bob")],
                        columns=["Date", "Qty", "Price", "Inv", "Cust"])


def test_the_fill_is_not_measured_when_no_sale_line_parses() -> None:
    df = _header_style().assign(Date="2026-08-03 10.15.00")

    assert order_checks(df, MAPPING).fill_lines is None


def test_the_fill_is_not_measured_when_blank_ids_make_the_raw_file_count_lines() -> None:
    df = _header_style()
    df.loc[2, "Inv"] = None

    assert order_checks(df, MAPPING).fill_lines is None


def test_the_fill_is_zero_not_unmeasured_without_a_customer_column() -> None:
    no_customer = {k: v for k, v in MAPPING.items() if v != "customer"}

    assert order_checks(_header_style().assign(Date="2026-08-03 10.15.00"), no_customer).fill_lines == 0


def test_a_2_0_schema_measured_nothing() -> None:
    schema = SchemaInferenceContract.model_validate({
        "schema_version": "2.0", "generated_at": NOW.isoformat(), "model_used": "m",
        "domain_confidence": 0.9, "domain_reasoning": "r", "dataset_issues": [], "columns": []})

    assert schema.receipt_fill_lines is None



def test_a_report_with_null_confirmations_reads_as_unanswered() -> None:
    """Cycle 3 F6: the plan maps null to "unanswered"; the report refused it."""
    from contracts.cleaning import CleaningReportContract

    report = CleaningReportContract.model_validate({
        "schema_version": "2.1", "generated_at": NOW.isoformat(), "rows_in": 1, "rows_out": 1,
        "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [], "column_mapping": {},
        "confirmations": None})

    assert report.confirmations == OrderConfirmations()
