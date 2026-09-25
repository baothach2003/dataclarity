"""Session 2E-e2 (Thach), stages 2 and 3, written before the change: the
answers given in Review reach metrics.json and stage 3 through
cleaning_report.json, and a fill the user's No withheld is counted with a
reason rather than lost silently (unanswered, it fills - doubt-review A). metrics.json 9.0, diagnosis.json 8.0: the
order basis and every per-customer figure change meaning for a file whose
answers were not given.
"""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from contracts.cleaning import CleaningReportContract, OrderConfirmations
from contracts.diagnosis import DiagnosisContract
from contracts.metrics import CustomerMetrics, MetricsContract
from shared.run_registry import create_run
from stages.analyze.assemble import SCHEMA_VERSION, analyze_run, assemble_metrics
from stages.analyze.metrics_core import core_metrics_for_run
from stages.analyze.metrics_customers import customer_metrics_for_run
from stages.diagnose.inputs import build_run_data, load_run

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price",
           "Inv": "order_id", "Cust": "customer", "Prod": "product_name"}
FIRST_LINE = OrderConfirmations(customer_on_first_line_only=True)
NO = OrderConfirmations(customer_on_first_line_only=False)


def _header_style() -> pd.DataFrame:
    """August 2026, header-style: each receipt names its customer on its
    first line only. Ann's R1 (10 + 40) and R3 (5 + 5 + 5); Bob's R2 (30)."""
    rows = [("2026-08-03", "1", "10", "R1", "Ann"), ("2026-08-03", "1", "40", "R1", None),
            ("2026-08-10", "1", "30", "R2", "Bob"),
            ("2026-08-20", "1", "5", "R3", "Ann"), ("2026-08-20", "1", "5", "R3", None),
            ("2026-08-20", "1", "5", "R3", None),
            ("2026-09-01", "1", "1", "R4", "Cy")]
    return pd.DataFrame(rows, columns=["Date", "Qty", "Price", "Inv", "Cust"]).assign(Prod="Mug")


def test_a_withheld_fill_is_counted_with_its_reason() -> None:
    metrics = assemble_metrics(_header_style(), MAPPING, NOW, NO)

    assert metrics.customers.unfilled_receipt_lines == 3
    assert metrics.customers.unfilled_receipt_lines_reason == (
        "3 lines have no customer but share a receipt with a line that names one; they were "
        "not given that customer because the answer in Review was that the customer is not "
        "written on a receipt's first line only, so their revenue is in no customer's figures")


def test_one_unfilled_line_is_said_in_the_singular() -> None:
    df = _header_style().drop(index=[4, 5])

    customers = assemble_metrics(df, MAPPING, NOW, NO).customers

    assert customers.unfilled_receipt_lines == 1
    assert customers.unfilled_receipt_lines_reason.startswith(
        "1 line has no customer but shares a receipt with a line that names one; it was not given")
    assert customers.unfilled_receipt_lines_reason.endswith(
        "so its revenue is in no customer's figures")


def test_a_confirmed_fill_counts_nothing_unfilled_and_moves_the_money() -> None:
    unconfirmed = assemble_metrics(_header_style(), MAPPING, NOW, NO)
    confirmed = assemble_metrics(_header_style(), MAPPING, NOW, FIRST_LINE)

    assert (confirmed.customers.unfilled_receipt_lines,
            confirmed.customers.unfilled_receipt_lines_reason) == (0, None)
    # August: Ann 10 + 40 + 5 + 5 + 5 = 65, Bob 30 - all new customers.
    assert confirmed.customers.new_vs_returning.new_revenue == pytest.approx(95.0)
    # Answered No, only the named lines are theirs: 10 + 30 + 5.
    assert unconfirmed.customers.new_vs_returning.new_revenue == pytest.approx(45.0)
    # Orders are the same either way: 2E-e's order key keeps the receipt.
    assert confirmed.core.orders_current == unconfirmed.core.orders_current == 3


