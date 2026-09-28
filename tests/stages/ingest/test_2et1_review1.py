"""Session 2E-t1, doubt-review cycle 1 - the gaps its findings showed, each
pinned: the rename only where the classes are written, with a warning that
says what each column holds and the flag columns following the data; the
classes of an answer a name-only line inherits; an empty frame; the 3.x stage
1 files refused with the reason; a gift-card answer through stage 3."""

from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

from contracts.cleaning import (
    CleaningPlanContract,
    ColumnAction,
    LineClassAnswer,
    OrderConfirmations,
)
from contracts.profile import SchemaInferenceContract
from stages.analyze.assemble import assemble_metrics
from stages.diagnose.inputs import build_run_data
from stages.diagnose.lever import month_revenue
from stages.diagnose.localization import compute_localization
from stages.ingest.cleaning import execute_run
from shared.line_taxonomy import classify_lines
from tests.stages.ingest.cleaning_fixtures import NOW, raw_run

BASE = [("sku", "identifier", "sku"), ("name", "text", "product_name"), ("qty", "numeric_discrete", "quantity"),
        ("price", "numeric_continuous", "unit_price"), ("day", "datetime", "transaction_date")]


def _action(name: str, semantic_type: str, field: str, action: str = "flag_only", params: dict | None = None
            ) -> ColumnAction:
    return ColumnAction.model_validate({
        "source_name": name, "semantic_type": semantic_type, "canonical_field": field, "action": action,
        "params": {"note": ""} if params is None else params, "rationale": "", "alternatives": [],
        "edited_by_user": False})


def _plan(actions: list[ColumnAction], answers: OrderConfirmations | None = None) -> CleaningPlanContract:
    return CleaningPlanContract(schema_version="4.0", generated_at=NOW, source="manual", dataset_actions=[],
                                column_actions=actions, confirmations=answers or OrderConfirmations())


def _header(root: Path, run_id: str) -> list[str]:
    return list(pd.read_csv(root / run_id / "cleaned.csv", dtype=str).columns)


# --- the rename ---------------------------------------------------------------------------

def test_a_file_that_is_not_classed_keeps_its_names_and_gets_no_warning(tmp_path: Path) -> None:
    # Generic cleaning: nothing mapped, no class column written - so nothing
    # is renamed and no warning speaks of a column that is not there (#3).
    run_id = raw_run(tmp_path, b"a,line_class\n1,x\n")
    plan = _plan([_action("a", "numeric_discrete", "ignore"), _action("line_class", "text", "ignore")])

    report = execute_run(tmp_path, run_id, plan, now=NOW, require_required_fields=False)

    assert _header(tmp_path, run_id) == ["a", "line_class"]
    assert report.warnings == []


def test_each_rename_says_what_the_column_it_makes_way_for_holds(tmp_path: Path) -> None:
    csv = b"sku,name,qty,price,day,line_class,class_source,suggested_class\nA1,Mug,3,9.99,2024-01-05,x,y,z\n"
    run_id = raw_run(tmp_path, csv)
    extra = [_action(n, "text", "ignore") for n in ("line_class", "class_source", "suggested_class")]

    report = execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    details = [w.detail for w in report.warnings]
    assert details == [
        "the source column 'line_class' is written as 'line_class_source': cleaned.csv's 'line_class' "
        "holds each line's class",
        "the source column 'class_source' is written as 'class_source_source': cleaned.csv's "
        "'class_source' holds whether the user's answer or a rule decided each line's class",
        "the source column 'suggested_class' is written as 'suggested_class_source': cleaned.csv's "
        "'suggested_class' holds the class suggested for each line's key and not confirmed"]


def test_a_flag_on_a_renamed_column_follows_the_data(tmp_path: Path) -> None:
    # #6: the negative-number flag of the source column "line_class" names
    # the column its data now sits in.
    csv = b"sku,name,qty,price,day,line_class\nA1,Mug,3,9.99,2024-01-05,-4\n"
    run_id = raw_run(tmp_path, csv)
    extra = [_action("line_class", "numeric_discrete", "ignore", "fix_negative", {"strategy": "flag"})]

    execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    header = _header(tmp_path, run_id)
    assert "__flag_negative__line_class_source" in header
    assert "__flag_negative__line_class" not in header


# --- the classifier ---------------------------------------------------------------------------

MAPPING = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Sku": "sku",
           "Name": "product_name"}


