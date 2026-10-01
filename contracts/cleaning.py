"""plan_proposed.json, plan_final.json and cleaning_report.json
(docs/CONTRACTS.md sections 4 and 5)."""

from typing import Any, ClassVar, Literal, get_args

from pydantic import Field, NonNegativeInt, StrictBool, field_validator

from contracts._base import ContractFile, ContractModel
from contracts.profile import CanonicalField, DateOrder, LineClass, NumberFormat, SemanticType

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

# The line taxonomy (session 2E-t1; docs/LINE_TAXONOMY.md section 2.1): the
# closed list of classes stage 1 writes into cleaned.csv's `line_class`, one per
# line. The first ten are counted (a counted line also needs a date to be in a
# month); the rest are outside revenue and reported. `unclassified` is the
# tested, empty class (Thach: no refusals in v1).
CleanedLineClass = Literal[
    "sale", "pooled_sale", "customer_return", "pooled_return", "allowance", "pooled_allowance",
    "discount", "charge", "no_money", "pooled_no_money",
    "gift_card_sale", "gift_card_redemption", "cost", "adjustment", "stock_in", "unclassified",
    "unmeasurable",
]
CLEANED_LINE_CLASSES: tuple[str, ...] = get_args(CleanedLineClass)
# cleaned.csv's three columns stage 1 adds (section 4): the class; "user" when
# the item answer decided it, "rule" otherwise; the suggestion pending on the
# line's key, a missing cell when there is none.
LINE_CLASS_COLUMN = "line_class"
CLASS_SOURCE_COLUMN = "class_source"
SUGGESTED_CLASS_COLUMN = "suggested_class"
TAXONOMY_COLUMNS = (LINE_CLASS_COLUMN, CLASS_SOURCE_COLUMN, SUGGESTED_CLASS_COLUMN)


class LineClassAnswer(ContractModel):
    """One product key the user classed in Review (2E-d2): its SKU - or, for
    lines without one, its name - as written; stages 2 and 3 compare it as
    they compare products (shared/line_classes.py).

    "product" is an answer too, sent for a name (2E-l review cycle 1): a
    line with no SKU takes the class of the one SKU its name is sold under
    only while the name is unanswered, and "a product" said for the name
    must hold (CLAUDE.md 3.3). For a SKU it changes no figure, but since 2E-t1
    it is an answer too: the key carries no pending suggestion into
    cleaned.csv (2E-t1 review cycle 1 #2)."""

    value: str
    field: Literal["sku", "product_name"]
    line_class: LineClass | Literal["product"]


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
    # 4.2 (2E-u3): the candidates the user answered "a real customer", as
    # written - so an unanswered one can be told from No (cleaning_report's
    # `unconfirmed_placeholders`). Their lines keep their customer either way.
    customer_not_placeholders: list[str] = Field(default_factory=list)
    # 2.3 (2E-d2): what the user said a product key's lines are when they are
    # not products. Unanswered, a key is not listed and its lines stay
    # products; "a product" is listed for a name (3.0, 2E-l review cycle 1:
    # it stops the name's lines taking their SKU's class), and for a SKU since
    # 4.0 (2E-t1: it clears the key's pending suggestion).
    line_classes: list[LineClassAnswer] = Field(default_factory=list)
    # 3.1 (2E-j): the user's answer to Review's date question - True: the
    # date column's day-month-year cells are written day first; False: month
    # first. Asked only when the file proves neither (or both). In
    # cleaning_report.json the order that was applied is `date_order`.
    dates_day_first: StrictBool | None = None
    # 4.1 (2E-u1): Review's answers to the number question, by source column
    # - the decimal mark of the cells the file cannot prove ("1,000"). Asked
    # only where the column proves neither (or both); cells that prove their
    # own mark are read by it. In cleaning_report.json what ran is
    # `number_formats`.
    number_formats: dict[str, NumberFormat] = Field(default_factory=dict)


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
    # (CONTRACTS section 10, Thach). 3 since 2E-l: the line-class enum gained
    # "pooled" (many items under one code). 4 since 2E-t1: it gained
    # "gift_card", and cleaned.csv carries each line's class (the line
    # taxonomy).
    supported_major: ClassVar[int] = 4
    stale_major_hint: ClassVar[str] = (
        ": this file was written by an earlier stage 1 with fewer line classes, "
        "without the line taxonomy or without the order_id field; re-upload the file")

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


class AppliedNumberFormat(ContractModel):
    """What stage 1 did to one quantity or price column before the plan ran
    (2E-u1): the mark its ambiguous cells were read with (None: no cell
    needed one), the cells it rewrote as plain numbers, the non-blank cells
    no rule reads (left as written - stage 2 lists them as unmeasurable), and
    whether the mark was the user's answer rather than the file's proof."""

    format: NumberFormat | None
    rewritten: NonNegativeInt
    unreadable: NonNegativeInt
    answered: bool


class CleaningReportContract(ContractFile):
    filename: ClassVar[str | None] = "cleaning_report.json"
    # 2 since 2E-e: the canonical enum gained "order_id" (and the issue enum
    # "order_id_not_one_order"). A reader validating these as closed enums
    # rejects the new values, so widening is breaking - a major bump
    # (CONTRACTS section 10, Thach). 3 since 2E-l: the line-class enum gained
    # "pooled" (many items under one code). 4 since 2E-t1: it gained
    # "gift_card", and cleaned.csv carries each line's class (the line
    # taxonomy).
    supported_major: ClassVar[int] = 4
    stale_major_hint: ClassVar[str] = (
        ": this file was written by an earlier stage 1 with fewer line classes, "
        "without the line taxonomy or without the order_id field; re-upload the file")
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
    # 3.1 (2E-j): the order the transaction_date column's day-month-year cells
    # were read in - the user's answer, else what the raw file proved; None
    # when no such cell (or a 3.0 report, read as before).
    date_order: DateOrder | None = None
    # 4.1 (2E-u1): per quantity and price column, what stage 1's number
    # reading did; empty in an earlier report.
    number_formats: dict[str, AppliedNumberFormat] = Field(default_factory=dict)
    # 4.2 (2E-u3): Review's walk-in placeholder candidates for the customer
    # column as mapped, measured on the raw file, that the user neither
    # confirmed nor answered "a real customer" - as written most often,
    # commonest first. They stay customers in every figure (the standing
    # no-guess rule); stages 2 and 5 mark them "suggested, not confirmed".
    # Empty in an earlier report.
    unconfirmed_placeholders: list[str] = Field(default_factory=list)

    @field_validator("confirmations", mode="before")
    @classmethod
    def _null_is_unanswered(cls, value: object) -> object:
        return {} if value is None else value

    def applied_confirmations(self) -> OrderConfirmations:
        """The answers as stages 2 and 3 read them: with the date order stage
        1 applied, so a date column the plan did not parse is read in it (a
        proof is no answer, so `confirmations` keeps the user's alone)."""
        applied = None if self.date_order is None else self.date_order == "day_first"
        return self.confirmations.model_copy(update={"dates_day_first": applied})
