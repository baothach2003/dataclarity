"""profile.json and schema_inference.json (docs/CONTRACTS.md sections 2 and 3)."""

from collections import Counter
from typing import Annotated, ClassVar, Literal, Self

from pydantic import Field, NonNegativeInt, model_validator

from contracts._base import ContractFile, ContractModel, Percent, UnitInterval

# Enums from docs/AI_PIPELINE.md section 5, shared by schema inference and the
# cleaning plan.
SemanticType = Literal[
    "numeric_continuous",
    "numeric_discrete",
    "categorical_nominal",
    "categorical_ordinal",
    "datetime",
    "identifier",
    "boolean",
    "text",
]
CanonicalField = Literal[
    "product_name",
    "sku",
    "category",
    "transaction_date",
    "quantity",
    "unit_price",
    "transaction_type",
    "supplier",
    "customer",
    "note",
    "order_id",
    "ignore",
]
IssueCode = Literal[
    "missing_values",
    "invalid_dates",
    "mixed_date_formats",
    "negative_values",
    "zero_values",
    "inconsistent_case",
    "trailing_whitespace",
    "near_duplicate_labels",
    "outliers_iqr",
    "mixed_types",
    "constant_column",
    "all_null_column",
    "duplicate_rows",
    "duplicate_business_key",
    # Stage 1's own check, never the AI's (2E-e): a column mapped to order_id
    # whose ids span several days or customers is not an order id.
    "order_id_not_one_order",
    "non_numeric_in_numeric",
]
Severity = Literal["low", "medium", "high"]

MAX_TOP_VALUES = 10


# --- profile.json -----------------------------------------------------------


class DatasetStats(ContractModel):
    rows: NonNegativeInt
    columns: NonNegativeInt
    duplicate_rows: NonNegativeInt
    missing_cells_pct: Percent
    encoding_used: str
    delimiter: str


class TopValue(ContractModel):
    value: str
    count: NonNegativeInt


class ColumnProfile(ContractModel):
    name: str
    dtype: str
    null_count: NonNegativeInt
    null_pct: Percent
    unique_count: NonNegativeInt
    # Required but nullable: null for non-numeric columns (CONTRACTS.md section 2).
    min: float | None
    max: float | None
    mean: float | None
    median: float | None
    q1: float | None
    q3: float | None
    top_values: Annotated[list[TopValue], Field(max_length=MAX_TOP_VALUES)]
    sample_values: list[str | None]


class ProfileContract(ContractFile):
    dataset: DatasetStats
    columns: list[ColumnProfile]


# --- schema_inference.json --------------------------------------------------


class DatasetIssue(ContractModel):
    code: IssueCode
    count: NonNegativeInt
    severity: Severity
    detail: str


class ColumnIssue(ContractModel):
    code: IssueCode
    count: NonNegativeInt
    # Required but nullable: null when the profile holds no percentage for the
    # issue, since the AI may not invent one (CONTRACTS.md section 3).
    pct: Percent | None
    examples: list[str]


class ColumnInference(ContractModel):
    source_name: str
    semantic_type: SemanticType
    canonical_field: CanonicalField
    confidence: UnitInterval
    issues: list[ColumnIssue]


class SchemaInferenceContract(ContractFile):
    # 2 since 2E-e: the canonical enum gained "order_id" (and the issue enum
    # "order_id_not_one_order"). A reader validating these as closed enums
    # rejects the new values, so widening is breaking - a major bump
    # (CONTRACTS section 10, Thach).
    supported_major: ClassVar[int] = 2
    stale_major_hint: ClassVar[str] = (
        ": this file was written by an earlier stage 1 without the order_id field; "
        "re-upload the file")
    model_used: str
    domain_confidence: UnitInterval
    domain_reasoning: str
    dataset_issues: list[DatasetIssue]
    columns: list[ColumnInference]
    # 2.1 (2E-e2): stage 1's own measure, never the AI's - on the raw file and
    # these columns' mapping, the lines with no customer that the fill would
    # give their receipt's one named customer. None: not measured (no sale
    # line parses on the raw file, blank ids make it count lines, or a 2.0
    # file). Review asks about the fill when it is above 0 or None.
    receipt_fill_lines: NonNegativeInt | None = None

    # "Every profiled column appears exactly once" also needs profile.json, so
    # only its in-file half (no duplicates) is checked here; stage 1 checks the
    # rest against the profile.
    @model_validator(mode="after")
    def _columns_are_consistent(self) -> Self:
        names = Counter(column.source_name for column in self.columns)
        repeated_names = sorted(name for name, n in names.items() if n > 1)
        if repeated_names:
            raise ValueError(f"source_name listed more than once: {repeated_names}")

        fields = Counter(
            column.canonical_field
            for column in self.columns
            if column.canonical_field != "ignore"
        )
        repeated_fields = sorted(field for field, n in fields.items() if n > 1)
        if repeated_fields:
            raise ValueError(
                f"canonical_field mapped by more than one column: {repeated_fields}"
            )
        return self
