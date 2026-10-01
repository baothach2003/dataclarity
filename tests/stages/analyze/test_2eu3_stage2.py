"""2E-u3 (Thach, 2026-10-02; 2E-u F3), stage 2, written before the code: the
walk-in candidates stage 1 recorded as unanswered stay customers in every
figure (the standing no-guess rule) and are marked "suggested, not
confirmed" in metrics.json's customers block, with their lines. Every count
worked by hand."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from contracts.metrics import MetricsContract
from stages.analyze.assemble import analyze_run, assemble_metrics
from stages.ingest.cleaning import execute_run
from tests.stages.ingest.test_2eu3_stage1 import CSV, _plan
from tests.stages.ingest.cleaning_fixtures import NOW as STAGE1_NOW
from tests.stages.ingest.cleaning_fixtures import raw_run

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name",
           "Cust": "customer"}
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def _frame() -> pd.DataFrame:
    # December 2023 and January 2024, whole months; "Guest" 3 lines (1 in
    # December, 2 in January, one written "GUEST"), "-" 1 line in December.
    rows = [("2023-12-01", "Ann"), ("2023-12-05", "Guest"), ("2023-12-31", "-"),
            ("2024-01-01", "Ann"), ("2024-01-10", "guest"), ("2024-01-31", "GUEST")]
    return pd.DataFrame([{"Date": d, "Qty": "1", "Price": "10", "Product": "Mug", "Cust": c} for d, c in rows])


def test_each_unanswered_value_is_marked_with_its_lines() -> None:
    found = assemble_metrics(_frame(), MAPPING, now=NOW, unconfirmed_placeholders=["Guest", "-"])
    marked = [(p.value, p.lines, p.lines_current, p.lines_previous) for p in found.customers.unconfirmed_placeholders]
    assert marked == [("Guest", 3, 2, 1), ("-", 1, 0, 1)]
    assert found.customers.unconfirmed_placeholders_reason == (
        'The file suggests "Guest" (3 lines, 2 in 2024-01) and "-" (1 line, 0 in 2024-01) are placeholders for '
        "walk-ins - suggested, not confirmed: their lines stay one customer's each in every customer figure and "
        "cause. Confirm them in Review to count those lines with no customer.")


def test_the_figures_are_unchanged_by_the_mark() -> None:
    # CLAUDE.md 3.3a: Ann and "guest" in January - 2 active customers either way.
    marked = assemble_metrics(_frame(), MAPPING, now=NOW, unconfirmed_placeholders=["Guest"])
    plain = assemble_metrics(_frame(), MAPPING, now=NOW)
    assert marked.core.active_customers_current == plain.core.active_customers_current == 2
    assert marked.customers.segments == plain.customers.segments
    assert (plain.customers.unconfirmed_placeholders, plain.customers.unconfirmed_placeholders_reason) == ([], None)


def test_one_value_reads_in_the_singular() -> None:
    found = assemble_metrics(_frame(), MAPPING, now=NOW, unconfirmed_placeholders=["-"])
    assert found.customers.unconfirmed_placeholders_reason == (
        'The file suggests "-" (1 line, 0 in 2024-01) is a placeholder for walk-ins - suggested, not confirmed: its '
        "lines stay one customer's in every customer figure and cause. Confirm it in Review to count those lines "
        "with no customer.")


def test_a_value_with_no_counted_line_left_is_not_marked() -> None:
    # The plan's cleaning dropped its lines: nothing of it is in any figure.
    found = assemble_metrics(_frame(), MAPPING, now=NOW, unconfirmed_placeholders=["Bob"])
    assert found.customers.unconfirmed_placeholders == []


def test_no_customer_column_marks_nothing() -> None:
    mapping = {k: v for k, v in MAPPING.items() if v != "customer"}
    found = assemble_metrics(_frame(), mapping, now=NOW, unconfirmed_placeholders=["Guest"])
    assert found.customers.unconfirmed_placeholders == []


def test_the_reason_is_paired_with_the_list() -> None:
    found = assemble_metrics(_frame(), MAPPING, now=NOW, unconfirmed_placeholders=["Guest"])
    broken = found.model_dump(mode="json")
    broken["customers"]["unconfirmed_placeholders_reason"] = None
    with pytest.raises(ValueError, match="unconfirmed_placeholders_reason"):
        MetricsContract.model_validate(broken)


def test_stage_2_reads_what_stage_1_recorded(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, CSV)
    execute_run(tmp_path, run_id, _plan(), now=STAGE1_NOW)
    found = analyze_run(tmp_path, run_id, NOW)
    assert [p.value for p in found.customers.unconfirmed_placeholders] == ["Guest", "-"]
