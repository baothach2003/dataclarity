"""The written schema_inference.json carries pandas' counts, not the AI's
estimates (PROJECT_PLAN 1D handover, decided by Thach in 1E)."""

from pathlib import Path

from tests.ai_fakes import FakeMessages
from tests.stages.ingest.schema_answers import (
    CANONICAL,
    COLUMNS,
    answer,
    column,
    profiled_run,
    run,
)

# schema_answers.CSV: qty is 3, -1, 3, 5 - one negative, no zero.
QTY = COLUMNS.index("qty")


def with_qty_issues(*issues: dict[str, object]) -> FakeMessages:
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[QTY]["issues"] = list(issues)
    return FakeMessages(answer(columns))


def qty_issue(code: str, count: int) -> dict[str, object]:
    return {"code": code, "count": count, "pct": None, "examples": ["row 2"]}


def test_an_estimated_count_is_replaced_without_a_retry(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)
    messages = with_qty_issues(qty_issue("negative_values", 4))

    returned = run(tmp_path, run_id, messages)

    assert [(i.code, i.count) for i in returned.columns[QTY].issues] == [("negative_values", 1)]
    # The run's single retry is untouched: a difference is not an error.
    assert len(messages.calls) == 1


def test_an_issue_with_nothing_behind_it_is_left_out(tmp_path: Path) -> None:
    run_id = profiled_run(tmp_path)

    returned = run(tmp_path, run_id, with_qty_issues(qty_issue("zero_values", 2)))

    assert returned.columns[QTY].issues == []


def test_a_profile_figure_is_kept(tmp_path: Path) -> None:
    # price has one gap in four rows (25.0 %), exactly as profile.json says.
    run_id = profiled_run(tmp_path)
    columns = [column(n, CANONICAL[n]) for n in COLUMNS]
    columns[COLUMNS.index("price")]["issues"] = [
        {"code": "missing_values", "count": 1, "pct": 25.0, "examples": ["row 4"]}]

    returned = run(tmp_path, run_id, FakeMessages(answer(columns)))

    kept = returned.columns[COLUMNS.index("price")].issues[0]
    assert (kept.code, kept.count, kept.pct) == ("missing_values", 1, 25.0)


def test_the_business_key_count_comes_from_the_mapped_columns(tmp_path: Path) -> None:
    # Rows 1 and 2 are identical, so profile.json counts one duplicate row; they
    # also share (A1, 2024-01-05, in), so two rows collide on the business key.
    csv = b"sku,day,kind\nA1,2024-01-05,in\nA1,2024-01-05,in\nB2,2024-01-05,in\n"
    run_id = profiled_run(tmp_path, csv)
    columns = [
        column("sku", "sku"),
        column("day", "transaction_date", semantic_type="datetime"),
        column("kind", "transaction_type"),
    ]
    dataset_issues = [
        {"code": "duplicate_rows", "count": 1, "severity": "low", "detail": "row 2 repeats row 1"},
        {"code": "duplicate_business_key", "count": 3, "severity": "medium",
         "detail": "estimated by the AI"},
    ]

    returned = run(tmp_path, run_id, FakeMessages(answer(columns, dataset_issues=dataset_issues)))

    assert [(i.code, i.count) for i in returned.dataset_issues] == [
        ("duplicate_rows", 1), ("duplicate_business_key", 2)]
