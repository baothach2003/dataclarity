"""Session 2E-t1 (Thach, 2026-09-28): stage 1 writes each line's class into
cleaned.csv, and its contracts go to 4.0 - written before the code.
docs/LINE_TAXONOMY.md section 4: three columns, `line_class`, `class_source`
and `suggested_class` (a missing cell when there is no suggestion - an empty
text would read back as missing and raise a warning on every file); a source
column already named like one of them is kept, renamed `<name>_source`, and
the mapping follows it (Thach's Q24). The line-class enum gains "gift_card"
(closed enums: a major bump, CONTRACTS section 10), and so metrics.json,
whose `non_product` rows carry it, goes to 16.0.
"""

import io
import re
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import (
    CleaningPlanContract,
    CleaningReportContract,
    ColumnAction,
    LineClassAnswer,
    OrderConfirmations,
)
from contracts.metrics import MetricsContract
from contracts.profile import SchemaInferenceContract
from stages.analyze import assemble
from stages.ingest import ai_plan, ai_schema, cleaning
from stages.ingest.cleaning import execute_run
from shared.line_words import CLASS_WORDS
from tests.stages.ingest.cleaning_fixtures import NOW, make_plan, raw_run

PROMPT = Path(__file__).resolve().parents[3] / "prompts" / "schema_inference.md"


def _action(name: str, semantic_type: str, field: str) -> ColumnAction:
    return ColumnAction.model_validate({
        "source_name": name, "semantic_type": semantic_type, "canonical_field": field,
        "action": "flag_only", "params": {"note": ""}, "rationale": "", "alternatives": [],
        "edited_by_user": False})


def _plan(columns: list[tuple[str, str, str]], answers: OrderConfirmations | None = None) -> CleaningPlanContract:
    return CleaningPlanContract(
        schema_version="4.0", generated_at=NOW, source="manual", dataset_actions=[],
        column_actions=[_action(*c) for c in columns], confirmations=answers or OrderConfirmations())


BASE = [("sku", "identifier", "sku"), ("name", "text", "product_name"), ("qty", "numeric_discrete", "quantity"),
        ("price", "numeric_continuous", "unit_price"), ("day", "datetime", "transaction_date")]


def _cleaned(root: Path, run_id: str) -> pd.DataFrame:
    return pd.read_csv(root / run_id / "cleaned.csv", dtype=str)


def test_cleaned_csv_carries_each_lines_class(tmp_path: Path) -> None:
    csv = (b"sku,name,qty,price,day\n"
           b"A1,Mug,3,9.99,2024-01-05\n"
           b"A1,Mug,-1,9.99,2024-01-06\n"
           b"POST,POSTAGE,1,18,2024-01-06\n"
           b"DOT,DOTCOM POSTAGE,1,9,2024-01-07\n"
           b"C3,Cup,2,0,not a date\n")
    run_id = raw_run(tmp_path, csv)
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])

    execute_run(tmp_path, run_id, _plan(BASE, answers), now=NOW)

    got = _cleaned(tmp_path, run_id)
    assert got["line_class"].tolist() == ["sale", "customer_return", "charge", "sale", "no_money"]
    assert got["class_source"].tolist() == ["rule", "rule", "user", "rule", "rule"]
    # DOT is a candidate nobody answered; POST is answered; the rest carry none.
    assert [None if pd.isna(v) else v for v in got["suggested_class"]] == [None, None, None, "charge", None]


