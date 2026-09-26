"""What the 16 transforms apply to and in which order they run
(docs/AI_PIPELINE.md section 6). What each one does: `transforms.py`.

Everything here is data, not branching logic: the legality matrix is a table
the AI's plan is checked against (stage 1E) and the tests walk every
(semantic_type, action) pair. Adding an action means adding a row, not an `if`.
The params an action takes are named here; whether a value is acceptable is
`transform_params.py`.
"""

from typing import Literal, get_args

from contracts.cleaning import TransformAction
from contracts.profile import CanonicalField, SemanticType

Scope = Literal["column", "dataset"]

# `ALL_ACTIONS` has no order; this one is the catalog's own (AI_PIPELINE section 6).
_CATALOG_ORDER: tuple[TransformAction, ...] = get_args(TransformAction)
ALL_ACTIONS: frozenset[TransformAction] = frozenset(_CATALOG_ORDER)
ALL_SEMANTIC_TYPES: frozenset[SemanticType] = frozenset(get_args(SemanticType))

NUMERIC_TYPES: frozenset[SemanticType] = frozenset({"numeric_continuous", "numeric_discrete"})
CATEGORICAL_TYPES: frozenset[SemanticType] = frozenset(
    {"categorical_nominal", "categorical_ordinal"}
)
# "text/categorical" in the catalog table.
TEXTUAL_TYPES: frozenset[SemanticType] = CATEGORICAL_TYPES | {"text"}
# The types the two string-shape actions apply to. An identifier is included
# (decided by Thach in 1D, AI_PIPELINE section 6 updated): trimming or
# re-casing a SKU standardizes how it is written and invents nothing, unlike
# imputation, which stays illegal on an identifier.
STRING_SHAPE_TYPES: frozenset[SemanticType] = TEXTUAL_TYPES | {"identifier"}

# The two dataset-wide actions: they take no column and read the whole frame.
DATASET_ACTIONS: frozenset[TransformAction] = frozenset(
    {"remove_exact_duplicates", "flag_duplicate_keys"}
)

# Filling a missing cell with a computed or chosen value. Illegal on a required
# canonical field, where an invented value would become a number in the report.
IMPUTATION_ACTIONS: frozenset[TransformAction] = frozenset(
    {"impute_median", "impute_mean", "impute_mode", "impute_constant"}
)
# Without these three a row cannot be counted at all (AI_PIPELINE section 6).
REQUIRED_CANONICAL_FIELDS: frozenset[CanonicalField] = frozenset(
    {"product_name", "transaction_date", "quantity"}
)
# Never imputed: the required fields (an invented value would be counted as
# measured), order_id (2E-e) - one filled-in id would merge every blank line
# into a single giant order, and AOV would read it as one basket - and
# customer (Thach, 2E-k), keyed on the field whatever its semantic type: an
# imputed "Unknown" became the top customer carrying every walk-in's money,
# the bridge's unattributed term vanished, and a batch code passed as a
# receipt number (2E-e2 doubt-review cycle 2 F11, cycle 3 F1).
NEVER_IMPUTED_FIELDS: frozenset[CanonicalField] = REQUIRED_CANONICAL_FIELDS | {
    "order_id", "customer"}
# The only actions an order_id column takes: none of them rewrites an id. A
# cast to a number blanked every "C..." cancellation id (return rate 0.25 ->
# 1.25), clip_outliers_iqr wrote "1334.5" into 28 walk-in receipt ids (same-day
# receipts merged), fix_negative rewrites "-5", and a case change can merge two
# ids (2E-e doubt-review F3, cycle 2 F3).
ORDER_ID_ACTIONS: frozenset[TransformAction] = frozenset(
    {"drop_rows_missing", "drop_column", "flag_only", "trim_whitespace"})

# The semantic types each column action is legal for. Absent from the catalog
# table means "any" (drop_rows_missing, drop_column, cast_type, flag_only): they
# neither invent a value nor assume a shape.
LEGAL_SEMANTIC_TYPES: dict[TransformAction, frozenset[SemanticType]] = {
    "impute_median": NUMERIC_TYPES,
    "impute_mean": NUMERIC_TYPES,
    "impute_mode": TEXTUAL_TYPES | {"boolean"},
    "impute_constant": TEXTUAL_TYPES | {"boolean"},
    "drop_rows_missing": ALL_SEMANTIC_TYPES,
    "drop_column": ALL_SEMANTIC_TYPES,
    "parse_datetime": frozenset({"datetime"}),
    "cast_type": ALL_SEMANTIC_TYPES,
    "trim_whitespace": STRING_SHAPE_TYPES,
    "normalize_case": STRING_SHAPE_TYPES,
    "standardize_categories": CATEGORICAL_TYPES,
    "fix_negative": NUMERIC_TYPES,
    "clip_outliers_iqr": NUMERIC_TYPES,
    "flag_only": ALL_SEMANTIC_TYPES,
}

