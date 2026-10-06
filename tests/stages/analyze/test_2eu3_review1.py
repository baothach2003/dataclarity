"""2E-u3 review 1 (eleventh run), written before the fixes: the mark on a file
whose prices are written for people (#1), the values kept from stage 4's AI
(#3, CLAUDE.md 3.2), a long list named in part (#5), the customers block run
alone (#10)."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from stages.analyze.assemble import assemble_metrics
from stages.analyze.metrics_customers import customer_metrics_for_run
from stages.ingest.cleaning import execute_run
from tests.stages.ingest.cleaning_fixtures import NOW as STAGE1_NOW
from tests.stages.ingest.cleaning_fixtures import raw_run
from tests.stages.ingest.test_2eu3_stage1 import CSV, _plan

MAPPING = {"Date": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Product": "product_name",
           "Cust": "customer"}
NOW = datetime(2026, 10, 1, tzinfo=UTC)


def test_a_file_priced_for_people_is_marked_too(tmp_path: Path) -> None:
    """#1: "$5.00" read by no rule before the number reading, so no line was
    measured and nothing was marked."""
    run_id = raw_run(tmp_path, CSV.replace(b",5.00,", b",$5.00,"))
    report = execute_run(tmp_path, run_id, _plan(), now=STAGE1_NOW)
    assert report.unconfirmed_placeholders == ["Guest", "-"]


def test_customers_block_alone_carries_the_mark(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, CSV)
    execute_run(tmp_path, run_id, _plan(), now=STAGE1_NOW)
    found = customer_metrics_for_run(tmp_path, run_id, NOW)
    assert [p.value for p in found.unconfirmed_placeholders] == ["Guest", "-"]


def _many(values: int) -> pd.DataFrame:
    rows = [{"Date": "2024-01-05", "Qty": "1", "Price": "10", "Product": "Mug", "Cust": f"Guest {i}"}
            for i in range(values)]
    # Ann on the 1st of December and the 31st of January: January is current.
    rows += [{"Date": d, "Qty": "1", "Price": "10", "Product": "Mug", "Cust": "Ann"} for d in ("2023-12-01",
                                                                                         "2024-01-31")]
    return pd.DataFrame(rows)


def test_a_long_list_names_five_and_counts_the_rest() -> None:
    found = assemble_metrics(_many(8), MAPPING, now=NOW, unconfirmed_placeholders=[f"Guest {i}" for i in range(8)])
    assert len(found.customers.unconfirmed_placeholders) == 8
    reason = found.customers.unconfirmed_placeholders_reason or ""
    assert '"Guest 4" (1 line, 1 in 2024-01) and 3 more (3 lines) are placeholders' in reason
    assert '"Guest 5"' not in reason


def test_stage_4s_ai_is_never_given_the_values() -> None:
    """#3: the customers block went to the AI whole - customer values from
    the file, beyond its bounded sample. Since the report redesign's step 4
    (Thach, Q50 (d), Q53) stage 4 asks no AI at all: no module of it may
    import the AI client, so no value of the file can reach one."""
    import ast

    stage = Path(__file__).resolve().parents[3] / "stages" / "predict"
    imported = {node.module for path in stage.glob("*.py") for node in ast.walk(ast.parse(path.read_text("utf-8")))
                if isinstance(node, ast.ImportFrom) and node.module}
    assert not {module for module in imported if module.startswith("shared.ai_client") or "anthropic" in module}
