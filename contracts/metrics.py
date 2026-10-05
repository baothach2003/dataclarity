"""metrics.json (docs/CONTRACTS.md section 6). Stage 2 never calls the AI."""

from datetime import date
from typing import Annotated, Any, ClassVar, Literal, Self

from pydantic import Field, NonNegativeInt, model_validator

from contracts._base import (
    ContractFile,
    ContractModel,
    NonNegativeFloat,
    Percent,
    YearMonth,
    major_of,
    minor_version,
    numbers_json_cannot_carry,
)
from contracts.lines import (
    TOO_LARGE_TO_ADD,
    Notes,
    OutsideRevenueLines,
    RevenueIdentity,
    UnclassifiedLines,
    UnmeasurableLines,
)
from contracts.profile import LineClass

# The refusal of a 16.0 file written before the line taxonomy's blocks
# (2E-t1, before 2E-t2): another version's file, as an older major is (2E-v).
BEFORE_THE_LINE_TAXONOMY = "this metrics.json was written before the line taxonomy's blocks"

# Only definitional bounds are enforced. Revenue, revenue shares and return
# rates stay unbounded: refunds can make net revenue negative, and returns in a
# period can belong to orders from an earlier one.
#
# Schema 2.0 (session 2E; 5.0 in 2E-e: orders by `orders_basis`). An order is
# a sale row (shared/transactions.py):
# orders, AOV, return_rate and RFM frequency changed meaning. A figure whose
# base is unusable, or whose only purpose is to compare the two months when
# the previous one is incomplete, is null and a `*_reason` says why - never a
# sign-inverted or half-month percentage. Every ratio with a zero or
# negligible denominator is null the same way: this supersedes 2A's "report
# 0.0" (Thach, 2E).


def _paired(unavailable: bool, reason: str | None, what: str) -> None:
    """A null says why, and a reason never sits beside a value: a reader must
    be able to tell "unavailable" from "missing by mistake" (2E)."""
    if unavailable and reason is None:
        raise ValueError(f"{what} is unavailable but no reason says why")
    if not unavailable and reason is not None:
        raise ValueError(f"{what} has a value, so it cannot also carry a reason")


def _paired_list(nulls: list[bool], reason: str | None, what: str) -> None:
    """One comparison spread over list members: all null with a reason, or
    all present without one. An empty list pairs with either - there is
    nothing to compare, and the reason may still record why."""
    if not nulls:
        return
    if not all(nulls) and any(nulls):
        raise ValueError(f"{what} is null for some members only; it is one "
                         "comparison, available for all or none")
    _paired(all(nulls), reason, what)


class Period(ContractModel):
    current: YearMonth
    previous: YearMonth
    data_start: date
    data_end: date
    # shared/periods.py: the previous month is a base the current one can be
    # compared with. When False every comparison below is null, and the
    # previous-month raw totals are a partial month (CONTRACTS.md section 6).
    previous_complete: bool
    previous_incomplete_reason: str | None
    # 14.0 (2E-j): every COUNTED line is at midnight on the 1st (or, 15.0 since
    # 2E-o, every one on the last day of its month), over two
    # months or more - the file records months, not days. Its last sale
    # month, once over, is then the current month, and stage 3's day-level
    # steps do not apply.
    month_grain: bool
    # 16.1 (2E-u6, Thach 2026-10-02): the last day a line may be dated - the
    # upload's day at UTC+14 (shared/periods.upload_cutoff). Lines after it
    # are left out of choosing this period (core.future_lines); stage 3 reads
    # it to choose its own coverage end the same way. Null in a 16.0 file.
    upload_cutoff: date | None = None

    @model_validator(mode="after")
    def _reason_when_incomplete(self) -> Self:
        _paired(not self.previous_complete, self.previous_incomplete_reason,
                "the previous month as a base")
        return self


class MonthlyRevenue(ContractModel):
    period: YearMonth
    revenue: float


