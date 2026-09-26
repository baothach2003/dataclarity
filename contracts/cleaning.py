"""plan_proposed.json, plan_final.json and cleaning_report.json
(docs/CONTRACTS.md sections 4 and 5)."""

from typing import Any, ClassVar, Literal

from pydantic import Field, NonNegativeInt, StrictBool, field_validator

from contracts._base import ContractFile, ContractModel
from contracts.profile import CanonicalField, LineClass, SemanticType

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


class LineClassAnswer(ContractModel):
    """One product key the user classed in Review (2E-d2): its SKU - or, for
    lines without one, its name - as written; stages 2 and 3 compare it as
    they compare products (shared/line_classes.py)."""

    value: str
    field: Literal["sku", "product_name"]
    line_class: LineClass


class OrderConfirmations(ContractModel):
    """Two answers only the user can give, asked on the Review screen (Thach,
    2E-e2). None: not asked, or not answered.

    - order_id_is_receipt: when no line names a customer an order id is
      checked by date only, and a daily batch or Z-report code passes that
      check; unless this is True the figures count lines (unconfirmed means
      untrusted, Thach).
    - customer_on_first_line_only: a receipt's unnamed lines take its one
      named customer (2E-f) unless this is False - a batch code with one named
      line and walk-ins looks the same (2E-f known limit L1, which Thach
      accepted as rare). Withheld when unanswered, a header-style credit
      note's named line kept its customer while the purchase it refunds lost
      it (2E-e2 review A), so no answer fills, as 2E-f did.

    Strict booleans: "yes" or 1 is no answer anyone gave (review N)."""

    order_id_is_receipt: StrictBool | None = None
    customer_on_first_line_only: StrictBool | None = None
    # 2.2 (2E-k): the customer values the user confirmed as a placeholder for
    # walk-ins ("Guest", "Walk-in", "0"), as written; stages 2 and 3 compare
    # them by customer identity, and their lines have no customer.
    customer_placeholders: list[str] = Field(default_factory=list)
    # 2.3 (2E-d2): what the user said a product key's lines are when they are
    # not products. Unanswered, or "a product", a key is not listed and its
    # lines stay products.
    line_classes: list[LineClassAnswer] = Field(default_factory=list)


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
    # 2.1 (2E-e2): optional, the user's own answers; the AI's proposal never
    # carries one (stage 1 builds it field by field).
    confirmations: OrderConfirmations = Field(default_factory=OrderConfirmations)

    @field_validator("confirmations", mode="before")
    @classmethod
    def _null_is_unanswered(cls, value: object) -> object:
        # A client that sends null answered nothing; refusing the whole plan
        # for it (review N) helped no one.
        return {} if value is None else value


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
    # 2.1 (2E-e2): the answers that ran, for stages 2 and 3; a 2.0 report
    # reads as nothing confirmed, and so does null (review cycle 3 F6).
    confirmations: OrderConfirmations = Field(default_factory=OrderConfirmations)

    @field_validator("confirmations", mode="before")
    @classmethod
    def _null_is_unanswered(cls, value: object) -> object:
        return {} if value is None else value
