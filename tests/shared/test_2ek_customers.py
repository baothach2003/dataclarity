"""Session 2E-k (Thach), stages 2 and 3, written before the change.

- A customer value the user confirmed in Review as a placeholder for walk-ins
  ("Guest", "Walk-in", "0") has no customer: its lines are unattributed in
  every figure of both stages, and counted with a reason in metrics.json.
- Q4, judged per receipt (the order-id check runs per receipt): when more
  than half of the receipts name no customer (after the receipt fill; a
  confirmed placeholder counts as none), or one customer is on more than half
  of them, or fewer than two customers are named, the check reads dates
  only and the receipt question decides. A header-style export - the
  customer on each receipt's first line - still passes: its receipts all
  carry a name.
- metrics.json 10.0, diagnosis.json 9.0.
"""

from datetime import UTC, datetime

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import OrderConfirmations
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import CustomerMetrics, MetricsContract
from shared.transactions import parse_transactions
from stages.analyze.assemble import SCHEMA_VERSION, assemble_metrics
from stages.diagnose.inputs import build_run_data

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Cust": "customer", "Prod": "product_name"}
GUEST = OrderConfirmations(customer_placeholders=["Guest"])


def _shop() -> pd.DataFrame:
    """August 2026: Ann 10, Bob 20, and three walk-ins written " guest " /
    "GUEST" / "Guest" (5 each). September 1: Ann again."""
    rows = [("2026-08-03", "10", "Ann"), ("2026-08-04", "20", "Bob"), ("2026-08-05", "5", " guest "),
            ("2026-08-06", "5", "GUEST"), ("2026-08-07", "5", "Guest"), ("2026-09-01", "1", "Ann")]
    return pd.DataFrame([{"Date": d, "Qty": "1", "Price": p, "Cust": c, "Prod": "Mug"} for d, p, c in rows])


def test_a_confirmed_placeholder_has_no_customer_in_either_stage() -> None:
    parsed = parse_transactions(_shop(), MAPPING, GUEST)
    metrics = assemble_metrics(_shop(), MAPPING, NOW, GUEST)
    data = build_run_data(_shop(), MAPPING, metrics, GUEST)

    assert parsed.customers.isna().tolist() == [False, False, True, True, True, False]
    assert data.parsed.customers.isna().tolist() == [False, False, True, True, True, False]
    # August: Ann and Bob are new (30); the walk-ins' 15 belong to no one.
    split = metrics.customers.new_vs_returning
    assert (split.new_customers, split.new_revenue) == (2, pytest.approx(30.0))
    assert metrics.core.active_customers_current == 2


def test_unanswered_the_placeholder_is_a_customer() -> None:
    metrics = assemble_metrics(_shop(), MAPPING, NOW)

    assert metrics.core.active_customers_current == 3  # ann, bob, guest
    assert (metrics.customers.placeholder_lines, metrics.customers.placeholder_lines_reason) == (0, None)


def test_the_placeholder_lines_are_counted_with_their_reason() -> None:
    customers = assemble_metrics(_shop(), MAPPING, NOW, GUEST).customers

    assert customers.placeholder_lines == 3
    assert customers.placeholder_lines_reason == (
        "3 lines carry a value confirmed in Review as a placeholder for walk-ins (Guest), so "
        "they have no customer and their revenue is in no customer's figures")


def test_one_placeholder_line_is_said_in_the_singular() -> None:
    df = _shop().drop(index=[2, 3])

    reason = assemble_metrics(df, MAPPING, NOW, GUEST).customers.placeholder_lines_reason

    assert reason == ("1 line carries a value confirmed in Review as a placeholder for walk-ins "
                      "(Guest), so it has no customer and its revenue is in no customer's figures")


def test_the_count_and_its_reason_come_together() -> None:
    base = assemble_metrics(_shop(), MAPPING, NOW, GUEST).customers.model_dump()

    with pytest.raises(ValidationError, match="placeholder_lines_reason"):
        CustomerMetrics.model_validate({**base, "placeholder_lines_reason": None})
    with pytest.raises(ValidationError, match="placeholder_lines_reason"):
        CustomerMetrics.model_validate({**base, "placeholder_lines": 0})


# --- Q4: the order-id check, judged per receipt ------------------------------------------

ORDERS = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
          "Inv": "order_id", "Cust": "customer"}


def _receipts(names: list[str | None]) -> pd.DataFrame:
    """One two-line receipt per name, each on its own day; the name on the
    receipt's first line only (header-style)."""
    rows = []
    for index, name in enumerate(names):
        day = f"2026-08-{index + 1:02d}"
        rows += [(day, f"R{index}", name), (day, f"R{index}", None)]
    return pd.DataFrame([{"Date": d, "Qty": "1", "Price": "10", "Inv": i, "Cust": c}
                         for d, i, c in rows])


def test_a_header_style_export_still_passes_the_check() -> None:
    parsed = parse_transactions(_receipts(["Ann", "Bob", "Cy", "Dee"]), ORDERS)

    assert (parsed.orders_basis, parsed.orders_basis_reason) == ("order_id", None)