class NonProductLines(ContractModel):
    """The lines of one class the user gave in Review (Thach, 2E-d2, 2E-l),
    dated and counted over the whole file: a charge the customer paid stays
    in revenue but is no order; a discount stays in revenue as a deduction;
    pooled items are sales and returns in every figure; a fee or cost, an
    accounting adjustment and (2E-t1) a gift card are left out of revenue - an
    adjustment's amount is reported as a reconciling amount, and a gift card
    sold is owed until redeemed. None of them is ranked in a product table.
    The reason says where the money went."""

    line_class: LineClass
    lines: Annotated[int, Field(gt=0)]
    amount: float
    amount_current: float
    amount_previous: float
    reason: str


class CoreMetrics(ContractModel):
    revenue_current: float
    revenue_previous: float
    revenue_change_pct: float | None
    revenue_change_pct_reason: str | None
    # 16.2 (the report redesign, step 1; Thach, 2026-10-05): this month's
    # revenue less last month's, the amount the report's summary states.
    # Null with the period's reason exactly when the previous month is
    # incomplete (never compared, CONTRACTS 11); an amount needs no base, so
    # a non-positive previous month still has one. Null in 16.1 and before.
    revenue_change: float | None = None
    revenue_change_reason: str | None = None
    # Distinct order ids with a sale row when `order_id` is mapped and passes
    # stage 1's check; else sale LINES (2E-e). The basis names which, so
    # stage 5 labels honestly ("average line value", "lines per customer").
    orders_basis: Literal["order_id", "lines"]
    orders_basis_reason: str | None
    orders_current: NonNegativeInt
    orders_previous: NonNegativeInt
    # Any revenue-counted row (3C). Buyers: customers with a sale row (2E) -
    # what the lever's level 1 counts, so B1 rests on stage 2's own figure.
    active_customers_current: NonNegativeInt
    active_customers_previous: NonNegativeInt
    buyers_current: NonNegativeInt
    buyers_previous: NonNegativeInt
    # Null with a reason when the month has no orders (2E, superseding 2A's 0.0).
    aov_current: float | None
    aov_current_reason: str | None
    aov_previous: float | None
    aov_previous_reason: str | None
    # Return lines / sale lines on basis "lines"; orders holding a return line /
    # orders holding a sale line on basis "order_id" (2E-e). Range [0,
    # infinity), not a proportion (2E).
    return_rate_current: NonNegativeFloat | None
    return_rate_current_reason: str | None
    return_rate_previous: NonNegativeFloat | None
    return_rate_previous_reason: str | None
    revenue_by_month: list[MonthlyRevenue]
    # Lines whose date is blank or no date - "now", a bare time, a year outside
    # 1900-2100, text that does not parse - belong to no month and are in no
    # figure; counted here with the reason, never dropped silently (Thach,
    # 2E-h). The reason is null exactly when the count is 0. An unmeasurable
    # line is reported once, in `unmeasurable` (Thach's Q24, 2E-t2).
    undated_lines: NonNegativeInt
    undated_lines_reason: str | None
    # 16.1 (2E-u6): the lines dated after `period.upload_cutoff`, of any
    # class, left out of choosing the period and the dates the file covers;
    # every other figure keeps them in their own month (the standing no-guess
    # rule, CLAUDE.md 3.3a). `future_revenue` is the counted ones' revenue.
    # The reason is null exactly when the count is 0; 0 in a 16.0 file.
    future_lines: NonNegativeInt = 0
    future_revenue: float = 0.0
    future_lines_reason: str | None = None
    # One row per class present, in the order charge, discount, pooled,
    # cost, adjustment, gift_card; empty when no line is classed (2E-d2, 2E-l,
    # 2E-t1).
    non_product: list[NonProductLines]
    # The line taxonomy (2E-t2; docs/LINE_TAXONOMY.md sections 3 and 5): the
    # compared months' revenue identity; the classes outside revenue per
    # scope; the lines no rule placed; the lines that could not be measured,
    # per scope and reason; the notes beside the figures the data cannot
    # fully tell apart (the standing rule, CLAUDE.md 3.3a).
    identity: RevenueIdentity
    outside_revenue: list[OutsideRevenueLines]
    unclassified: UnclassifiedLines
    unmeasurable: list[UnmeasurableLines]
    notes: Notes

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        classes = [row.line_class for row in self.non_product]
        if len(set(classes)) != len(classes):
            raise ValueError(f"non_product lists a class more than once: {classes}")
        if (self.undated_lines == 0) != (self.undated_lines_reason is None):
            raise ValueError("undated_lines_reason says why lines were left out; it is null "
                             "exactly when undated_lines is 0")
        if (self.future_lines == 0) != (self.future_lines_reason is None):
            raise ValueError("future_lines_reason says why lines were left out of the period; it is "
                             "null exactly when future_lines is 0")
        if self.future_lines == 0 and self.future_revenue != 0:
            raise ValueError("future_revenue is the revenue of the lines dated after the upload; it is 0 "
                             "when there are none")
        if self.orders_basis == "order_id" and self.orders_basis_reason is not None:
            raise ValueError("orders_basis_reason explains a fallback to lines; "
                             "it is null when the basis is order_id")
        for name in ("revenue_change_pct", "aov_current", "aov_previous",
                     "return_rate_current", "return_rate_previous"):
            _paired(getattr(self, name) is None, getattr(self, f"{name}_reason"), name)
        # A per-order figure is null exactly when there were no orders (F8).
        for period in ("current", "previous"):
            no_orders = getattr(self, f"orders_{period}") == 0
            for name in (f"aov_{period}", f"return_rate_{period}"):
                if (getattr(self, name) is None) != no_orders:
                    raise ValueError(f"{name} must be null exactly when there are no orders "
                                     f"(orders_{period} = {getattr(self, f'orders_{period}')})")
        return self