def test_a_blank_suggestion_is_a_missing_cell_and_raises_no_warning(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,2024-01-05\n")

    report = execute_run(tmp_path, run_id, _plan(BASE), now=NOW)

    text = (tmp_path / run_id / "cleaned.csv").read_text(encoding="utf-8")
    assert text == ("sku,name,qty,price,day,line_class,class_source,suggested_class\n"
                    "A1,Mug,3,9.99,2024-01-05,sale,rule,\n")
    assert report.warnings == []


def test_columns_out_counts_the_three_new_columns(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,2024-01-05\n")

    report = execute_run(tmp_path, run_id, _plan(BASE), now=NOW)

    assert (report.columns_in, report.columns_out) == (5, 8)


def test_a_source_column_named_like_a_new_one_is_renamed_and_the_mapping_follows(tmp_path: Path) -> None:
    csv = b"sku,name,qty,price,day,line_class\nA1,Mug,3,9.99,2024-01-05,Kitchen\n"
    run_id = raw_run(tmp_path, csv)

    report = execute_run(tmp_path, run_id, _plan(BASE + [("line_class", "categorical_nominal", "category")]),
                         now=NOW)

    got = _cleaned(tmp_path, run_id)
    assert list(got.columns) == ["sku", "name", "qty", "price", "day", "line_class_source",
                                 "line_class", "class_source", "suggested_class"]
    assert got["line_class_source"].tolist() == ["Kitchen"]
    assert got["line_class"].tolist() == ["sale"]
    assert report.column_mapping["line_class_source"] == "category"
    assert "line_class" not in report.column_mapping
    assert [w.code for w in report.warnings] == ["reserved_column_renamed"]
    assert "line_class" in report.warnings[0].detail and "line_class_source" in report.warnings[0].detail
    # The change log names the column as cleaned.csv holds it (review cycle 2
    # #4: the rename happens before the plan runs); plan_final.json keeps the
    # plan as submitted.
    assert [c.column for c in report.changes][-1] == "line_class_source"
    plan_final = CleaningPlanContract.model_validate_json(
        (tmp_path / run_id / "plan_final.json").read_text(encoding="utf-8"))
    assert plan_final.column_actions[-1].source_name == "line_class"


def test_the_rename_is_numbered_when_the_suffixed_name_is_taken(tmp_path: Path) -> None:
    csv = b"sku,name,qty,price,day,suggested_class,suggested_class_source\nA1,Mug,3,9.99,2024-01-05,x,y\n"
    run_id = raw_run(tmp_path, csv)
    extra = [("suggested_class", "text", "ignore"), ("suggested_class_source", "text", "ignore")]

    execute_run(tmp_path, run_id, _plan(BASE + extra), now=NOW)

    got = _cleaned(tmp_path, run_id)
    assert got["suggested_class_source_2"].tolist() == ["x"]
    assert got["suggested_class_source"].tolist() == ["y"]
    assert got["suggested_class"].isna().all()


def test_a_file_without_the_numbers_mapped_gets_no_class_columns(tmp_path: Path) -> None:
    # A file that is not inventory data (SPECS section 10): generic cleaning,
    # nothing mapped, so there is nothing to classify.
    run_id = raw_run(tmp_path, b"a,b\n1,2\n")
    plan = _plan([("a", "numeric_discrete", "ignore"), ("b", "numeric_discrete", "ignore")])

    report = execute_run(tmp_path, run_id, plan, now=NOW, require_required_fields=False)

    assert list(_cleaned(tmp_path, run_id).columns) == ["a", "b"]
    assert report.columns_out == 2


def test_the_classes_read_the_dates_in_the_order_stage_1_applied(tmp_path: Path) -> None:
    # 13/01/2024 proves day first: the SKU's sale is dated, so the name-only
    # line takes the SKU's answer through the vote on dated sale lines (E7).
    csv = (b"sku,name,qty,price,day\n"
           b"POST,Handling,1,4,13/01/2024\n"
           b",Handling,-1,4,14/01/2024\n")
    run_id = raw_run(tmp_path, csv)
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="POST", field="sku", line_class="charge")])

    execute_run(tmp_path, run_id, _plan(BASE, answers), now=NOW)

    assert _cleaned(tmp_path, run_id)["line_class"].tolist() == ["charge", "charge"]


