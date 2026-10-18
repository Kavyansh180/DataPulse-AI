from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    """Optional parameters when requesting an AI root-cause analysis."""

    focus_areas: Optional[List[str]] = Field(
        default=None,
        description="Optional list of specific columns, metrics, or issues to prioritize in analysis",
    )
    custom_context: Optional[str] = Field(
        default=None,
        description="Optional domain, pipeline, or ingestion context to provide the diagnostics engine",
    )


class Recommendation(BaseModel):
    """Actionable corrective recommendation with priority and evidence."""

    action: str = Field(
        ...,
        description="Specific corrective or remediation action to address the quality issue",
    )
    priority: str = Field(
        ...,
        description="Remediation priority: 'high', 'medium', or 'low'",
    )
    evidence: str = Field(
        ...,
        description="Empirical profiling metrics or issue observations directly justifying this action",
    )
    trade_offs: Optional[str] = Field(
        default=None,
        description="Trade-offs, potential information loss, or downstream implications of applying this recommendation",
    )


class LikelyCause(BaseModel):
    """Hypothesized root cause explicitly distinguishing hypotheses from proven facts."""

    cause: str = Field(
        ...,
        description="Diagnostic explanation or hypothesized origin of the observed quality degradation",
    )
    is_hypothesis: bool = Field(
        default=True,
        description="Flag explicitly marking this cause as an informed hypothesis rather than verified ground truth",
    )
    supporting_evidence: str = Field(
        ...,
        description="Observed profiling facts, anomaly flags, or statistical metrics supporting this hypothesis",
    )


class RootCauseAnalysisResponse(BaseModel):
    """Validated structured output of AI Root-Cause Analysis."""

    run_id: int = Field(..., description="Target profiling run identifier")
    dataset_id: int = Field(..., description="Parent dataset identifier")
    dataset_name: Optional[str] = Field(default=None, description="Name of the evaluated dataset")
    overall_score: Optional[float] = Field(default=None, description="Overall quality score (0-100)")
    overall_assessment: str = Field(
        ...,
        description="Concise executive assessment and summary of dataset quality health",
    )
    key_findings: List[str] = Field(
        default_factory=list,
        description="Key empirical findings directly grounded in observed profiling metrics and issues",
    )
    likely_causes: List[LikelyCause] = Field(
        default_factory=list,
        description="Hypothesized root causes clearly labeled and supported by evidence",
    )
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="Prioritized corrective remediation actions",
    )
    limitations: List[str] = Field(
        default_factory=list,
        description="Known diagnostic limitations, missing pipeline lineage, or domain uncertainties",
    )
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when the analysis was generated",
    )