class SegmentSummary(ContractModel):
    segment: str
    customers: NonNegativeInt
    # Null when whole-file monetary is zero or negligible (2E).
    revenue_share_pct: float | None
    avg_monetary: float
    # Exists only to show migration between the two periods: null when the
    # previous month is incomplete (Thach, 2E).
    customers_previous: NonNegativeInt | None


class NewVsReturning(ContractModel):
    new_customers: NonNegativeInt
    returning_customers: NonNegativeInt
    new_revenue: float
    returning_revenue: float


class UnconfirmedPlaceholder(ContractModel):
    """A walk-in candidate left unanswered in Review (2E-u3): its counted
    lines in the file and in the two compared months, by customer identity."""

    value: str
    lines: Annotated[int, Field(gt=0)]
    lines_current: NonNegativeInt
    lines_previous: NonNegativeInt


class CustomerMetrics(ContractModel):
    rfm_reference_date: date
    segments: list[SegmentSummary]
    new_vs_returning: NewVsReturning
    customers_previous_reason: str | None
    revenue_share_reason: str | None
    # Counted lines with no customer that share a receipt with a line naming
    # one, left unattributed because the user answered in Review that the
    # customer is not written on a receipt's first line only (2E-e2): their
    # revenue is in no customer's figures, and a reader must see that. The
    # reason is null exactly when the count is 0.
    unfilled_receipt_lines: NonNegativeInt
    unfilled_receipt_lines_reason: str | None
    # Counted lines whose customer value the user confirmed in Review as a
    # placeholder for walk-ins (2E-k): no customer, so in no customer's
    # figures. The reason is null exactly when the count is 0.
    placeholder_lines: NonNegativeInt
    placeholder_lines_reason: str | None
    # 16.1 (2E-u3, Thach 2026-10-02): the walk-in candidates stage 1 recorded
    # as unanswered (cleaning_report.json `unconfirmed_placeholders`) - still
    # customers in every figure (CLAUDE.md 3.3a), marked "suggested, not
    # confirmed" like Q17. The reason is null exactly when the list is empty;
    # empty in a 16.0 file.
    unconfirmed_placeholders: list[UnconfirmedPlaceholder] = Field(default_factory=list)
    unconfirmed_placeholders_reason: str | None = None

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        if (not self.unconfirmed_placeholders) != (self.unconfirmed_placeholders_reason is None):
            raise ValueError("unconfirmed_placeholders_reason marks the values Review suggested; it is null "
                             "exactly when unconfirmed_placeholders is empty")
        if (self.unfilled_receipt_lines == 0) != (self.unfilled_receipt_lines_reason is None):
            raise ValueError("unfilled_receipt_lines_reason says why lines were left "
                             "unattributed; it is null exactly when unfilled_receipt_lines is 0")
        if (self.placeholder_lines == 0) != (self.placeholder_lines_reason is None):
            raise ValueError("placeholder_lines_reason says why lines have no customer; it is "
                             "null exactly when placeholder_lines is 0")
        _paired_list([segment.customers_previous is None for segment in self.segments],
                     self.customers_previous_reason, "customers_previous")
        _paired_list([segment.revenue_share_pct is None for segment in self.segments],
                     self.revenue_share_reason, "revenue_share_pct")
        return self


