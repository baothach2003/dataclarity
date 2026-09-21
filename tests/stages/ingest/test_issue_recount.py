"""Replacing the AI's issue counts with pandas' (stages/ingest/issue_recount.py,
PROJECT_PLAN 1E). Every expected count is worked out by hand from the frame."""

import logging
from typing import Any

import pandas as pd
import pytest

from contracts.profile import ColumnInference, ColumnIssue, DatasetIssue
from stages.ingest.issue_counts import business_key_columns
from stages.ingest.issue_recount import recount_issues


def frame(**columns: list[str | None]) -> pd.DataFrame:
    return pd.DataFrame(columns, dtype="str")


def issue(code: Any, count: int, pct: float | None = None) -> ColumnIssue:
    return ColumnIssue(code=code, count=count, pct=pct, examples=["row 1"])


def column_of(
    name: str, canonical: Any = "ignore", issues: list[ColumnIssue] | None = None
) -> ColumnInference:
    return ColumnInference(
        source_name=name, semantic_type="text", canonical_field=canonical,
        confidence=0.9, issues=issues or [],
    )


def dataset_issue(code: Any, count: int) -> DatasetIssue:
    return DatasetIssue(code=code, count=count, severity="low", detail="from the AI")


# --- the business key (a definition, decided by Thach in 1E) ----------------


def test_the_key_is_sku_date_and_transaction_type() -> None:
    columns = [
        column_of("Item", "sku"), column_of("Day", "transaction_date"),
        column_of("Kind", "transaction_type"), column_of("Qty", "quantity"),
    ]

    assert business_key_columns(columns) == ["Item", "Day", "Kind"]


def test_the_key_falls_back_to_the_product_name_without_a_sku() -> None:
    columns = [column_of("Name", "product_name"), column_of("Day", "transaction_date")]

    assert business_key_columns(columns) == ["Name", "Day"]


def test_a_sku_wins_over_the_product_name() -> None:
    columns = [
        column_of("Name", "product_name"), column_of("Item", "sku"),
        column_of("Day", "transaction_date"),
    ]

    assert business_key_columns(columns) == ["Item", "Day"]


def test_the_transaction_type_is_optional() -> None:
    columns = [column_of("Item", "sku"), column_of("Day", "transaction_date")]

    assert business_key_columns(columns) == ["Item", "Day"]


@pytest.mark.parametrize(
    "columns",
    [
        [column_of("Item", "sku")],                          # no date
        [column_of("Day", "transaction_date")],              # nothing to identify
        [column_of("Kind", "transaction_type")],             # neither
        [column_of("Item", "ignore"), column_of("Day", "ignore")],
        [],
    ],
    ids=["no-date", "no-identity", "type-only", "all-ignored", "no-columns"],
)
def test_without_an_identity_and_a_date_there_is_no_key(columns: list[ColumnInference]) -> None:
    # A file with no key has no such issue: the empty key is a value, not an error.
    assert business_key_columns(columns) == []


# --- column counts ----------------------------------------------------------


def test_a_computed_count_replaces_the_ais_estimate() -> None:
    data = frame(qty=["3", "-1", "5", "-2"])  # two negatives
    columns = [column_of("qty", issues=[issue("negative_values", 7)])]

    result, _, stats = recount_issues(columns, [], data)

    assert result[0].issues[0].count == 2
    assert stats.replaced == 1 and stats.dropped == 0


def test_an_estimate_that_was_right_counts_as_neither_replaced_nor_dropped() -> None:
    data = frame(qty=["3", "-1", "5"])
    columns = [column_of("qty", issues=[issue("negative_values", 1)])]

    result, _, stats = recount_issues(columns, [], data)

    assert result[0].issues[0].count == 1
    assert (stats.replaced, stats.dropped) == (0, 0)


def test_an_issue_pandas_finds_nothing_for_is_dropped() -> None:
    # A "0 negative values" badge on the review screen is noise.
    data = frame(qty=["3", "1", "5"])
    columns = [column_of("qty", issues=[issue("negative_values", 3)])]

    result, _, stats = recount_issues(columns, [], data)

    assert result[0].issues == []
    assert stats.dropped == 1


