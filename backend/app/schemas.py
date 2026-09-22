"""Response bodies of the stage 1 endpoints (SPECS section 8)."""

from typing import Any, Literal

from pydantic import BaseModel, Field

from contracts import CleaningPlanContract, CleaningReportContract, SchemaInferenceContract
from stages.ingest.preview import PreviewResult


class Notice(BaseModel):
    """A SPECS section 10 case that is a 200 with a flag, not an error: the
    request worked and the client must say something plainly to the user.
    Same `code / message / details` shape as an error, so the UI reads both alike."""

    code: Literal["NOT_INVENTORY", "AI_UNAVAILABLE"]
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


class ExecuteResponse(BaseModel):
    run_id: str
    status: Literal["cleaned"]
    report: CleaningReportContract
    notices: list[Notice] = Field(default_factory=list)