class Pareto(ContractModel):
    products_for_80pct_revenue: NonNegativeInt
    total_products: NonNegativeInt
    # Null when no product has positive revenue this month (2E).
    concentration_pct: Percent | None
    concentration_reason: str | None

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        _paired(self.concentration_pct is None, self.concentration_reason, "concentration_pct")
        return self


class TopProduct(ContractModel):
    product: str
    revenue: float
    units: int


class ProductDecline(ContractModel):
    product: str
    # The ranking key: the fall in money (negative). A percentage cannot rank
    # a product whose previous revenue was negative (2E).
    revenue_change: float
    revenue_change_pct: float | None
    revenue_change_pct_reason: str | None

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        _paired(self.revenue_change_pct is None, self.revenue_change_pct_reason,
                f"{self.product}'s revenue_change_pct")
        return self


class ProductVelocity(ContractModel):
    product: str
    units_per_day: NonNegativeFloat
    # Null when the file records no stock received for this product (2E-g):
    # stock on hand is unknown, and flooring it at 0 read "out of stock today".
    days_to_stockout: NonNegativeFloat | None
    days_to_stockout_reason: str | None

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        _paired(self.days_to_stockout is None, self.days_to_stockout_reason,
                f"{self.product}'s days_to_stockout")
        return self


class ProductMetrics(ContractModel):
    pareto: Pareto
    top_products: list[TopProduct]
    biggest_decliners: list[ProductDecline] | None
    biggest_decliners_reason: str | None
    # Null on EVERY file since 2E-t2, with its reason: stock figures are not
    # supported in v1 (Thach, the line taxonomy's scope cut - v1 analyses
    # sales, not inventory). The shape stays for v2.
    velocity: list[ProductVelocity] | None
    velocity_reason: str | None
    # Every product this block names whose key carries a line-class
    # suggestion nobody confirmed, by its label (unique), with that class -
    # shown as "(suggested: <class>, not confirmed)" (Thach's Q17, 2E-t2).
    suggested_classes: dict[str, LineClass]

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        _paired(self.biggest_decliners is None, self.biggest_decliners_reason,
                "biggest_decliners")
        _paired(self.velocity is None, self.velocity_reason, "velocity")
        if self.velocity is not None:
            raise ValueError("stock figures are not supported in v1: velocity is null on every file")
        named = {p.product for p in self.top_products} | {d.product for d in self.biggest_decliners or []}
        if not set(self.suggested_classes) <= named:
            raise ValueError("suggested_classes names a product this block does not name")
        return self


