"""plan_proposed.json, plan_final.json and cleaning_report.json
(docs/CONTRACTS.md sections 4 and 5)."""

from typing import Any, ClassVar, Literal

from pydantic import NonNegativeInt

from contracts._base import ContractFile, ContractModel
from contracts.profile import CanonicalField, SemanticType

# The transform catalog, docs/AI_PIPELINE.md section 6. Typing every action
# field with it is the whitelist: an off-catalog action cannot reach a contract
# file. Which action is legal for which column is checked by stage 1, not here.
TransformAction = Literal[
    "impute_median",
    "impute_mean",
    "impute_mode",
    "impute_constant",
    "drop_rows_missing",
    "drop_column",
    "parse_datetime",
    "cast_type",
    "trim_whitespace",
    "normalize_case",
    "standardize_categories",
    "fix_negative",
    "remove_exact_duplicates",
    "flag_duplicate_keys",
    "clip_outliers_iqr",
    "flag_only",
]
PlanSource = Literal["ai", "user_edited", "manual"]


# --- plan_proposed.json / plan_final.json -----------------------------------


class DatasetAction(ContractModel):
    action: TransformAction
    params: dict[str, Any]
    rationale: str
    alternatives: list[TransformAction]
    edited_by_user: bool


class ColumnAction(ContractModel):
    source_name: str
    semantic_type: SemanticType
    canonical_field: CanonicalField
    action: TransformAction
    params: dict[str, Any]
    rationale: str
    alternatives: list[TransformAction]
    edited_by_user: bool


class CleaningPlanContract(ContractFile):
    """Shared by plan_proposed.json and plan_final.json ("identical schema")."""
    # 2 since 2E-e: the canonical enum gained "order_id" (and the issue enum
    # "order_id_not_one_order"). A reader validating these as closed enums
    # rejects the new values, so widening is breaking - a major bump
    # (CONTRACTS section 10, Thach).
    supported_major: ClassVar[int] = 2
    stale_major_hint: ClassVar[str] = (
        ": this file was written by an earlier stage 1 without the order_id field; "
        "re-upload the file")

    source: PlanSource
    dataset_actions: list[DatasetAction]
    column_actions: list[ColumnAction]


# --- cleaning_report.json ---------------------------------------------------


class ChangeLogEntry(ContractModel):
    action: TransformAction
    # None for dataset-level actions: apply(df, column | None, params).
    column: str | None
    cells_affected: NonNegativeInt
    rows_affected: NonNegativeInt
    params: dict[str, Any]
    detail: str


class CleaningWarning(ContractModel):
    code: str
    detail: str


class CleaningReportContract(ContractFile):
    # 2 since 2E-e: the canonical enum gained "order_id" (and the issue enum
    # "order_id_not_one_order"). A reader validating these as closed enums
    # rejects the new values, so widening is breaking - a major bump
    # (CONTRACTS section 10, Thach).
    supported_major: ClassVar[int] = 2
    stale_major_hint: ClassVar[str] = (
        ": this file was written by an earlier stage 1 without the order_id field; "
        "re-upload the file")
    rows_in: NonNegativeInt
    rows_out: NonNegativeInt
    columns_in: NonNegativeInt
    columns_out: NonNegativeInt
    changes: list[ChangeLogEntry]
    warnings: list[CleaningWarning]
    column_mapping: dict[str, CanonicalField]
