"""metrics.json (docs/CONTRACTS.md section 6). Stage 2 never calls the AI."""

from datetime import date

from pydantic import NonNegativeInt

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


class Period(ContractModel):
    current: YearMonth
    previous: YearMonth
    data_start: date
    data_end: date


class MonthlyRevenue(ContractModel):
    period: YearMonth
    revenue: float


class CoreMetrics(ContractModel):
    revenue_current: float
    revenue_previous: float
    revenue_change_pct: float
    orders_current: NonNegativeInt
    orders_previous: NonNegativeInt
    active_customers_current: NonNegativeInt
    active_customers_previous: NonNegativeInt
    aov_current: float
    aov_previous: float
    return_rate_current: float
    return_rate_previous: float
    revenue_by_month: list[MonthlyRevenue]


class SegmentSummary(ContractModel):
    segment: str
    customers: NonNegativeInt
    revenue_share_pct: float
    avg_monetary: float
    customers_previous: NonNegativeInt


class NewVsReturning(ContractModel):
    new_customers: NonNegativeInt
    returning_customers: NonNegativeInt
    new_revenue: float
    returning_revenue: float


class CustomerMetrics(ContractModel):
    rfm_reference_date: date
    segments: list[SegmentSummary]
    new_vs_returning: NewVsReturning


class Pareto(ContractModel):
    products_for_80pct_revenue: NonNegativeInt
    total_products: NonNegativeInt
    concentration_pct: Percent


class TopProduct(ContractModel):
    product: str
    revenue: float
    units: int


class ProductDecline(ContractModel):
    product: str
    revenue_change_pct: float


class ProductVelocity(ContractModel):
    product: str
    units_per_day: NonNegativeFloat
    days_to_stockout: NonNegativeFloat


class ProductMetrics(ContractModel):
    pareto: Pareto
    top_products: list[TopProduct]
    biggest_decliners: list[ProductDecline]
    velocity: list[ProductVelocity]


class DimensionChange(ContractModel):
    name: str
    revenue_current: float
    revenue_previous: float
    # Signed share of the total change, not share of revenue.
    contribution_pct: float


class DimensionBreakdown(ContractModel):
    country: list[DimensionChange]
    category: list[DimensionChange]


class MetricsContract(ContractFile):
    period: Period
    core: CoreMetrics
    customers: CustomerMetrics
    products: ProductMetrics
    by_dimension: DimensionBreakdown
