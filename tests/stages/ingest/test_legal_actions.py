"""The legal action lists the plan prompt shows the AI and the retry message
repeats (stages/ingest/transform_catalog.py). Written out by hand from
docs/AI_PIPELINE.md section 6, in the catalog's own order."""

from typing import get_args

import pytest

from contracts.cleaning import TransformAction
from contracts.profile import CanonicalField, SemanticType
from stages.ingest.transform_catalog import (
    is_legal,
    legal_column_actions,
    legal_dataset_actions,
    scope_of,
)


@pytest.mark.parametrize(
    ("semantic_type", "canonical_field", "expected"),
    [
        # product_name is required: no imputation. Text is trimmed and re-cased,
        # not merged (standardize_categories is categorical only).
        ("text", "product_name",
         ["drop_rows_missing", "drop_column", "cast_type", "trim_whitespace",
          "normalize_case", "flag_only"]),
        ("numeric_continuous", "unit_price",
         ["impute_median", "impute_mean", "drop_rows_missing", "drop_column", "cast_type",
          "fix_negative", "clip_outliers_iqr", "flag_only"]),
        # quantity is required: the same numeric list without the two imputations.
        ("numeric_discrete", "quantity",
         ["drop_rows_missing", "drop_column", "cast_type", "fix_negative",
          "clip_outliers_iqr", "flag_only"]),
        # transaction_date is required but must stay parseable.
        ("datetime", "transaction_date",
         ["drop_rows_missing", "drop_column", "parse_datetime", "cast_type", "flag_only"]),
        ("categorical_nominal", "category",
         ["impute_mode", "impute_constant", "drop_rows_missing", "drop_column", "cast_type",
          "trim_whitespace", "normalize_case", "standardize_categories", "flag_only"]),
        # An identifier is never imputed but may be trimmed and re-cased (1D).
        ("identifier", "sku",
         ["drop_rows_missing", "drop_column", "cast_type", "trim_whitespace",
          "normalize_case", "flag_only"]),
        ("boolean", "ignore",
         ["impute_mode", "impute_constant", "drop_rows_missing", "drop_column", "cast_type",
          "flag_only"]),
    ],
)
def test_the_legal_column_actions_for_a_column(
    semantic_type: SemanticType, canonical_field: CanonicalField, expected: list[str]
) -> None:
    assert legal_column_actions(semantic_type, canonical_field) == expected


def test_the_dataset_actions_are_the_two_that_take_no_column() -> None:
    assert legal_dataset_actions() == ["remove_exact_duplicates", "flag_duplicate_keys"]


def test_no_dataset_action_is_ever_offered_for_a_column() -> None:
    assert not set(legal_dataset_actions()) & set(legal_column_actions("text", "note"))


def test_every_listed_action_passes_the_legality_check_itself() -> None:
    # The list and the validator must never disagree, or the AI is told an
    # action is fine and then rejected for using it.
    for action in get_args(TransformAction):
        listed = action in legal_column_actions("numeric_discrete", "quantity")
        assert listed == (scope_of(action) == "column"
                          and is_legal(action, "numeric_discrete", "quantity"))
