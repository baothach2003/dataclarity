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


class CustomerPlaceholder(ContractModel):
    """A customer value that may stand for walk-ins (2E-k), found by stage 1
    on the raw file: a known placeholder word, or a value carrying 10% or more
    of the counted lines or of the sale revenue. Review asks about each."""

    value: str  # as written in the file (its commonest spelling)
    lines: NonNegativeInt
    lines_pct: Percent
    revenue_pct: Percent | None  # None when the file has no sale revenue
    why: Literal["word", "share"]


# The four classes of a line that is not a product (Thach, 2E-d2): a charge
# the customer paid (postage) stays in revenue; a discount stays in revenue as
# a deduction (2E-c); a fee or cost, and an accounting adjustment, leave it.
LineClass = Literal["charge", "discount", "cost", "adjustment"]


class NonProductCandidate(ContractModel):
    """A product key whose lines may not be products (2E-d2), found by stage 1
    on the raw file: its SKU text, or the name its lines carry most often,
    begins or ends with a class word ("POSTAGE", "AMAZON FEE", "Adjust bad
    debt"). Review asks the user what it is; the suggestion never applies by
    itself."""

    value: str  # the SKU (or, for a line without one, the name) as written most often
    field: Literal["sku", "product_name"]
    name: str | None  # the commonest name on its lines, for display
    lines: NonNegativeInt
    # Sums of its counted lines' amounts: M "Manual" on Online Retail II is
    # +341,104.90 and -423,886.17, which a net figure would hide.
    positive: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    negative: Annotated[float, Field(le=0, allow_inf_nan=False)]
    suggested: LineClass | None  # None: a word that fits no class ("SAMPLES")
    word: str  # the word that made it a candidate


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
    # 2.2 (2E-k): stage 1's own measures on the raw file and these columns'
    # mapping - the customer values that may be walk-in placeholders, and
    # whether the order-id check could read dates only (most receipts name no
    # customer, one customer is on most, or fewer than two are named; None:
    # not measured).
    # None: not measured (the raw file did not parse into lines, or a file
    # older than 2.2) - Review then reads profile.json's top values.
    customer_placeholders: list[CustomerPlaceholder] | None = None
    order_id_date_only: bool | None = None
    # 2.3 (2E-d2): the product keys that may not be products, commonest
    # first. None: not measured (quantity or price not mapped, or no line
    # counted) - Review then reads profile.json's top values.
    non_product_candidates: list[NonProductCandidate] | None = None

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
