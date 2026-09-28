"""forecast.json (docs/CONTRACTS.md section 8)."""

from typing import Self

from pydantic import NonNegativeInt, PositiveInt, model_validator

from contracts._base import (
    ContractFile,
    ContractModel,
    NonNegativeFloat,
    UnitInterval,
    YearMonth,
)


class RevenuePoint(ContractModel):
    period: YearMonth
    point: float
    low: float
    high: float
    confidence: UnitInterval

    @model_validator(mode="after")
    def _point_inside_interval(self) -> Self:
        if not self.low <= self.point <= self.high:
            raise ValueError(
                f"expected low <= point <= high, got "
                f"{self.low} / {self.point} / {self.high}"
            )
        return self


class StockoutRisk(ContractModel):
    product: str
    days_to_stockout: NonNegativeFloat
    suggested_reorder_units: NonNegativeInt


class ForecastBlock(ContractModel):
    """Computed by code in stage 4; the AI never produces it."""

    method: str
    horizon_periods: NonNegativeInt
    revenue: list[RevenuePoint]
    insufficient_history: bool
    # Null with its reason on every file since 2E-t2: stock figures are not
    # supported in v1 (Thach, the line taxonomy's scope cut - v1 analyses
    # sales, not inventory). Changed in place: no forecast.json has been
    # written (CONTRACTS section 10). The shape stays for v2.
    products_at_stockout_risk: list[StockoutRisk] | None
    products_at_stockout_risk_reason: str | None

    @model_validator(mode="after")
    def _no_stock_figure_in_v1(self) -> Self:
        if self.products_at_stockout_risk is not None:
            raise ValueError("stock figures are not supported in v1: products_at_stockout_risk is null")
        if not self.products_at_stockout_risk_reason:
            raise ValueError("products_at_stockout_risk is null, so its reason must say why")
        return self


class Recommendation(ContractModel):
    priority: PositiveInt
    insight: str
    cause: str
    action: str
    expected_impact: str
    how_to_measure: str
    confidence: UnitInterval


class DoNotDo(ContractModel):
    tempting_action: str
    why_wrong_here: str


class ForecastContract(ContractFile):
    # Required but nullable: null means the AI step was unavailable, and a
    # missing key must not be mistaken for that (CONTRACTS.md section 8).
    model_used: str | None
    forecast: ForecastBlock
    recommendations: list[Recommendation] | None
    do_not_do: list[DoNotDo] | None

    @model_validator(mode="after")
    def _ai_blocks_all_or_nothing(self) -> Self:
        nulls = [
            self.model_used is None,
            self.recommendations is None,
            self.do_not_do is None,
        ]
        if any(nulls) and not all(nulls):
            raise ValueError(
                "model_used, recommendations and do_not_do must be "
                "all null or all filled"
            )
        return self
