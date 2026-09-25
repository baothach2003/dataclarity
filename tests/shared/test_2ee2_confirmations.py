"""Session 2E-e2 (Thach), the shared reading, written before the change: two
answers the user gives in Review reach every stage that reads orders and
customers.

- No customer column: an order id can be checked by date only, and a daily
  batch or Z-report code passes that check. Unless the user confirmed in
  Review that the column is a receipt number, the figures count lines
  (Thach: "unconfirmed means untrusted").
- The 2E-f customer fill (a receipt's unnamed lines are its named
  customer's) is withheld when the user answers that the customer is not
  written on a receipt's first line only (2E-f known limit L1); unanswered,
  it happens (doubt-review A, test_2ee2_review.py). The ORDER KEY keeps
  2E-e's fill: that is order counting, not money.
- A withheld fill that would have happened is counted.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest

from contracts.cleaning import CleaningPlanContract, CleaningReportContract, OrderConfirmations
from contracts.profile import SchemaInferenceContract
from shared.order_checks import receipt_fill_lines
from shared.transactions import parse_transactions

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
NO_CUSTOMER = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Inv": "order_id"}
WITH_CUSTOMER = {**NO_CUSTOMER, "Cust": "customer"}
RECEIPT = OrderConfirmations(order_id_is_receipt=True)
FIRST_LINE = OrderConfirmations(customer_on_first_line_only=True)
NO = OrderConfirmations(customer_on_first_line_only=False)


def _receipts() -> pd.DataFrame:
    """Two receipts on two days, two lines each, no customer column."""
    return pd.DataFrame([("2026-08-03", "1", "10", "R1"), ("2026-08-03", "2", "5", "R1"),
                         ("2026-08-04", "1", "30", "R2"), ("2026-08-04", "1", "20", "R2")],
                        columns=["Date", "Qty", "Price", "Inv"])


def _header_style() -> pd.DataFrame:
    """ERP "invoice detail" export: the customer on each receipt's first line
    only. R1 is Ann's (10 + 40), R2 has no customer at all, R3 is Cy's - two
    customers, so the order id check reads customers, not dates only."""
    return pd.DataFrame([("2026-08-03", "1", "10", "R1", "Ann"), ("2026-08-03", "1", "40", "R1", None),
                         ("2026-08-04", "1", "30", "R2", None), ("2026-08-05", "1", "20", "R3", "Cy")],
                        columns=["Date", "Qty", "Price", "Inv", "Cust"])


# --- contracts ------------------------------------------------------------------


def test_a_plan_without_answers_has_none_and_a_2_0_plan_still_reads() -> None:
    plan = CleaningPlanContract.model_validate({
        "schema_version": "2.0", "generated_at": NOW.isoformat(), "source": "manual",
        "dataset_actions": [], "column_actions": []})

    assert plan.confirmations == OrderConfirmations()
    assert plan.confirmations.order_id_is_receipt is None
    assert plan.confirmations.customer_on_first_line_only is None


def test_answers_round_trip_through_the_plan_and_the_report() -> None:
    answers = OrderConfirmations(order_id_is_receipt=True, customer_on_first_line_only=False)
    plan = CleaningPlanContract(schema_version="2.1", generated_at=NOW, source="manual",
                                dataset_actions=[], column_actions=[], confirmations=answers)
    report = CleaningReportContract(schema_version="2.1", generated_at=NOW, rows_in=1, rows_out=1,
                                    columns_in=1, columns_out=1, changes=[], warnings=[],
                                    column_mapping={}, confirmations=answers)

    assert CleaningPlanContract.model_validate_json(plan.model_dump_json()).confirmations == answers
    assert CleaningReportContract.model_validate_json(report.model_dump_json()).confirmations == answers


def test_a_2_0_report_reads_as_nothing_confirmed() -> None:
    report = CleaningReportContract.model_validate({
        "schema_version": "2.0", "generated_at": NOW.isoformat(), "rows_in": 1, "rows_out": 1,
        "columns_in": 1, "columns_out": 1, "changes": [], "warnings": [], "column_mapping": {}})

    assert report.confirmations == OrderConfirmations()


def test_a_2_0_schema_carries_no_fill_measure() -> None:
    # 0 in the first RED set; None ("not measured") since review cycle 2 F5.
    schema = SchemaInferenceContract.model_validate({
        "schema_version": "2.0", "generated_at": NOW.isoformat(), "model_used": "m",
        "domain_confidence": 0.9, "domain_reasoning": "r", "dataset_issues": [], "columns": []})

    assert schema.receipt_fill_lines is None


# --- no customer column: the receipt question ----------------------------------------


def test_an_order_id_checked_by_date_only_counts_lines_until_confirmed() -> None:
    parsed = parse_transactions(_receipts(), NO_CUSTOMER)

    assert parsed.orders_basis == "lines"
    assert parsed.orders_basis_reason == (
        "the order id column could be checked by date only (there is no customer column), and "
        "it was not confirmed in Review as a receipt number, so the figures count lines")
    assert parsed.order_key.nunique() == 4


def test_a_confirmed_receipt_number_counts_orders() -> None:
    parsed = parse_transactions(_receipts(), NO_CUSTOMER, RECEIPT)

    assert (parsed.orders_basis, parsed.orders_basis_reason) == ("order_id", None)
    assert parsed.order_key.nunique() == 2


def test_a_column_the_user_called_a_batch_code_counts_lines() -> None:
    parsed = parse_transactions(_receipts(), NO_CUSTOMER,
                                OrderConfirmations(order_id_is_receipt=False))

    assert parsed.orders_basis == "lines"
    assert parsed.orders_basis_reason == (
        "the order id column was marked in Review as not a receipt number (a batch or "
        "day code), so the figures count lines")


def test_with_a_customer_column_the_question_is_not_needed() -> None:
    df = _receipts().assign(Cust=["Ann", "Ann", "Bob", "Bob"])

    parsed = parse_transactions(df, WITH_CUSTOMER)

    assert (parsed.orders_basis, parsed.orders_basis_reason) == ("order_id", None)


def test_blank_ids_still_fall_back_with_their_exact_count_when_confirmed() -> None:
    df = _receipts()
    df.loc[1, "Inv"] = "  "

    parsed = parse_transactions(df, NO_CUSTOMER, RECEIPT)

    assert parsed.orders_basis_reason == (
        "1 of 4 sale and return lines have no order id, so orders cannot be counted by id; "
        "the figures count lines")


# --- the customer fill -------------------------------------------------------------


def test_a_no_leaves_the_line_unattributed_but_one_order() -> None:
    parsed = parse_transactions(_header_style(), WITH_CUSTOMER, NO)

    assert parsed.customers[0] == "ann" and pd.isna(parsed.customers[1])
    assert parsed.order_key[0] == parsed.order_key[1]  # 2E-e: one receipt, one order
    assert parsed.receipt_fillable.tolist() == [False, True, False, False]


def test_a_confirmed_fill_gives_the_line_its_receipts_customer() -> None:
    parsed = parse_transactions(_header_style(), WITH_CUSTOMER, FIRST_LINE)

    assert parsed.customers[:2].tolist() == ["ann", "ann"]
    assert pd.isna(parsed.customers[2])  # R2 names nobody: nothing to take
    assert parsed.receipt_fillable.tolist() == [False, True, False, False]


def test_an_unanswered_fill_question_fills() -> None:
    parsed = parse_transactions(_header_style(), WITH_CUSTOMER)

    assert parsed.customers[:2].tolist() == ["ann", "ann"]


def test_the_receipt_answer_does_not_answer_the_fill() -> None:
    parsed = parse_transactions(_header_style(), WITH_CUSTOMER,
                                OrderConfirmations(order_id_is_receipt=True,
                                                   customer_on_first_line_only=False))

    assert pd.isna(parsed.customers[1])


def test_a_stock_in_line_is_never_counted_as_fillable() -> None:
    df = _header_style().assign(Type=["out", "in", "out", "out"])
    mapping = {**WITH_CUSTOMER, "Type": "transaction_type"}

    parsed = parse_transactions(df, mapping, FIRST_LINE)

    assert parsed.receipt_fillable.tolist() == [False, False, False, False]


def test_receipt_fill_lines_measures_what_the_fill_would_give() -> None:
    assert receipt_fill_lines(_header_style(), WITH_CUSTOMER) == 1


def test_receipt_fill_lines_is_zero_without_a_customer_or_an_order_id() -> None:
    no_order_id = {k: v for k, v in WITH_CUSTOMER.items() if v != "order_id"}

    assert receipt_fill_lines(_header_style(), NO_CUSTOMER) == 0
    assert receipt_fill_lines(_header_style(), no_order_id) == 0


def test_receipt_fill_lines_is_unmeasured_when_nothing_parses() -> None:
    # 0 in the first RED set; None ("not measured") since review cycle 2 F5.
    assert receipt_fill_lines(_header_style().assign(Price="$10"), WITH_CUSTOMER) is None
    assert receipt_fill_lines(_header_style(), {"Inv": "order_id", "Cust": "customer"}) is None


def test_receipt_fill_lines_does_not_parse_a_file_it_cannot_fill(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mutation check E8: the schema step pays a second parse of the raw file
    (~3 s at 50 MB) only when order_id and customer are both mapped."""
    from shared import transactions

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("parsed a file with nothing to fill")

    monkeypatch.setattr(transactions, "parse_transactions", refuse)

    assert receipt_fill_lines(_header_style(), NO_CUSTOMER) == 0