@pytest.mark.parametrize("code", ["missing_values", "all_null_column"])
def test_a_figure_the_profile_holds_is_left_as_checked(code: str) -> None:
    # 1C already made these equal to profile.json; pct is the profile's too.
    data = frame(qty=["3", None, None])
    columns = [column_of("qty", issues=[issue(code, 2, pct=66.7)])]

    result, _, stats = recount_issues(columns, [], data)

    assert (result[0].issues[0].count, result[0].issues[0].pct) == (2, 66.7)
    assert (stats.replaced, stats.dropped) == (0, 0)


def test_pct_stays_null_when_a_computed_count_is_replaced() -> None:
    # No pct is filled in for computed codes (decided in 1E): a stale one could
    # never contradict the new count.
    data = frame(qty=["-1", "-2", "5"])
    columns = [column_of("qty", issues=[issue("negative_values", 9, pct=None)])]

    result, _, _ = recount_issues(columns, [], data)

    assert result[0].issues[0].pct is None


def test_the_examples_and_other_fields_survive_a_replaced_count() -> None:
    data = frame(qty=["-1", "5"])
    columns = [column_of("qty", issues=[issue("negative_values", 4)])]

    result, _, _ = recount_issues(columns, [], data)

    assert result[0].issues[0].examples == ["row 1"]
    assert result[0].source_name == "qty"


def test_a_code_listed_twice_for_one_column_keeps_the_first() -> None:
    data = frame(qty=["-1", "5"])
    columns = [column_of("qty", issues=[
        issue("negative_values", 4), issue("negative_values", 6)])]

    result, _, stats = recount_issues(columns, [], data)

    assert [(i.code, i.count) for i in result[0].issues] == [("negative_values", 1)]
    assert stats.dropped == 1


@pytest.mark.parametrize("code", ["duplicate_rows", "duplicate_business_key"])
def test_a_dataset_code_under_a_column_is_dropped(code: str) -> None:
    # A count at a level it cannot describe has no source: keeping it would let
    # an AI number through.
    data = frame(qty=["1", "1"])
    columns = [column_of("qty", issues=[issue(code, 2)])]

    result, _, stats = recount_issues(columns, [], data)

    assert result[0].issues == []
    assert stats.dropped == 1


def test_issues_keep_their_order_and_other_columns_are_untouched() -> None:
    data = frame(a=["-1", "x", "-2"], b=["1", "2", "3"])
    columns = [
        column_of("a", issues=[issue("non_numeric_in_numeric", 5), issue("negative_values", 5)]),
        column_of("b"),
    ]

    result, _, _ = recount_issues(columns, [], data)

    assert [(i.code, i.count) for i in result[0].issues] == [
        ("non_numeric_in_numeric", 1), ("negative_values", 2)]
    assert result[1] == columns[1]


def test_the_inputs_are_not_modified() -> None:
    data = frame(qty=["-1", "5"])
    columns = [column_of("qty", issues=[issue("negative_values", 4)])]

    recount_issues(columns, [dataset_issue("duplicate_rows", 1)], data)

    assert columns[0].issues[0].count == 4


# --- dataset counts ---------------------------------------------------------

# Rows 1 and 2 share (A1, 2024-01-05, in); row 3 differs in the date, row 4 in
# the type. Two rows collide.
KEYED = frame(
    sku=["A1", "A1", "A1", "B2"],
    day=["2024-01-05", "2024-01-05", "2024-01-06", "2024-01-05"],
    kind=["in", "in", "in", "out"],
)
KEYED_COLUMNS = [
    column_of("sku", "sku"), column_of("day", "transaction_date"),
    column_of("kind", "transaction_type"),
]


def test_the_business_key_count_is_computed_over_the_key_columns() -> None:
    _, dataset, stats = recount_issues(
        KEYED_COLUMNS, [dataset_issue("duplicate_business_key", 9)], KEYED)

    assert [(i.code, i.count) for i in dataset] == [("duplicate_business_key", 2)]
    assert stats.replaced == 1


def test_the_business_key_description_is_rewritten_from_the_computed_figures() -> None:
    # The AI's prose quoted its own estimate ("12 rows"); next to the computed
    # count that would be two different numbers for one thing.
    stale = DatasetIssue(code="duplicate_business_key", count=12, severity="low",
                         detail="12 rows share a sku and date")

    _, dataset, _ = recount_issues(KEYED_COLUMNS, [stale], KEYED)

    assert dataset[0].count == 2
    assert dataset[0].detail == "2 rows share their sku, day, kind key with another row"
    assert dataset[0].severity == "low"  # the AI's judgement is kept


