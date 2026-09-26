"""Session 2E-e2 doubt-review cycle 1, written before the fixes.

- A (FABRICATE): with the fill withheld by default, a header-style receipt's
  unnamed purchase lines lost their customer while its credit note's named
  line kept it, so a first-time buyer's history "opened with a refund" and
  she read as returning. Unanswered, the fill happens again (2E-f, the known
  limit L1 Thach accepted); only the user's "No" withholds it.
- C (FABRICATE): a customer column that is mapped but names nobody leaves the
  order id checked by date only, exactly like no customer column.
- G: the exact blank-id count is written even when the receipt question is
  unanswered.
- M: the schema step parses the raw file once for both of its order checks.
- N: the answers are booleans or null, never coerced from "yes" or 1, and a
  plan whose confirmations are null reads as unanswered.
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import CleaningPlanContract, OrderConfirmations
from shared import transactions
from shared.transactions import parse_transactions
from stages.analyze.assemble import assemble_metrics
from tests.ai_fakes import FakeMessages
from tests.stages.ingest.schema_answers import answer, column, profiled_run, run

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Inv": "order_id", "Cust": "customer", "Prod": "product_name"}
# Bob is on two of the three receipts - one customer on most receipts, which
# since 2E-k leaves the check on dates only - so the receipt question is
# answered Yes: these tests are about the fill.
NO = OrderConfirmations(order_id_is_receipt=True, customer_on_first_line_only=False)
RECEIPT = OrderConfirmations(order_id_is_receipt=True)


def _first_time_buyer_with_a_credit_note() -> pd.DataFrame:
    """Bob is a regular. On 5 August Ann buys a pen and a chair (the customer
    on the receipt's first line only) and returns the chair the same day on
    a one-line credit note that names her. By hand: Ann is new, with 10."""
    rows = [("2026-07-10", "1", "10", "R0", "Bob", "Pen"),
            ("2026-08-05", "1", "10", "R1", "Ann", "Pen"),
            ("2026-08-05", "1", "500", "R1", None, "Chair"),
            ("2026-08-05", "-1", "500", "C1", "Ann", "Chair"),
            ("2026-09-01", "1", "10", "R9", "Bob", "Pen")]
    return pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Inv", "Cust", "Prod"])


def test_an_unanswered_fill_question_fills_so_a_first_time_buyer_is_new() -> None:
    split = assemble_metrics(_first_time_buyer_with_a_credit_note(), MAPPING, NOW, RECEIPT).customers

    assert (split.new_vs_returning.new_customers, split.new_vs_returning.new_revenue) == (
        1, pytest.approx(10.0))
    assert (split.unfilled_receipt_lines, split.unfilled_receipt_lines_reason) == (0, None)


def test_only_the_users_no_withholds_the_fill_and_it_is_counted() -> None:
    customers = assemble_metrics(_first_time_buyer_with_a_credit_note(), MAPPING, NOW, NO).customers

    assert customers.unfilled_receipt_lines == 1
    assert customers.unfilled_receipt_lines_reason == (
        "1 line has no customer but shares a receipt with a line that names one; it was not "
        "given that customer because the answer in Review was that the customer is not written "
        "on a receipt's first line only, so its revenue is in no customer's figures")


def _receipts(customers: list[str | None]) -> pd.DataFrame:
    return pd.DataFrame({"Date": ["2026-08-03", "2026-08-03", "2026-08-04", "2026-08-04"],
                         "Qty": "1", "Price": "10", "Inv": ["R1", "R1", "R2", "R2"],
                         "Cust": customers})


def test_a_customer_column_that_names_nobody_is_no_customer_column() -> None:
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Inv": "order_id", "Cust": "customer"}

    unanswered = parse_transactions(_receipts([None, " ", None, ""]), mapping)
    confirmed = parse_transactions(_receipts([None, " ", None, ""]), mapping,
                                   OrderConfirmations(order_id_is_receipt=True))

    assert unanswered.orders_basis == "lines"
    assert unanswered.orders_basis_reason == (
        "the order id column could be checked by date only (most receipts name no customer), "
        "and it was not confirmed in Review as a receipt number, so the figures count lines")
    assert confirmed.orders_basis == "order_id"


def test_the_blank_id_count_is_written_when_the_receipt_question_is_unanswered() -> None:
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Inv": "order_id"}
    df = _receipts([None] * 4).drop(columns=["Cust"])
    df.loc[1, "Inv"] = None

    parsed = parse_transactions(df, mapping)

    assert parsed.orders_basis == "lines"
    assert parsed.orders_basis_reason == (
        "1 of 4 sale and return lines have no order id, so orders cannot be counted by id; "
        "the figures count lines. Also, the order id column could be checked by date only "
        "(there is no customer column), and it was not confirmed in Review as a receipt number")


def test_the_schema_step_parses_the_raw_file_once(tmp_path: Path,
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    csv = (b"Inv,Day,Qty,Price,Cust\nR1,2026-08-03,1,10,Ann\nR1,2026-08-03,1,40,\n"
           b"R2,2026-08-04,1,30,Bob\n")
    mapped = {"Inv": "order_id", "Day": "transaction_date", "Qty": "quantity",
              "Price": "unit_price", "Cust": "customer"}
    run_id = profiled_run(tmp_path, csv)
    real, calls = transactions.parse_transactions, []

    def counting(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(transactions, "parse_transactions", counting)
    reply = answer([column(n, mapped[n]) for n in mapped], dataset_issues=[])

    schema = run(tmp_path, run_id, FakeMessages(reply))

    assert schema.receipt_fill_lines == 1
    assert len(calls) == 1


def test_a_plan_with_null_confirmations_reads_as_unanswered() -> None:
    plan = CleaningPlanContract.model_validate({
        "schema_version": "2.1", "generated_at": NOW.isoformat(), "source": "manual",
        "dataset_actions": [], "column_actions": [], "confirmations": None})

    assert plan.confirmations == OrderConfirmations()


@pytest.mark.parametrize("value", ["yes", "0", 1])
def test_an_answer_is_a_boolean_never_coerced(value: object) -> None:
    with pytest.raises(ValidationError):
        OrderConfirmations.model_validate({"order_id_is_receipt": value})


def test_a_header_line_names_a_customer_but_a_restock_line_does_not() -> None:
    """Review C's rule, narrowed: any line but a stock-in may name the
    customers (a header line does, 2E-h cycle 2 F3); a "Warehouse" on
    restock lines alone leaves the order id checked by date only."""
    mapping = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
               "Inv": "order_id", "Cust": "customer", "Type": "transaction_type"}
    df = _receipts([None] * 4).assign(Type="out")
    restock = pd.DataFrame([{"Date": "2026-08-03", "Qty": "5", "Price": "2", "Inv": "S1",
                             "Cust": "Warehouse", "Type": "in"}])

    parsed = parse_transactions(pd.concat([df, restock], ignore_index=True), mapping)

    assert parsed.orders_basis == "lines"
    assert "most receipts name no customer" in parsed.orders_basis_reason  # per receipt since 2E-k