def test_the_vote_reads_the_dates_in_the_answered_order(tmp_path: Path) -> None:
    # Mutation checks M15 and M22: the user answered month first, so
    # "13/01/2024" is a day the order cannot hold - no date - and the SKU's
    # only sale is no dated sale: the name-only line stays a product. Read in
    # no order, pandas would swap it into 13 January and the line would take
    # the SKU's class.
    csv = (b"sku,name,qty,price,day\n"
           b"POST,Handling,1,4,13/01/2024\n"
           b",Handling,-1,4,01/14/2024\n"
           b"A1,Mug,1,4,01/15/2024\n")
    run_id = raw_run(tmp_path, csv)
    answers = OrderConfirmations(dates_day_first=False, line_classes=[
        LineClassAnswer(value="POST", field="sku", line_class="charge")])

    execute_run(tmp_path, run_id, _plan(BASE, answers), now=NOW)

    assert _cleaned(tmp_path, run_id)["line_class"].tolist() == ["charge", "customer_return", "sale"]


def test_the_classes_are_read_from_the_file_as_the_later_stages_read_it(tmp_path: Path) -> None:
    # Mutation check M21: trimmed, " N/A " is the text "N/A" in the run, but
    # cleaned.csv reads it back as missing - so the line has neither SKU nor
    # name, and is pooled, as stages 2 and 3 will see it.
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\n N/A ,,1,5,2024-01-05\nA1,Mug,2,5,2024-01-05\n")
    columns = [("sku", "identifier", "sku"), ("name", "text", "product_name"),
               ("qty", "numeric_discrete", "quantity"), ("price", "numeric_continuous", "unit_price"),
               ("day", "datetime", "transaction_date")]
    plan = _plan(columns)
    plan = CleaningPlanContract.model_validate({**plan.model_dump(mode="json"), "column_actions": [
        {**a.model_dump(mode="json"), "action": "trim_whitespace", "params": {}} if a.source_name == "sku"
        else a.model_dump(mode="json") for a in plan.column_actions]})

    execute_run(tmp_path, run_id, plan, now=NOW)

    assert _cleaned(tmp_path, run_id)["line_class"].tolist() == ["pooled_sale", "sale"]


# --- the contracts ------------------------------------------------------------------------

def test_stage_1_contracts_are_4_0_and_metrics_16_0() -> None:
    assert (ai_schema.SCHEMA_VERSION, ai_plan.SCHEMA_VERSION, cleaning.SCHEMA_VERSION) == ("4.2", "4.2", "4.2")
    assert (SchemaInferenceContract.supported_major, CleaningPlanContract.supported_major,
            CleaningReportContract.supported_major) == (4, 4, 4)
    assert (assemble.SCHEMA_VERSION, MetricsContract.supported_major) == ("16.2", 16)


def test_a_3_x_report_is_refused_with_the_reason() -> None:
    stale = CleaningReportContract(
        schema_version="4.0", generated_at=NOW, rows_in=1, rows_out=1, columns_in=1, columns_out=1,
        changes=[], warnings=[], column_mapping={}).model_dump(mode="json")
    stale["schema_version"] = "3.1"
    with pytest.raises(ValueError, match="without the line taxonomy"):
        CleaningReportContract.model_validate(stale)


def test_gift_card_is_a_line_class_and_an_answer() -> None:
    assert LineClassAnswer(value="gift_0001_10", field="sku", line_class="gift_card").line_class == "gift_card"
    order = [line_class for line_class, _ in CLASS_WORDS]
    assert order.index("discount") < order.index("gift_card") < order.index("charge")


def test_the_schema_prompt_no_longer_calls_a_return_stock_received() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "a purchase or a return" not in text
    assert re.search(r'"in" \(stock received', text)


def test_the_report_reads_back(tmp_path: Path) -> None:
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day\nA1,Mug,3,9.99,2024-01-05\n")
    report = execute_run(tmp_path, run_id, make_plan(), now=NOW)
    on_disk = (tmp_path / run_id / "cleaning_report.json").read_text(encoding="utf-8")
    assert CleaningReportContract.model_validate_json(on_disk) == report
    assert pd.read_csv(io.StringIO((tmp_path / run_id / "cleaned.csv").read_text(encoding="utf-8")),
                       dtype=str)["line_class"].tolist() == ["sale"]
