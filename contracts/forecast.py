"""forecast.json (docs/CONTRACTS.md section 8)."""

from typing import ClassVar, Self

from pydantic import NonNegativeInt, PositiveInt, model_validator

from contracts._base import (
    ContractFile,
    ContractModel,
    NonNegativeFloat,
    UnitInterval,
    YearMonth,
    minor_version,
)
from contracts.forecast_actions import ActionsStatus, SuggestedAction, check_actions
from contracts.lines import refuse_non_finite

# SPECS 7.4: fewer complete months than this and there is no forecast - one
# copy for stage 4, this contract and stage 5's page (5B review 1 #14).
MIN_HISTORY_MONTHS = 3
# SPECS 7.5: a season needs this many full years; read from exactly this many
# it carries the two-year note (Thach, 2026-10-01, 4A option b). One copy for
# stage 4 and this model (4A-b review 2 #4).
MIN_SEASON_YEARS = 2
# Thach's "exactly two years" (2026-10-01): the theoretical minimum of two
# cycles, which the note names - kept apart from MIN_SEASON_YEARS so a later
# minimum (8D's option (d)) cannot put "two years" beside three (4A-b review
# 3 #6).
NOTED_SEASON_YEARS = 2


def check_season(months_used: int, insufficient: bool, season_years: int | None, season_note: str | None) -> None:
    """The season rules forecast.json holds and report.json's view of it
    repeats, so a reader of either decides on `season_years` (4A-b review 3
    #4). Raises ValueError."""
    if insufficient:
        if season_note is not None or season_years is not None:
            raise ValueError("insufficient history: no season was measured, so no season and no season note")
        return
    # The full years counted back from the compared month: the history's
    # own (4A-b review 2 #2), never fewer than a season needs.
    if season_years is not None and (season_years < MIN_SEASON_YEARS or season_years != months_used // 12):
        raise ValueError(f"season_years is the full years of the history ({months_used // 12}), "
                         f"at least {MIN_SEASON_YEARS}, or null when no season is claimed")
    # Thach, 2026-10-01 (4A option b): a season read from exactly two years
    # carries its note; from more, none.
    # An empty or blank note is no note: the page and the chart skip it
    # (4A-b review 4 #2).
    if season_years == NOTED_SEASON_YEARS and not (season_note or "").strip():
        raise ValueError("a season claimed from two years carries its note (season_note)")
    if season_years is not None and season_years != NOTED_SEASON_YEARS and season_note is not None:
        raise ValueError("a season claimed from more than two years carries no season note")


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
    # The full years a CLAIMED season was read from, counted back from the
    # compared month (two or more: SPECS 7.5); null when no season is
    # claimed. A consumer decides on this number, never by parsing
    # `method` or `season_note` (CLAUDE.md 3.7; 4A-b review 1 #2).
    season_years: int | None
    # A note on the season reading (the standing rule): why no season is
    # claimed when the months rise or fall steadily through the year - the
    # shape a one-time change of level between the years also leaves (4A
    # review 3 #7), `season_years` null - or that the season claimed rests on
    # exactly two years (Thach, 2026-10-01, 4A option b), `season_years` 2;
    # null otherwise. Since forecast.json 2.0 (its meaning widened: a major).
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
        check_season(self.months_used, self.insufficient_history, self.season_years, self.season_note)
        if self.insufficient_history:
            if self.revenue or self.horizon_periods:
                raise ValueError("insufficient history: no forecast, horizon 0")
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
    # 2 since 4A-b (2026-10-01): `season_note` also notes a season claimed
    # from two years, and `season_years` says how many - a change of meaning,
    # so a 1.x file is refused ("run the prediction again"), never shown
    # without the note (4A-b review 1 #1).
    supported_major: ClassVar[int] = 2
    filename: ClassVar[str | None] = "forecast.json"
    written_by_stage: ClassVar[int] = 4
    stale_major_hint: ClassVar[str] = ": this file was written by an earlier stage 4; run the prediction again"
    # Required but nullable: null means the AI step was unavailable, and a
    # missing key must not be mistaken for that (CONTRACTS.md section 8).
    model_used: str | None
    forecast: ForecastBlock
    recommendations: list[Recommendation] | None
    do_not_do: list[DoNotDo] | None
    # 2.1 (the report redesign, D4; contracts/forecast_actions.py): the
    # structured actions, their state and the model that wrote them. Absent
    # before 2.1; required from it.
    actions: list[SuggestedAction] | None = None
    actions_status: ActionsStatus | None = None
    actions_model: str | None = None

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
        if not all(nulls) and minor_version(self.schema_version) >= (2, 1):
            # The free-text strategy step is removed (Thach, Q53): no AI writes
            # recommendations in v1, and a 2.1 file holds none.
            raise ValueError("a 2.1 forecast holds no AI recommendations: model_used, recommendations and do_not_do "
                             "are null")
        check_actions(self.actions, self.actions_status, self.actions_model, minor_version(self.schema_version))
        return self