class DimensionChange(ContractModel):
    name: str
    revenue_current: float
    revenue_previous: float
    # Signed share of the total change, not share of revenue. Null when the
    # previous month is incomplete (DimensionBreakdown.contribution_reason).
    contribution_pct: float | None


class DimensionBreakdown(ContractModel):
    country: list[DimensionChange]
    category: list[DimensionChange]
    contribution_reason: str | None

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        _paired_list([member.contribution_pct is None
                      for member in self.country + self.category],
                     self.contribution_reason, "contribution_pct")
        return self


class MetricsContract(ContractFile):
    filename: ClassVar[str | None] = "metrics.json"
    written_by_stage: ClassVar[int] = 2
    # 5 since 2E-e: orders are order ids when order_id is mapped (and its
    # basis is a required field). 3 since 2E-c: a sale row needs a positive amount, new customers exclude
    # histories that open with a refund, RFM ties score alike - orders,
    # buyers, AOV, new customers and RFM scores changed MEANING, and a 2.x
    # and a 3.x file must not be compared silently (Thach). 4 since 2E-c2: a
    # return line needs a negative amount (return_rate) and any return on a
    # customer's first day means they are not new (new_vs_returning). 6 since
    # 2E-f: the first day nets per product (new_vs_returning), exactly one
    # order is F = 1 (RFM), and a header-style receipt's lines are its named
    # customer's (segment money, customer counts). 7 since 2E-g: product units
    # are sale lines, labels the name sale lines carry most, the gap never
    # ranked, and velocity null without stock-in lines. 8 since 2E-h: every
    # day and month on the wall clock as written (UTC before), and
    # undated_lines with its reason. 9 since 2E-e2: an order id checked by
    # date only, and the customer fill, count only with the user's answer in
    # Review (orders and every per-customer figure), and
    # unfilled_receipt_lines with its reason. 10 since 2E-k: a confirmed
    # walk-in placeholder has no customer (placeholder_lines), and the
    # order-id check is judged per receipt (most receipts unnamed, or one
    # customer on most, falls back to the receipt question). 11 since 2E-d2:
    # lines the user classed as not products leave the product tables, fees
    # and adjustments leave revenue, a discount is no return line
    # (core.non_product says what moved). 12 since 2E-l: a charge is no order
    # and no return line (orders, AOV, return rate, units), and pooled items
    # are sales ranked as no product. 13 since 2E-i: customers, order ids,
    # categories and transaction types read what a reader sees (a trailing
    # zero-width space no longer makes a second customer, order or category),
    # and a cell with nothing visible is blank. 14 since 2E-j: a date column
    # can be read day first (the order stage 1 decided), placeholder dates and
    # days the order cannot hold are undated, and a month-grain file compares
    # its last month (`period.month_grain`). 15 since 2E-o: a month-end dated
    # file is month grain too (another month compared), and a day-month-year
    # date is found beside a dotted time or before its time. 16 since 2E-t1:
    # the line taxonomy (docs/LINE_TAXONOMY.md) - `non_product` can carry
    # "gift_card" (a closed enum widened), the one major of the migration;
    # 2E-t2 added its blocks inside it (T1), and a 16.0 file without them is
    # refused as stale.
    supported_major: ClassVar[int] = 16
    stale_major_hint: ClassVar[str] = (
        ": this metrics.json was written by an earlier stage 2 with different "
        "definitions (orders, buyers, AOV, return rate, new customers, RFM "
        "scores, segment names); re-analyse this run")

    period: Period
    core: CoreMetrics
    customers: CustomerMetrics
    products: ProductMetrics
    by_dimension: DimensionBreakdown

    @model_validator(mode="before")
    @classmethod
    def _written_before_the_line_taxonomy(cls, data: Any) -> Any:
        """A 16.0 file written by 2E-t1, before the line taxonomy's blocks:
        told to re-analyse, not handed pydantic's "field required" (2E-t2
        reviews 1 #13, 3 #5). Only a file of this major: any other is told its
        major first (2E-v #8)."""
        core = data.get("core") if isinstance(data, dict) else None
        if major_of(data) != cls.supported_major:
            return data
        if isinstance(core, dict) and "revenue_current" in core and "identity" not in core:
            raise ValueError(BEFORE_THE_LINE_TAXONOMY + cls.stale_major_hint)
        return data

    @model_validator(mode="after")
    def _every_number_json_can_carry(self) -> Self:
        """No figure anywhere in the file is infinite or not a number: JSON
        writes it as null, and a required one makes a file no reader can load.
        A month outside the two compared whose amounts overflow was written so,
        after a 200 (2E-v #1). A NaN is an overflow's trace too - +inf and -inf
        meeting in one segment's average (2E-v review 2 #2)."""
        for path, value in numbers_json_cannot_carry(self.model_dump()):
            raise ValueError(f"{path}: {TOO_LARGE_TO_ADD} ({value}): JSON cannot carry it")
        return self

    @model_validator(mode="after")
    def _the_upload_bounds_the_period(self) -> Self:
        """2E-u6 review 1, #9: lines dated after the upload need the cutoff
        they were judged by, and no date the period covers is after it."""
        cutoff = self.period.upload_cutoff
        if cutoff is None:
            if self.core.future_lines:
                raise ValueError("future_lines counts lines after period.upload_cutoff, which is missing")
            return self
        if self.period.data_end > cutoff:
            raise ValueError(f"period.data_end {self.period.data_end} is after period.upload_cutoff {cutoff}")
        return self

    @model_validator(mode="after")
    def _the_change_is_the_two_months_difference(self) -> Self:
        """16.2: `core.revenue_change` is written whenever the previous month
        is complete - exactly revenue_current - revenue_previous, as stage 2
        computes it - and null with the period's reason otherwise. A file
        before 16.2 carries neither (the report redesign, step 1)."""
        core, period = self.core, self.period
        if core.revenue_change is not None and core.revenue_change != core.revenue_current - core.revenue_previous:
            raise ValueError(f"core.revenue_change {core.revenue_change!r} is not revenue_current - revenue_previous")
        if minor_version(self.schema_version) < (16, 2):
            return self
        if period.previous_complete:
            if core.revenue_change is None or core.revenue_change_reason is not None:
                raise ValueError("a 16.2 file states core.revenue_change, with no reason, when the previous "
                                 "month is complete")
        elif core.revenue_change is not None or core.revenue_change_reason != period.previous_incomplete_reason:
            raise ValueError("core.revenue_change is null with the period's reason when the previous month "
                             "is incomplete")
        return self

    @model_validator(mode="after")
    def _no_comparison_against_an_incomplete_month(self) -> Self:
        """Every field whose only purpose is to compare the two months is
        null when the previous month is incomplete (2E doubt-review F8: the
        per-block pairing alone accepted a percentage beside the flag)."""
        if self.period.previous_complete:
            return self
        # Each comparison says why it is missing, even a list with no members
        # to null (2E doubt-review cycle 2, F7).
        if None in (self.core.revenue_change_pct_reason, self.products.biggest_decliners_reason,
                    self.by_dimension.contribution_reason,
                    self.customers.customers_previous_reason):
            raise ValueError("the previous month is incomplete, so every comparison must carry "
                             "a reason")
        compared = [self.core.revenue_change_pct, self.core.revenue_change, self.products.biggest_decliners]
        compared += [m.contribution_pct for m in self.by_dimension.country + self.by_dimension.category]
        compared += [s.customers_previous for s in self.customers.segments]
        if any(value is not None for value in compared):
            raise ValueError("the previous month is incomplete, so every comparison with it "
                             "must be null")
        return self