def test_a_file_the_fill_does_not_touch_counts_nothing() -> None:
    df = _header_style().assign(Cust=["Ann", "Ann", "Bob", "Ann", "Ann", "Ann", "Cy"])

    customers = assemble_metrics(df, MAPPING, NOW).customers

    assert (customers.unfilled_receipt_lines, customers.unfilled_receipt_lines_reason) == (0, None)


def test_the_count_and_its_reason_come_together() -> None:
    base = assemble_metrics(_header_style(), MAPPING, NOW, NO).customers.model_dump()

    with pytest.raises(ValidationError, match="unfilled_receipt_lines_reason"):
        CustomerMetrics.model_validate({**base, "unfilled_receipt_lines_reason": None})
    with pytest.raises(ValidationError, match="unfilled_receipt_lines_reason"):
        CustomerMetrics.model_validate({**base, "unfilled_receipt_lines": 0})


def test_the_receipt_answer_reaches_the_order_basis() -> None:
    df = _header_style().drop(columns=["Cust"])
    mapping = {k: v for k, v in MAPPING.items() if v != "customer"}

    unconfirmed = assemble_metrics(df, mapping, NOW)
    confirmed = assemble_metrics(df, mapping, NOW, OrderConfirmations(order_id_is_receipt=True))

    assert (unconfirmed.core.orders_basis, unconfirmed.core.orders_current) == ("lines", 6)
    assert (confirmed.core.orders_basis, confirmed.core.orders_current) == ("order_id", 3)


def test_stage_3_reads_the_same_answers_as_stage_2() -> None:
    df = _header_style()
    metrics = assemble_metrics(df, MAPPING, NOW, FIRST_LINE)

    confirmed = build_run_data(df, MAPPING, metrics, FIRST_LINE)
    unconfirmed = build_run_data(df, MAPPING, assemble_metrics(df, MAPPING, NOW, NO), NO)

    assert confirmed.parsed.customers[:3].tolist() == ["ann", "ann", "bob"]
    assert pd.isna(unconfirmed.parsed.customers[1])


def _run_with(tmp_path: Path, answers: OrderConfirmations, customers: bool = True) -> str:
    run = create_run(tmp_path)
    df = _header_style() if customers else _header_style().drop(columns=["Cust"])
    mapping = MAPPING if customers else {k: v for k, v in MAPPING.items() if v != "customer"}
    df.to_csv(run.path / "cleaned.csv", index=False)
    report = CleaningReportContract(schema_version="2.1", generated_at=NOW, rows_in=7, rows_out=7,
                                    columns_in=len(df.columns), columns_out=len(df.columns),
                                    changes=[], warnings=[], column_mapping=mapping,
                                    confirmations=answers)
    (run.path / "cleaning_report.json").write_text(report.model_dump_json(), encoding="utf-8")
    return run.run_id


def test_both_stages_read_the_answers_from_cleaning_report(tmp_path: Path) -> None:
    run_id = _run_with(tmp_path, NO)

    metrics = analyze_run(tmp_path, run_id, NOW)
    data = load_run(tmp_path, run_id)

    assert metrics.customers.unfilled_receipt_lines == 3
    assert pd.isna(data.parsed.customers[1])


def test_an_unanswered_run_fills(tmp_path: Path) -> None:
    run_id = _run_with(tmp_path, OrderConfirmations())

    metrics = analyze_run(tmp_path, run_id, NOW)

    assert metrics.customers.unfilled_receipt_lines == 0
    assert load_run(tmp_path, run_id).parsed.customers[1] == "ann"


def test_each_block_run_on_its_own_reads_the_answers_too(tmp_path: Path) -> None:
    """Mutation check E20/E21: stage 2's per-block runners read
    cleaning_report.json themselves."""
    withheld = _run_with(tmp_path, NO)
    receipt = _run_with(tmp_path, OrderConfirmations(order_id_is_receipt=True), customers=False)

    assert customer_metrics_for_run(tmp_path, withheld, NOW).unfilled_receipt_lines == 3
    assert core_metrics_for_run(tmp_path, receipt, NOW)[1].orders_basis == "order_id"


def test_versions() -> None:
    assert SCHEMA_VERSION == "9.0"
    assert MetricsContract.supported_major == 9
    assert DiagnosisContract.supported_major == 8