def test_the_description_is_rewritten_even_when_the_count_was_right() -> None:
    # The count matches, but the sentence around it may quote another figure.
    right = DatasetIssue(code="duplicate_business_key", count=2, severity="low",
                         detail="about 40% of the file")

    _, dataset, stats = recount_issues(KEYED_COLUMNS, [right], KEYED)

    assert "40" not in dataset[0].detail
    assert stats.replaced == 0  # nothing about the count changed


def test_the_duplicate_rows_description_is_rewritten_from_the_profile_count() -> None:
    # Its count is checked equal to profile.json, but the AI's sentence around it
    # can quote another figure ("12 exact duplicate rows" beside a 1), and that
    # sentence goes to the review screen and into the plan prompt.
    stale = DatasetIssue(code="duplicate_rows", count=3, severity="low",
                         detail="12 exact duplicate rows")

    _, dataset, _ = recount_issues(KEYED_COLUMNS, [stale], KEYED)

    assert dataset[0].detail == "3 rows are exact copies of an earlier row"
    assert dataset[0].severity == "low"  # the AI's judgement is kept


def test_a_business_key_issue_is_dropped_when_the_file_has_no_key() -> None:
    columns = [column_of("sku", "sku"), column_of("day"), column_of("kind")]

    _, dataset, stats = recount_issues(
        columns, [dataset_issue("duplicate_business_key", 5)], KEYED)

    assert dataset == [] and stats.dropped == 1


def test_a_business_key_issue_is_dropped_when_no_row_collides() -> None:
    data = frame(sku=["A1", "B2"], day=["2024-01-05", "2024-01-05"], kind=["in", "in"])

    _, dataset, _ = recount_issues(
        KEYED_COLUMNS, [dataset_issue("duplicate_business_key", 1)], data)

    assert dataset == []


def test_the_duplicate_rows_count_is_left_as_1c_checked_it() -> None:
    _, dataset, stats = recount_issues(
        KEYED_COLUMNS, [dataset_issue("duplicate_rows", 3)], KEYED)

    assert [(i.code, i.count) for i in dataset] == [("duplicate_rows", 3)]
    assert (stats.replaced, stats.dropped) == (0, 0)


@pytest.mark.parametrize("code", ["negative_values", "missing_values", "outliers_iqr"])
def test_a_column_code_at_dataset_level_is_dropped(code: str) -> None:
    _, dataset, stats = recount_issues(
        KEYED_COLUMNS, [dataset_issue(code, 4)], KEYED)

    assert dataset == [] and stats.dropped == 1


def test_a_dataset_code_listed_twice_keeps_the_first() -> None:
    _, dataset, _ = recount_issues(
        KEYED_COLUMNS,
        [dataset_issue("duplicate_rows", 3), dataset_issue("duplicate_rows", 3)], KEYED)

    assert len(dataset) == 1


def test_an_empty_frame_and_no_issues_is_a_clean_no_op() -> None:
    result, dataset, stats = recount_issues([column_of("qty")], [], frame(qty=[]))

    assert result == [column_of("qty")] and dataset == []
    assert (stats.replaced, stats.dropped) == (0, 0)


# --- log --------------------------------------------------------------------


def test_the_log_line_holds_counts_and_no_cell_values(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="stages.ingest.issue_recount")
    data = frame(qty=["-1", "SECRET-CELL"])
    columns = [column_of("qty", issues=[
        issue("negative_values", 4), issue("zero_values", 3)])]

    recount_issues(columns, [], data)

    assert "replaced=1" in caplog.text and "dropped=1" in caplog.text
    assert "SECRET-CELL" not in caplog.text


# --- a count of 0 removes the issue whatever its source (1E review) -----------


@pytest.mark.parametrize("code", ["missing_values", "all_null_column"])
def test_a_profile_held_issue_with_a_count_of_zero_is_dropped_too(code: str) -> None:
    # check_answer only made it equal to the profile, and 0 equals 0: without
    # this a "0 missing values" badge survives.
    data = frame(qty=["1", "2"])
    columns = [column_of("qty", issues=[issue(code, 0, pct=0.0)])]

    result, _, stats = recount_issues(columns, [], data)

    assert result[0].issues == [] and stats.dropped == 1


def test_a_duplicate_rows_issue_with_a_count_of_zero_is_dropped_too() -> None:
    _, dataset, stats = recount_issues(
        KEYED_COLUMNS, [dataset_issue("duplicate_rows", 0)], KEYED)

    assert dataset == [] and stats.dropped == 1
