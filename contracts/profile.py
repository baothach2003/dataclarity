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


# How a column's day-month-year or month-day-year cells are written (2E-j).
DateOrder = Literal["day_first", "month_first"]


class DateOrderMeasure(ContractModel):
    """Stage 1's own measure of a column's cells written day-month-year or
    month-day-year (two numbers and a year: "05/01/2026", "5.1.26"), on the
    raw file (2E-j). A first number 13-31 proves day first, a second number
    13-31 month first. `ambiguous` counts the cells either order reads, each
    as another date (two numbers 1-12 that differ; "05/05/2026" reads the
    same either way). `decision` is "ask" when both orders are proven, or
    neither is and some cell is ambiguous, and Review then asks the user; a
    column where nothing depends on the order carries no measure. `hint` is
    a suggestion only (2E-d2): the 1st of each month written day first never
    proves itself. The examples are the date text alone, never the cell."""

    shaped: Annotated[int, Field(gt=0)]
    day_first: NonNegativeInt
    month_first: NonNegativeInt
    ambiguous: NonNegativeInt
    day_first_example: str | None
    month_first_example: str | None
    decision: DateOrder | Literal["ask"]
    hint: DateOrder | None

    @model_validator(mode="after")
    def _decision_follows_the_counts(self) -> Self:
        proven = {"day_first": self.day_first > 0, "month_first": self.month_first > 0}
        if sum(proven.values()) == 1:
            expected = next(order for order, proof in proven.items() if proof)
        elif all(proven.values()) or self.ambiguous:
            expected = "ask"
        else:
            raise ValueError("a column where nothing depends on the order carries no measure")
        if self.decision != expected:
            raise ValueError(f"decision must be {expected!r} for these counts")
        if self.hint is not None and self.decision != "ask":
            raise ValueError("a hint is given only when the order is asked")
        if (self.day_first_example is None) != (self.day_first == 0) or (
                (self.month_first_example is None) != (self.month_first == 0)):
            raise ValueError("an example is given exactly when its order is proven")
        return self


# How a numeric column's numbers are written (2E-u1): the decimal mark.
NumberFormat = Literal["decimal_point", "decimal_comma"]


class NumberFormatMeasure(ContractModel):
    """Stage 1's own measure of a column's cells read as numbers written
    for people (2E-u1; Thach, 2E-u F1): "1,000.00", "$12.50", "10,5". A cell
    whose last separator is not followed by three digits, or that holds both
    marks, proves its decimal mark (`point`, `comma`); "1,000" reads two ways
    (`ambiguous`). `decision`: the mark the column proves for its ambiguous
    cells; "ask" when it proves neither or both and some cell is ambiguous -
    Review then asks; None when no cell depends on it. `currency` counts the
    readable cells that carried a currency symbol; `unreadable` the
    non-blank cells no rule reads. The examples are cells as written."""

    readable: NonNegativeInt
    point: NonNegativeInt
    comma: NonNegativeInt
    ambiguous: NonNegativeInt
    currency: NonNegativeInt
    unreadable: NonNegativeInt
    point_example: str | None
    comma_example: str | None
    ambiguous_example: str | None
    decision: NumberFormat | Literal["ask"] | None

    @model_validator(mode="after")
    def _decision_follows_the_counts(self) -> Self:
        if self.point and not self.comma:
            expected: str | None = "decimal_point"
        elif self.comma and not self.point:
            expected = "decimal_comma"
        else:
            expected = "ask" if self.ambiguous else None
        if self.decision != expected:
            raise ValueError(f"decision must be {expected!r} for these counts")
        if any((example is None) != (count == 0) for example, count in (
                (self.point_example, self.point), (self.comma_example, self.comma),
                (self.ambiguous_example, self.ambiguous))):
            raise ValueError("an example is given exactly when its cells are counted")
        return self


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
    # 1.1 (2E-j): only for a column with a cell written day-month-year or
    # month-day-year; None otherwise, and in a 1.0 file.
    date_order: DateOrderMeasure | None = None
    # 1.2 (2E-u1): for a text column with a cell read as a number written for
    # people (a separator, a decimal comma or a currency sign), and for a
    # column pandas reads as numbers only when it holds a question ("1.000",
    # "2.500" - review 1, F1); None otherwise, and in an earlier file.
    number_format: NumberFormatMeasure | None = None


class ProfileContract(ContractFile):
    filename: ClassVar[str | None] = "profile.json"
    stale_major_hint: ClassVar[str] = ": this file was written by an earlier stage 1; re-upload the file"
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
    on the raw file: a known placeholder word (`why` "word"), or an unusual
    share (`why` "share") - 10% or more of the counted lines or of the sale
    revenue, or the largest of the values not already asked at 4 times the
    next one, which on a small file can be a real customer (2E-r F4). Review
    asks about each; a false question costs one answer."""

    value: str  # as written in the file (its commonest spelling)
    lines: NonNegativeInt
    lines_pct: Percent
    revenue_pct: Percent | None  # None when the file has no sale revenue
    why: Literal["word", "share"]


# The classes of a line the user says is not an ordinary product (Thach,
# 2E-d2, 2E-l): a charge the customer paid (postage) stays in revenue but is
# no order; a discount stays in revenue as a deduction (2E-c); pooled items
# (many items under one code, Online Retail II's M "Manual") are sales ranked
# as no product; a fee or cost, and an accounting adjustment, leave revenue.
# "gift_card" since 2E-t1 (Thach, decision 4 of the line taxonomy): a voucher
# sold is a liability, outside revenue once the user confirms it.
LineClass = Literal["charge", "discount", "pooled", "cost", "adjustment", "gift_card"]


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
    suggested: LineClass | None  # None: a word that fits no class (none since 2E-l)
    word: str  # the word that made it a candidate


class SchemaInferenceContract(ContractFile):
    filename: ClassVar[str | None] = "schema_inference.json"
    # 2 since 2E-e: the canonical enum gained "order_id" (and the issue enum
    # "order_id_not_one_order"). A reader validating these as closed enums
    # rejects the new values, so widening is breaking - a major bump
    # (CONTRACTS section 10, Thach). 3 since 2E-l: the line-class enum gained
    # "pooled" (many items under one code). 4 since 2E-t1: it gained
    # "gift_card" (the line taxonomy).
    supported_major: ClassVar[int] = 4
    stale_major_hint: ClassVar[str] = (
        ": this file was written by an earlier stage 1 with fewer line classes, "
        "without the line taxonomy or without the order_id field; re-upload the file")
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
