"""Response bodies of the stage 1 endpoints (SPECS section 8)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts import (
    CleaningPlanContract,
    CleaningReportContract,
    DiagnosisContract,
    ForecastContract,
    MetricsContract,
    ReportContract,
    SchemaInferenceContract,
)
from contracts.lines import LineSummary, ReservedRename
from stages.ingest.preview import PreviewResult


class Notice(BaseModel):
    """A SPECS section 10 case that is a 200 with a flag, not an error: the
    request worked and the client must say something plainly to the user.
    Same `code / message / details` shape as an error, so the UI reads both alike."""

    # AI_NOT_ASKED (4C): stage 4 did not ask the AI - the step is switched
    # off, the diagnosis is blocked, or the previous month is incomplete.
    code: Literal["NOT_INVENTORY", "AI_UNAVAILABLE", "AI_NOT_ASKED"]
    message: str
    details: dict[str, Any] | None = None


class AnalyzeSchemaResponse(BaseModel):
    run_id: str
    status: Literal["profiled"]
    # None when the AI produced no accepted answer (notice AI_UNAVAILABLE).
    schema_inference: SchemaInferenceContract | None
    notices: list[Notice] = Field(default_factory=list)


class PlanResponse(BaseModel):
    run_id: str
    status: Literal["profiled", "planned"]
    # None when the AI produced no accepted answer: the user builds the plan by
    # hand from the transform catalog (AI_PIPELINE section 9).
    plan: CleaningPlanContract | None
    notices: list[Notice] = Field(default_factory=list)


class PreviewResponse(BaseModel):
    run_id: str
    preview: PreviewResult


class LineSummaryResponse(BaseModel):
    """Review's whole-file view of the line taxonomy (2E-t3). `summary` is
    None, with `summary_unavailable_reason`, while the plan does not map and
    keep a date, a quantity and a unit price, while the date question is
    open, or when a figure's amounts are too large to add up;
    `reserved_renames` stands either way."""

    run_id: str
    reserved_renames: list[ReservedRename]
    summary: LineSummary | None
    summary_unavailable_reason: str | None


class ExecuteResponse(BaseModel):
    run_id: str
    status: Literal["cleaned"]
    report: CleaningReportContract
    notices: list[Notice] = Field(default_factory=list)


class DiagnoseResponse(BaseModel):
    run_id: str
    status: Literal["analyzed"]
    diagnosis: DiagnosisContract
    # 3G-lite runs no AI step (the designed degraded mode: `ai_findings` and
    # `model_used` null, docs/AI_PIPELINE.md section 9), so nothing is
    # flagged; 3F adds AI_UNAVAILABLE when the narration is tried and fails.
    notices: list[Notice] = Field(default_factory=list)


class PredictResponse(BaseModel):
    run_id: str
    status: Literal["analyzed"]
    forecast: ForecastContract
    # AI_NOT_ASKED or AI_UNAVAILABLE when the recommendations are null: the
    # forecast stands either way (CONTRACTS 8).
    notices: list[Notice] = Field(default_factory=list)


class ReportResponse(BaseModel):
    run_id: str
    status: Literal["analyzed"]
    report: ReportContract
    # Where report.html downloads from (SPECS 8: "report.json + html download url").
    html_url: str
    # Stage 5 calls no AI and has no degraded path: nothing is flagged.
    notices: list[Notice] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    run_id: str
    status: Literal["analyzed"]
    metrics: MetricsContract
    # Stage 2 has no AI and no degraded path (docs/adr/0002): a run that
    # cannot be analyzed is ANALYSIS_FAILED, not a 200 with a notice, so this
    # is always empty. Kept for response-shape consistency with the other
    # stage endpoints.
    notices: list[Notice] = Field(default_factory=list)