# The fixed execution order, one group per step. Order changes results (trimming
# after merging labels would leave " Cafe" unmerged), so the plan never sets it;
# within a group the plan's own order is kept.
EXECUTION_ORDER: tuple[tuple[TransformAction, ...], ...] = (
    ("drop_column",),
    ("remove_exact_duplicates",),
    ("trim_whitespace",),
    ("normalize_case",),
    ("parse_datetime", "cast_type"),
    # Dropping first: an imputed median must be the median of the rows that stay
    # (decided by Thach in 1F; before, both shared one group and the plan's
    # column order decided).
    ("drop_rows_missing",),
    ("impute_median", "impute_mean", "impute_mode", "impute_constant"),
    ("standardize_categories",),
    ("fix_negative", "clip_outliers_iqr"),
    ("flag_duplicate_keys", "flag_only"),
)

# Params an action cannot run without; everything else has a documented default.
REQUIRED_PARAMS: dict[TransformAction, frozenset[str]] = {
    "impute_constant": frozenset({"value"}),
    "cast_type": frozenset({"target"}),
    "normalize_case": frozenset({"mode"}),
    "standardize_categories": frozenset({"mapping"}),
    "flag_duplicate_keys": frozenset({"keys"}),
}
OPTIONAL_PARAMS: dict[TransformAction, frozenset[str]] = {
    "parse_datetime": frozenset({"format", "dayfirst"}),
    "fix_negative": frozenset({"strategy"}),
    "clip_outliers_iqr": frozenset({"k"}),
    "flag_only": frozenset({"note"}),
}

CAST_TARGETS: frozenset[str] = frozenset({"integer", "float", "string", "boolean"})
CASE_MODES: frozenset[str] = frozenset({"title", "lower", "upper"})
NEGATIVE_STRATEGIES: frozenset[str] = frozenset({"flag", "abs", "drop"})


def scope_of(action: TransformAction) -> Scope:
    return "dataset" if action in DATASET_ACTIONS else "column"


def execution_rank(action: TransformAction) -> int:
    """The action's place in the fixed order. Sorting a plan by this with a
    stable sort keeps the plan's own order inside a group."""
    for rank, group in enumerate(EXECUTION_ORDER):
        if action in group:
            return rank
    raise KeyError(f"{action} is not in the execution order")


def illegality_reason(
    action: TransformAction,
    semantic_type: SemanticType | None = None,
    canonical_field: CanonicalField | None = None,
) -> str | None:
    """Why this action may not run on this column, or None when it may.

    A dataset action is checked with `semantic_type=None`: it has no column.
    """
    if action not in ALL_ACTIONS:
        return f"{action} is not in the transform catalog"
    if scope_of(action) == "dataset":
        if semantic_type is not None:
            return f"{action} applies to the dataset, not to a column"
        return None
    if semantic_type is None:
        return f"{action} applies to a column, not to the dataset"
    if semantic_type not in LEGAL_SEMANTIC_TYPES[action]:
        return f"{action} is not legal for a {semantic_type} column"
    if (canonical_field == "order_id" and action not in ORDER_ID_ACTIONS
            and action not in IMPUTATION_ACTIONS):
        return (f"{action} is not legal for order_id: an id is text and must stay as it "
                f"is - rewriting ids splits or merges orders")
    if canonical_field in NEVER_IMPUTED_FIELDS and action in IMPUTATION_ACTIONS:
        # Imputation only: a filled-in product name or quantity would be
        # counted in the report as if it had been measured (CLAUDE.md 3.2).
        # Every other action the semantic type allows stays legal here, or
        # transaction_date could never be parsed (AI_PIPELINE section 6).
        if canonical_field == "order_id":
            return (f"{action} is not legal for order_id: one filled-in id would merge "
                    f"every blank line into a single order - drop those rows, or leave "
                    f"them and the figures count lines")
        if canonical_field == "customer":
            return (f"{action} is not legal for customer: a filled-in value becomes a customer "
                    f"the file never named - leave the blanks, they are walk-ins")
        return (
            f"{action} is not legal for {canonical_field}, a required field: "
            f"use drop_rows_missing or flag_only"
        )
    return None


def is_legal(
    action: TransformAction,
    semantic_type: SemanticType | None = None,
    canonical_field: CanonicalField | None = None,
) -> bool:
    return illegality_reason(action, semantic_type, canonical_field) is None


def legal_column_actions(
    semantic_type: SemanticType, canonical_field: CanonicalField
) -> list[TransformAction]:
    """Every action a plan may give this column, in the catalog's order. The AI
    is shown this list, so the whitelist is something it is told, not guessed."""
    return [
        action
        for action in _CATALOG_ORDER
        if scope_of(action) == "column" and is_legal(action, semantic_type, canonical_field)
    ]


def legal_dataset_actions() -> list[TransformAction]:
    return [action for action in _CATALOG_ORDER if scope_of(action) == "dataset"]