def test_a_name_only_line_inherits_a_gift_card_answer_and_the_users_source() -> None:
    df = pd.DataFrame({"Day": "2026-08-03", "Sku": ["GV10", None, None], "Name": ["Voucher 10"] * 3,
                       "Qty": ["1", "1", "-1"], "Price": ["10", "10", "10"]})
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="GV10", field="sku", line_class="gift_card")])

    got = classify_lines(df, MAPPING, answers)

    assert got["line_class"].tolist() == ["gift_card_sale", "gift_card_sale", "gift_card_redemption"]
    assert got["class_source"].tolist() == ["user", "user", "user"]
    assert got["suggested_class"].isna().all()


def test_an_empty_frame_gets_no_line() -> None:
    df = pd.DataFrame({c: pd.Series(dtype=object) for c in MAPPING})
    got = classify_lines(df, MAPPING, OrderConfirmations())
    assert list(got.columns) == ["line_class", "class_source", "suggested_class"]
    assert got.empty


# --- the 3.x stage 1 files ----------------------------------------------------------------------

def test_a_3_x_plan_and_schema_are_refused_with_the_reason() -> None:
    plan = {"schema_version": "3.1", "generated_at": NOW.isoformat(), "source": "manual",
            "dataset_actions": [], "column_actions": []}
    schema = {"schema_version": "3.1", "generated_at": NOW.isoformat(), "model_used": "m",
              "domain_confidence": 0.9, "domain_reasoning": "r", "dataset_issues": [], "columns": []}
    for model, payload in ((CleaningPlanContract, plan), (SchemaInferenceContract, schema)):
        with pytest.raises(ValueError, match="without the line taxonomy"):
            model.model_validate(payload)


# --- a gift card through stage 3 ----------------------------------------------------------------

def test_a_gift_card_answer_is_no_product_member_and_no_money_in_stage_3() -> None:
    # The same enum reaches stage 3 in the same session (CONTRACTS 10): a
    # confirmed voucher is out of revenue, so no product member and no
    # "(not a product)" money - as a fee.
    rows = []
    for month in ("2026-06", "2026-07", "2026-08"):
        for day in range(1, 29):
            rows.append((f"{month}-{day:02d}", "A1", "Mug", "2", "5"))
        rows.append((f"{month}-10", "GV10", "Gift voucher 10", "1", "10"))
    rows.append(("2026-09-02", "A1", "Mug", "1", "5"))
    df = pd.DataFrame(rows, columns=["Day", "Sku", "Name", "Qty", "Price"])
    answers = OrderConfirmations(line_classes=[LineClassAnswer(value="GV10", field="sku", line_class="gift_card")])
    metrics = assemble_metrics(df, MAPPING, datetime(2026, 9, 26, tzinfo=UTC), answers)
    data = build_run_data(df, MAPPING, metrics, answers)
    period = data.metrics.period

    loc = compute_localization(data, month_revenue(data, period.current) - month_revenue(data, period.previous))

    assert metrics.core.revenue_current == 28 * 10.0
    products = next(d for d in loc.dimensions if d.name == "product")
    assert {m.name for m in products.members} <= {"Mug"}
    assert not any(m.is_not_a_product for m in products.members)


# --- review cycle 2: the rename happens before the plan runs --------------------------------

