"""The legality matrix and the fixed execution order (docs/AI_PIPELINE.md
section 6), walked pair by pair as section 10 requires.

The expected matrix below is written out from the documentation by hand, not
derived from the module's own constants: a test that reused them would agree
with any mistake they contained.
"""

import pytest

from contracts.cleaning import TransformAction
from contracts.profile import CanonicalField, SemanticType
from stages.ingest.transform_catalog import (
    ALL_ACTIONS,
    ALL_SEMANTIC_TYPES,
    DATASET_ACTIONS,
    EXECUTION_ORDER,
    IMPUTATION_ACTIONS,
    REQUIRED_CANONICAL_FIELDS,
    execution_rank,
    illegality_reason,
    is_legal,
    scope_of,
)

NUMERIC = ("numeric_continuous", "numeric_discrete")
CATEGORICAL = ("categorical_nominal", "categorical_ordinal")
TEXTUAL = (*CATEGORICAL, "text")
STRING_SHAPE = (*TEXTUAL, "identifier")
EVERY_TYPE: tuple[SemanticType, ...] = (
    "numeric_continuous", "numeric_discrete", "categorical_nominal", "categorical_ordinal",
    "datetime", "identifier", "boolean", "text",
)

# The catalog table's "Applies to" column, spelled out. Dataset actions take no
# column at all and are therefore not in this table.
LEGAL: dict[TransformAction, tuple[SemanticType, ...]] = {
    "impute_median": NUMERIC,                       # numeric only; never identifier
    "impute_mean": NUMERIC,
    "impute_mode": (*TEXTUAL, "boolean"),           # categorical / text / boolean
    "impute_constant": (*TEXTUAL, "boolean"),       # not "any": see the matrix
    "drop_rows_missing": EVERY_TYPE,                # "any"
    "drop_column": EVERY_TYPE,
    "parse_datetime": ("datetime",),                # datetime only
    "cast_type": EVERY_TYPE,
    "trim_whitespace": STRING_SHAPE,                # text / categorical / identifier
    "normalize_case": STRING_SHAPE,
    "standardize_categories": CATEGORICAL,          # categorical
    "fix_negative": NUMERIC,
    "clip_outliers_iqr": NUMERIC,
    "flag_only": EVERY_TYPE,
}

PAIRS = [(action, kind) for action in sorted(LEGAL) for kind in EVERY_TYPE]


def test_the_expected_matrix_covers_every_column_action() -> None:
    assert set(LEGAL) | DATASET_ACTIONS == ALL_ACTIONS
    assert set(EVERY_TYPE) == ALL_SEMANTIC_TYPES


# --- every (semantic_type, action) pair -------------------------------------


@pytest.mark.parametrize(("action", "semantic_type"), PAIRS)
def test_legality_of_every_pair(action: TransformAction, semantic_type: SemanticType) -> None:
    assert is_legal(action, semantic_type) is (semantic_type in LEGAL[action])


@pytest.mark.parametrize(("action", "semantic_type"), PAIRS)
def test_an_illegal_pair_says_why(action: TransformAction, semantic_type: SemanticType) -> None:
    reason = illegality_reason(action, semantic_type)

    if semantic_type in LEGAL[action]:
        assert reason is None
    else:
        assert reason is not None and semantic_type in reason


def test_imputing_an_identifier_is_illegal_for_every_imputation() -> None:
    # Called out in the catalog: a made-up SKU would join rows that are not
    # the same product.
    assert [a for a in sorted(IMPUTATION_ACTIONS) if is_legal(a, "identifier")] == []


def test_an_identifier_can_still_be_trimmed_and_re_cased() -> None:
    # Decided by Thach in 1D: a padded or mis-cased SKU is ordinary dirt, and
    # standardizing how a value is written invents nothing - unlike imputation,
    # which stays illegal above.
    assert is_legal("trim_whitespace", "identifier")
    assert is_legal("normalize_case", "identifier")


@pytest.mark.parametrize("action", ["standardize_categories", "impute_mode", "impute_constant"])
def test_the_identifier_exception_stops_at_the_two_string_shape_actions(
    action: TransformAction,
) -> None:
    # Only trim_whitespace and normalize_case were widened; merging labels
    # would still collapse two ids into one.
    assert is_legal(action, "identifier") is False


# --- the required-canonical-field exception ---------------------------------


@pytest.mark.parametrize("field", sorted(REQUIRED_CANONICAL_FIELDS))
@pytest.mark.parametrize("action", sorted(IMPUTATION_ACTIONS))
def test_imputation_is_illegal_on_a_required_field(
    action: TransformAction, field: CanonicalField
) -> None:
    # Checked on a column the action would otherwise be legal for, so the
    # refusal comes from the field and not from the semantic type.
    legal_type = LEGAL[action][0]

    reason = illegality_reason(action, legal_type, field)

    assert reason is not None and "required field" in reason
    assert "drop_rows_missing or flag_only" in reason


@pytest.mark.parametrize("field", sorted(REQUIRED_CANONICAL_FIELDS))
def test_a_required_field_may_still_be_dropped_or_flagged(field: CanonicalField) -> None:
    assert is_legal("drop_rows_missing", "text", field)
    assert is_legal("flag_only", "text", field)