def test_most_receipts_naming_no_customer_fall_back_to_the_question() -> None:
    parsed = parse_transactions(_receipts(["Ann", "Bob", None, None, None]), ORDERS)

    assert parsed.orders_basis_reason == (
        "the order id column could be checked by date only (most receipts name no customer), "
        "and it was not confirmed in Review as a receipt number, so the figures count lines")


def test_half_the_receipts_unnamed_is_not_most() -> None:
    parsed = parse_transactions(_receipts(["Ann", "Bob", None, None]), ORDERS)

    assert parsed.orders_basis == "order_id"


def test_one_customer_on_most_receipts_falls_back_to_the_question() -> None:
    parsed = parse_transactions(_receipts(["Walk-in", "Walk-in", "Walk-in", "Ann"]), ORDERS)

    assert parsed.orders_basis_reason == (
        "the order id column could be checked by date only (one customer is on most receipts), "
        "and it was not confirmed in Review as a receipt number, so the figures count lines")


def test_a_confirmed_placeholder_counts_as_no_customer_for_the_check() -> None:
    names = ["Guest", "Guest", "Ann", "Bob", "Cy"]

    unanswered = parse_transactions(_receipts(names), ORDERS)
    confirmed = parse_transactions(_receipts(names), ORDERS, GUEST)

    assert unanswered.orders_basis == "order_id"
    assert confirmed.orders_basis == "order_id"  # 2 of 5 receipts unnamed: not most
    three = parse_transactions(_receipts(["Guest", "Guest", "Guest", "Ann", "Bob"]), ORDERS, GUEST)
    assert "most receipts name no customer" in three.orders_basis_reason


def test_one_customer_everywhere_is_one_customer_on_most_receipts() -> None:
    parsed = parse_transactions(_receipts(["Ann"]), ORDERS)

    assert "one customer is on most receipts" in parsed.orders_basis_reason


def test_the_receipt_answer_still_decides() -> None:
    names = ["Ann", "Bob", None, None, None]

    yes = parse_transactions(_receipts(names), ORDERS, OrderConfirmations(order_id_is_receipt=True))

    assert yes.orders_basis == "order_id"


def test_versions() -> None:
    assert SCHEMA_VERSION == "11.0"  # 10.0 in 2E-k; 11.0 since 2E-d2
    assert MetricsContract.supported_major == 11
    assert DiagnosisContract.supported_major == 10


def test_a_named_and_an_unnamed_receipt_never_name_two_customers() -> None:
    """Mutation check K6: neither half is "most", and one name is not two."""
    parsed = parse_transactions(_receipts(["Ann", None]), ORDERS)

    assert "the receipts never name two different customers" in parsed.orders_basis_reason


def test_a_receipt_named_on_its_header_line_is_named() -> None:
    """Mutation check K21: the check reads each receipt's customer after the
    fill - a header line (no quantity) naming the receipt names its unnamed
    item lines."""
    rows = []
    for index, name in enumerate(["Ann", "Bob", "Cy"]):
        day = f"2026-08-{index + 1:02d}"
        rows += [{"Date": day, "Qty": "", "Price": "", "Inv": f"R{index}", "Cust": name},
                 {"Date": day, "Qty": "1", "Price": "10", "Inv": f"R{index}", "Cust": None}]

    parsed = parse_transactions(pd.DataFrame(rows), ORDERS)

    assert (parsed.orders_basis, parsed.orders_basis_reason) == ("order_id", None)


def test_a_placeholder_on_a_line_that_is_not_counted_is_not_counted() -> None:
    """Mutation check K14: placeholder_lines counts counted lines only."""
    df = pd.concat([_shop(), pd.DataFrame([{"Date": "2026-08-08", "Qty": "", "Price": "5",
                                            "Cust": "Guest", "Prod": "Mug"}])], ignore_index=True)

    assert assemble_metrics(df, MAPPING, NOW, GUEST).customers.placeholder_lines == 3


def test_a_placeholder_line_the_fill_names_is_not_counted_as_without_customer() -> None:
    """Review cycle 1 F5: the POS writes "Guest" until the loyalty card is
    scanned - the receipt fill names that line after the member, so
    placeholder_lines counts only the lines left with no customer."""
    rows = [("2026-08-03", "R1", "Guest"), ("2026-08-03", "R1", "Ann"),
            ("2026-08-04", "R2", "Guest"), ("2026-08-05", "R3", "Bob"), ("2026-08-06", "R4", "Cy")]
    df = pd.DataFrame([{"Date": d, "Qty": "1", "Price": "10", "Inv": i, "Cust": c, "Prod": "Mug"}
                       for d, i, c in rows])
    mapping = {**ORDERS, "Prod": "product_name"}

    customers = assemble_metrics(df, mapping, NOW, GUEST).customers

    assert customers.placeholder_lines == 1
