"""forecast.json (docs/CONTRACTS.md section 8)."""

from typing import ClassVar, Self

from pydantic import NonNegativeInt, PositiveInt, model_validator

from contracts._base import (
    ContractFile,
    ContractModel,
    NonNegativeFloat,
    UnitInterval,
    YearMonth,
)
from contracts.lines import refuse_non_finite

# SPECS 7.4: fewer complete months than this and there is no forecast - one
# copy for stage 4, this contract and stage 5's page (5B review 1 #14).
MIN_HISTORY_MONTHS = 3


class RevenuePoint(ContractModel):
    period: YearMonth
    point: float
    low: float
    high: float
    confidence: UnitInterval

    @model_validator(mode="after")
    def _point_inside_interval(self) -> Self:
        # Amounts past a float (4A review 1 #6): the user's data, "too large".
        refuse_non_finite("forecast figures", (self.point, self.low, self.high))
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
    # 4A reviews 1 #10 and 2 #13 (the standing rule, CLAUDE.md 3.3a): the
    # complete months the forecast learned from, the compared month included
    # (not diagnosis.json's `frame.history_months`, which leaves it out),
    # and why they start where they do when an earlier stretch with revenue
    # was cut off by a month with none - a closed month or missing data,
    # which the file cannot tell apart. Added in place: no forecast.json has
    # been written yet (CONTRACTS section 10).
    months_used: NonNegativeInt
    history_note: str | None
    # 4A review 3 #7 (the standing rule): why no season is claimed when the
    # months rise or fall steadily through the year - the shape a one-time
    # change of level between the years also leaves; null otherwise.
    season_note: str | None
    # Null with its reason on every file since 2E-t2: stock figures are not
    # supported in v1 (Thach, the line taxonomy's scope cut - v1 analyses
    # sales, not inventory). Changed in place: no forecast.json has been
    # written (CONTRACTS section 10). The shape stays for v2.
    products_at_stockout_risk: list[StockoutRisk] | None
    products_at_stockout_risk_reason: str | None

    @model_validator(mode="after")
    def _a_forecast_or_none(self) -> Self:
        """No forecast on too short a history; otherwise one point per month
        of the horizon, the months consecutive (4A review 1 #12)."""
        # SPECS 7.4: insufficient exactly when fewer than 3 months (4A review 2 #8).
        if self.insufficient_history != (self.months_used < MIN_HISTORY_MONTHS):
            raise ValueError(f"insufficient history means fewer than {MIN_HISTORY_MONTHS} months used")
        if self.insufficient_history:
            if self.revenue or self.horizon_periods:
                raise ValueError("insufficient history: no forecast, horizon 0")
            if self.season_note is not None:
                raise ValueError("insufficient history: no season was measured, so no season note")
            return self
        if not self.revenue or self.horizon_periods != len(self.revenue):
            raise ValueError("one forecast point per month of the horizon")
        for earlier, later in zip(self.revenue, self.revenue[1:]):
            year, month = int(earlier.period[:4]), int(earlier.period[5:])
            following = f"{year + month // 12:04d}-{month % 12 + 1:02d}"
            if later.period != following:
                raise ValueError(f"the forecast months follow each other: {earlier.period} then {later.period}")
        return self

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
    filename: ClassVar[str | None] = "forecast.json"
    written_by_stage: ClassVar[int] = 4
    stale_major_hint: ClassVar[str] = ": this file was written by an earlier stage 4; run the prediction again"
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