@pytest.mark.parametrize(("action", "semantic_type"), PAIRS)
def test_a_required_field_refuses_imputation_and_nothing_else(
    action: TransformAction, semantic_type: SemanticType
) -> None:
    # The whole matrix, walked against a required field. The rule subtracts the
    # four imputations from what the semantic type allows and nothing more:
    # reading "only drop_rows_missing or flag_only" as a whitelist would leave
    # transaction_date unparseable (1D, decided by Thach).
    allowed_by_type = semantic_type in LEGAL[action]

    assert is_legal(action, semantic_type, "transaction_date") is (
        allowed_by_type and action not in IMPUTATION_ACTIONS
    )


def test_a_required_field_keeps_every_other_legal_action() -> None:
    # The exception is about inventing values, not about cleaning: a date
    # column still has to be parsed, and a product name still has to be trimmed.
    assert is_legal("parse_datetime", "datetime", "transaction_date")
    assert is_legal("trim_whitespace", "text", "product_name")
    assert is_legal("clip_outliers_iqr", "numeric_discrete", "quantity")


@pytest.mark.parametrize("action", sorted(IMPUTATION_ACTIONS))
def test_imputation_stays_legal_on_a_field_that_is_not_required(
    action: TransformAction,
) -> None:
    assert is_legal(action, LEGAL[action][0], "note")


# --- scope ------------------------------------------------------------------


@pytest.mark.parametrize("action", sorted(DATASET_ACTIONS))
def test_a_dataset_action_is_legal_without_a_column(action: TransformAction) -> None:
    assert is_legal(action) is True


@pytest.mark.parametrize("action", sorted(DATASET_ACTIONS))
@pytest.mark.parametrize("semantic_type", EVERY_TYPE)
def test_a_dataset_action_is_illegal_on_a_column(
    action: TransformAction, semantic_type: SemanticType
) -> None:
    assert illegality_reason(action, semantic_type) == (
        f"{action} applies to the dataset, not to a column"
    )


@pytest.mark.parametrize("action", sorted(LEGAL))
def test_a_column_action_is_illegal_without_a_column(action: TransformAction) -> None:
    assert illegality_reason(action) == f"{action} applies to a column, not to the dataset"


def test_scope_of_every_action() -> None:
    assert {a for a in ALL_ACTIONS if scope_of(a) == "dataset"} == DATASET_ACTIONS


def test_an_action_outside_the_catalog_is_never_legal() -> None:
    assert is_legal("delete_everything", "text") is False  # type: ignore[arg-type]  # the whitelist is what this checks


# --- the fixed execution order ----------------------------------------------


def test_the_order_holds_every_action_exactly_once() -> None:
    listed = [action for group in EXECUTION_ORDER for action in group]

    assert sorted(listed) == sorted(ALL_ACTIONS)
    assert len(listed) == len(set(listed))


def test_the_order_is_the_documented_one() -> None:
    # AI_PIPELINE section 6: drop_column -> remove_exact_duplicates ->
    # trim_whitespace -> normalize_case -> parse_datetime / cast_type ->
    # missing-value handling -> standardize_categories -> fix_negative /
    # clip_outliers_iqr -> flags.
    assert [sorted(group) for group in EXECUTION_ORDER] == [
        ["drop_column"],
        ["remove_exact_duplicates"],
        ["trim_whitespace"],
        ["normalize_case"],
        ["cast_type", "parse_datetime"],
        ["drop_rows_missing", "impute_constant", "impute_mean", "impute_median", "impute_mode"],
        ["standardize_categories"],
        ["clip_outliers_iqr", "fix_negative"],
        ["flag_duplicate_keys", "flag_only"],
    ]


@pytest.mark.parametrize(
    ("earlier", "later"),
    [
        ("drop_column", "remove_exact_duplicates"),
        ("remove_exact_duplicates", "trim_whitespace"),
        # Trimming before merging labels, or " Cafe" never joins "Cafe".
        ("trim_whitespace", "normalize_case"),
        ("normalize_case", "parse_datetime"),
        ("cast_type", "impute_median"),
        ("impute_median", "standardize_categories"),
        ("standardize_categories", "fix_negative"),
        ("clip_outliers_iqr", "flag_only"),
    ],
)
def test_the_documented_pairs_run_in_order(
    earlier: TransformAction, later: TransformAction
) -> None:
    assert execution_rank(earlier) < execution_rank(later)


def test_sorting_a_plan_keeps_the_plan_order_inside_a_group() -> None:
    plan: list[TransformAction] = [
        "flag_only", "impute_mean", "drop_column", "impute_median", "trim_whitespace",
    ]

    assert sorted(plan, key=execution_rank) == [
        # impute_mean before impute_median, as the plan listed them.
        "drop_column", "trim_whitespace", "impute_mean", "impute_median", "flag_only",
    ]


def test_an_action_outside_the_catalog_has_no_rank() -> None:
    with pytest.raises(KeyError):
        execution_rank("delete_everything")  # type: ignore[arg-type]  # the whitelist is what this checks