def test_a_flag_never_lands_on_a_name_the_file_already_has(tmp_path: Path) -> None:
    # #2: a file that already holds the flag name the renamed column's flag
    # would take - the run's flag is numbered, never a duplicate header.
    csv = (b"sku,name,qty,price,day,suggested_class,__flag_negative__suggested_class_source\n"
           b"A1,Mug,3,9.99,2024-01-05,-4,x\n")
    run_id = raw_run(tmp_path, csv)
    extra = [_action("suggested_class", "numeric_discrete", "ignore", "fix_negative", {"strategy": "flag"}),
             _action("__flag_negative__suggested_class_source", "text", "ignore")]

    execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    header = (tmp_path / run_id / "cleaned.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert len(header) == len(set(header))
    assert "suggested_class_source" in header and "suggested_class" in header


def test_a_source_column_that_looks_like_a_flag_keeps_its_name(tmp_path: Path) -> None:
    # #3: only the three names are renamed; the run's own flag follows its data.
    csv = (b"sku,name,qty,price,day,line_class,__flag_negative__line_class\n"
           b"A1,Mug,3,9.99,2024-01-05,-4,x\n")
    run_id = raw_run(tmp_path, csv)
    extra = [_action("line_class", "numeric_discrete", "ignore", "fix_negative", {"strategy": "flag"}),
             _action("__flag_negative__line_class", "text", "ignore")]

    report = execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    header = _header(tmp_path, run_id)
    assert "__flag_negative__line_class" in header  # the source's own column, as written
    assert "__flag_negative__line_class_source" in header  # the run's flag, on the renamed data
    assert [w.code for w in report.warnings] == ["reserved_column_renamed"]


def test_the_change_log_names_columns_that_are_in_cleaned_csv(tmp_path: Path) -> None:
    # #4: the detail names the flag column as it is written.
    csv = b"sku,name,qty,price,day,line_class\nA1,Mug,3,9.99,2024-01-05,-4\n"
    run_id = raw_run(tmp_path, csv)
    extra = [_action("line_class", "numeric_discrete", "ignore", "fix_negative", {"strategy": "flag"})]

    report = execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    header = _header(tmp_path, run_id)
    flagged = next(c for c in report.changes if c.action == "fix_negative")
    assert flagged.column in header
    assert "__flag_negative__line_class_source" in flagged.detail


# --- review cycle 3 ------------------------------------------------------------------------------

def test_a_dataset_actions_keys_follow_the_rename(tmp_path: Path) -> None:
    # #3 (mutation M1): flag_duplicate_keys over a column named "line_class"
    # runs on its renamed data.
    from tests.stages.ingest.cleaning_fixtures import dataset_action

    csv = (b"sku,name,qty,price,day,line_class\n"
           b"A1,Mug,3,9.99,2024-01-05,K1\nA1,Mug,1,9.99,2024-01-06,K1\n")
    run_id = raw_run(tmp_path, csv)
    plan = CleaningPlanContract(
        schema_version="4.0", generated_at=NOW, source="manual",
        dataset_actions=[dataset_action("flag_duplicate_keys", {"keys": ["line_class", "sku"]})],
        column_actions=[_action(*c) for c in BASE] + [_action("line_class", "text", "ignore")])

    report = execute_run(tmp_path, run_id, plan, now=NOW)

    flagged = next(c for c in report.changes if c.action == "flag_duplicate_keys")
    assert flagged.params["keys"] == ["line_class_source", "sku"]
    assert "__flag_duplicate_key" in _header(tmp_path, run_id)


def test_a_reserved_column_the_plan_drops_is_not_renamed(tmp_path: Path) -> None:
    # #2 and #5 (mutation M2): nothing of it is written, so no rename, no
    # warning, no mapping entry.
    csv = b"sku,name,qty,price,day,line_class\nA1,Mug,3,9.99,2024-01-05,Kitchen\n"
    run_id = raw_run(tmp_path, csv)
    extra = [_action("line_class", "categorical_nominal", "category", "drop_column", {})]

    report = execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    assert _header(tmp_path, run_id) == ["sku", "name", "qty", "price", "day", "line_class", "class_source",
                                         "suggested_class"]
    assert report.warnings == []
    assert "category" not in report.column_mapping.values()
    assert [c.column for c in report.changes if c.action == "drop_column"] == ["line_class"]


def test_a_failure_names_the_column_as_the_user_wrote_it(tmp_path: Path, monkeypatch) -> None:
    # #7: the run renames the column before the plan; its failure says the
    # name the user knows.
    from stages.ingest import transforms
    from stages.ingest.cleaning import CleaningError

    def failing(action, frame, column, params):
        if column == "line_class_source":
            raise ValueError(f"cannot read {column!r}")
        return real(action, frame, column, params)

    real = transforms.apply_action
    monkeypatch.setattr(transforms, "apply_action", failing)
    run_id = raw_run(tmp_path, b"sku,name,qty,price,day,line_class\nA1,Mug,3,9.99,2024-01-05,x\n")
    extra = [_action("line_class", "text", "ignore")]

    with pytest.raises(CleaningError) as caught:
        execute_run(tmp_path, run_id, _plan([_action(*c) for c in BASE] + extra), now=NOW)

    assert caught.value.column == "line_class"
    assert "'line_class_source'" not in str(caught.value)


def test_a_name_keyed_candidate_is_suggested_for_its_lines() -> None:
    # #4 (mutation M3): with no SKU column the key is the name.
    mapping = {"Day": "transaction_date", "Qty": "quantity", "Price": "unit_price", "Name": "product_name"}
    df = pd.DataFrame({"Day": "2026-08-03", "Name": ["Postage", "Postage", "Mug"], "Qty": "1",
                       "Price": ["4", "4", "5"]})

    got = classify_lines(df, mapping, OrderConfirmations())

    assert [None if pd.isna(v) else v for v in got["suggested_class"]] == ["charge", "charge", None]


def test_answer_keys_reads_every_value_as_answer_key_does() -> None:
    from shared.line_classes import answer_key, answer_keys

    values = ["POST", " post ", "Maßband", "", "​", "Postage", "A1", "DOTCOM POSTAGE"]
    fields = ["sku", "sku", "product_name", "sku", "product_name", "product_name", "sku", "product_name"]
    assert answer_keys(values, fields) == [
        answer_key(LineClassAnswer(value=v, field=f, line_class="product")) for v, f in zip(values, fields, strict=True)]
