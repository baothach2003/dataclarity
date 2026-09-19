"""Pydantic models for the stage contract files (docs/CONTRACTS.md).

The only package every stage may import (CLAUDE.md section 3.1).
"""

from contracts.cleaning import CleaningPlanContract, CleaningReportContract
from contracts.diagnosis import DiagnosisContract
from contracts.forecast import ForecastContract
from contracts.metrics import MetricsContract
from contracts.profile import ProfileContract, SchemaInferenceContract
from contracts.report import ReportContract

__all__ = [
    "CleaningPlanContract",
    "CleaningReportContract",
    "DiagnosisContract",
    "ForecastContract",
    "MetricsContract",
    "ProfileContract",
    "ReportContract",
    "SchemaInferenceContract",
]
