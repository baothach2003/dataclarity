"""report.json, the data layer of stage 5 (docs/CONTRACTS.md section 9)."""

from typing import Any, Self

from pydantic import NonNegativeInt, model_validator

from contracts._base import ContractFile, ContractModel


class DataQuality(ContractModel):
    rows_in: NonNegativeInt
    rows_out: NonNegativeInt
    issues_fixed: NonNegativeInt
    warnings: NonNegativeInt


class ChartSeries(ContractModel):
    name: str
    x: list[str]
    y: list[float]

    @model_validator(mode="after")
    def _points_pair_up(self) -> Self:
        if len(self.x) != len(self.y):
            raise ValueError(
                f"x and y must have the same length, got {len(self.x)} and {len(self.y)}"
            )
        return self


class Chart(ContractModel):
    id: str
    type: str
    title: str
    series: list[ChartSeries]


class Provenance(ContractModel):
    stages_run: list[str]
    ai_calls: NonNegativeInt
    models_used: list[str]


class ReportContract(ContractFile):
    run_id: str
    source_file: str
    data_quality: DataQuality
    # CONTRACTS.md section 9 only says "selected fields from" the earlier
    # contracts. Their real structure is defined in Phase 5A through the
    # section 10 change policy, not guessed here.
    layer_1_numbers: dict[str, Any]
    layer_2_causes: dict[str, Any]
    layer_3_actions: dict[str, Any]
    charts: list[Chart]
    provenance: Provenance
