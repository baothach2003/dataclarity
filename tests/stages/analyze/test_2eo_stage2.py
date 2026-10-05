"""Session 2E-o (Thach, 2026-09-28), stages 1-3, written before the change.

- Q8: Review may override a proven date order. The user's answer wins; the
  cells that contradict it become undated and are counted with their reason.
- Q10: month grain covers files whose every counted line falls on the last
  day of its month (accounting period ends): the last month is compared,
  every month is complete, and a two-month file is not "30 days into" its
  first month.
"""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from contracts.cleaning import OrderConfirmations
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.trust import evaluate_trust
from stages.diagnose.frame import history_window
from stages.ingest.cleaning import execute_run
from tests.stages.diagnose.diagnose_fixtures import MAPPING, NOW, run_data
from tests.stages.ingest.cleaning_fixtures import column_action, make_plan, raw_run


# --- Q8: overriding a proven order --------------------------------------------------------


def _us_export_with_a_typo() -> bytes:
    """A US export, 1-12 September 2026 month first, and one typo
    "13/09/2026" that proves day first."""
    lines = ["sku,name,qty,price,day"]
    lines += [f"A{n},Mug,1,10.00,09/{n:02d}/2026" for n in range(1, 13)]
    lines.append("B1,Cup,1,10.00,13/09/2026")
    return ("\n".join(lines) + "\n").encode()


def test_the_answer_wins_over_a_proof(tmp_path: Path) -> None:
    # Stage 1 already let an answer win (2E-j); this pins the rule Review's
    # override (the frontend's tests) relies on.
    run_id = raw_run(tmp_path, _us_export_with_a_typo())
    actions = [column_action("sku", "trim_whitespace"), column_action("name", "trim_whitespace"),
               column_action("qty", "flag_only"), column_action("price", "flag_only"),
               column_action("day", "flag_only")]
    plan = make_plan(actions).model_copy(update={"confirmations": OrderConfirmations(dates_day_first=False)})

    report = execute_run(tmp_path, run_id, plan, now=NOW)

    assert report.date_order == "month_first"


def test_the_cells_against_the_answer_are_undated_and_counted() -> None:
    rows = [{"Date": f"09/{n:02d}/2026", "Qty": "1", "Price": "10", "Product": "Mug", "Cust": "A"}
            for n in range(1, 13)]
    rows.append({"Date": "13/09/2026", "Qty": "1", "Price": "10", "Product": "Cup", "Cust": "B"})

    metrics = assemble_metrics(pd.DataFrame(rows), MAPPING, NOW, OrderConfirmations(dates_day_first=False))

    assert [(m.period, m.revenue) for m in metrics.core.revenue_by_month] == [("2026-09", 120.0)]
    assert metrics.core.undated_lines == 1
    assert "a day and month the file's date order cannot hold" in str(metrics.core.undated_lines_reason)


# --- Q10: month-end grain -----------------------------------------------------------------


def month_end_rows(months: int = 24) -> list[dict]:
    """`months` months from 2024-01, each line on the month's LAST day: five
    products P0-P4 priced 10-14, three lines of 10 units a month (1,800); in
    the last month P4 is gone (1,380)."""
    rows = []
    for index in range(months):
        year, month = 2024 + index // 12, index % 12 + 1
        last = date(year + month // 12, month % 12 + 1, 1) - timedelta(days=1)
        for product in range(5):
            if index == months - 1 and product == 4:
                continue
            for line in range(3):
                rows.append({"Date": last.isoformat(), "Qty": "10", "Price": str(10.0 + product),
                             "Product": f"P{product}", "Cust": f"C{(index + line + product) % 10}"})
    return rows


def test_a_month_end_file_is_month_grain_and_compares_its_last_month() -> None:
    metrics = assemble_metrics(pd.DataFrame(month_end_rows()), MAPPING, NOW, None)

    assert metrics.period.month_grain is True
    assert (metrics.period.current, metrics.period.previous) == ("2025-12", "2025-11")
    assert (metrics.core.revenue_current, metrics.core.revenue_previous) == (1380.0, 1800.0)


def test_every_month_of_a_month_end_file_is_complete() -> None:
    data = run_data(month_end_rows())

    assert data.complete_months[0] == "2024-01"
    assert len(data.complete_months) == 24


def test_a_two_month_month_end_file_is_not_thirty_days_into_its_first_month() -> None:
    """Its first sale is on 31 January: by days, "30 days into 2024-01", so
    the comparison was blocked; by months, January holds a sale."""
    data = run_data(month_end_rows(2))

    assert data.metrics.period.previous_complete is True
    assert evaluate_trust(data, history_window(data)).verdict != "blocked"


def test_complete_months_start_at_the_first_counted_month() -> None:
    """A month-grain file with an uncounted row dated earlier: the empty
    month before it is no history (review cycle 1 #9)."""
    rows = month_end_rows()
    rows.append({"Date": "2023-11-15", "Qty": "1", "Price": "", "Product": "P0", "Cust": "C0"})

    data = run_data(rows)

    assert data.metrics.period.month_grain is True
    assert data.complete_months[0] == "2024-01"


def test_metrics_json_is_15_and_diagnosis_json_16() -> None:
    """Rules 5 and 6 ranked together can name another cause on the same data
    (Kaggle 2024-12: T2 -> B1) and a month-end file compares another month:
    a change of meaning, a major bump (CONTRACTS section 10)."""
    from contracts.diagnosis import DiagnosisContract
    from contracts.metrics import MetricsContract
    from stages.analyze.assemble import SCHEMA_VERSION

    assert (SCHEMA_VERSION, MetricsContract.supported_major, DiagnosisContract.supported_major) == ("16.2", 16, 18)  # 16.2 in the report redesign's step 1 (additive); 16.1 in 2E-u6 (additive); metrics 16.0 since 2E-t1, diagnosis 18.0 since 3E1b (17.0 since 2E-t2)


def test_complete_months_end_at_the_last_counted_month() -> None:
    """A later uncounted row added empty months after the current one
    (review cycle 3 #7)."""
    rows = month_end_rows(18)
    rows.append({"Date": "2026-06-15", "Qty": "1", "Price": "", "Product": "P0", "Cust": "C0"})

    data = run_data(rows)

    assert data.complete_months[-1] == "2025-06"
    assert len(data.complete_months) == 18
