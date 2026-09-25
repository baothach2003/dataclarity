"""metrics.json (docs/CONTRACTS.md section 6). Stage 2 never calls the AI."""

from datetime import date
from typing import ClassVar, Literal, Self

from pydantic import NonNegativeInt, model_validator

from contracts._base import (
    ContractFile,
    ContractModel,
    NonNegativeFloat,
    Percent,
    YearMonth,
)

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

    @model_validator(mode="after")
    def _reason_when_incomplete(self) -> Self:
        _paired(not self.previous_complete, self.previous_incomplete_reason,
                "the previous month as a base")
        return self


class MonthlyRevenue(ContractModel):
    period: YearMonth
    revenue: float


class CoreMetrics(ContractModel):
    revenue_current: float
    revenue_previous: float
    revenue_change_pct: float | None
    revenue_change_pct_reason: str | None
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

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
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


class CustomerMetrics(ContractModel):
    rfm_reference_date: date
    segments: list[SegmentSummary]
    new_vs_returning: NewVsReturning
    customers_previous_reason: str | None
    revenue_share_reason: str | None

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
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
    days_to_stockout: NonNegativeFloat


class ProductMetrics(ContractModel):
    pareto: Pareto
    top_products: list[TopProduct]
    biggest_decliners: list[ProductDecline] | None
    biggest_decliners_reason: str | None
    velocity: list[ProductVelocity]

    @model_validator(mode="after")
    def _reason_when_null(self) -> Self:
        _paired(self.biggest_decliners is None, self.biggest_decliners_reason,
                "biggest_decliners")
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
    # 5 since 2E-e: orders are order ids when order_id is mapped (and its
    # basis is a required field). 3 since 2E-c: a sale row needs a positive amount, new customers exclude
    # histories that open with a refund, RFM ties score alike - orders,
    # buyers, AOV, new customers and RFM scores changed MEANING, and a 2.x
    # and a 3.x file must not be compared silently (Thach). 4 since 2E-c2: a
    # return line needs a negative amount (return_rate) and any return on a
    # customer's first day means they are not new (new_vs_returning). 6 since
    # 2E-f: the first day nets per product (new_vs_returning), exactly one
    # order is F = 1 (RFM), and a header-style receipt's lines are its named
    # customer's (segment money, customer counts).
    supported_major: ClassVar[int] = 6
    stale_major_hint: ClassVar[str] = (
        ": this metrics.json was written by an earlier stage 2 with different "
        "definitions (orders, buyers, AOV, return rate, new customers, RFM "
        "scores, segment names); re-analyse this run")

    period: Period
    core: CoreMetrics
    customers: CustomerMetrics
    products: ProductMetrics
    by_dimension: DimensionBreakdown

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
        compared = [self.core.revenue_change_pct, self.products.biggest_decliners]
        compared += [m.contribution_pct for m in self.by_dimension.country + self.by_dimension.category]
        compared += [s.customers_previous for s in self.customers.segments]
        if any(value is not None for value in compared):
            raise ValueError("the previous month is incomplete, so every comparison with it "
                             "must be null")
        return self
