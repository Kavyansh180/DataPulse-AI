from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class QualityMetricBase(BaseModel):
    metric_name: str = Field(..., max_length=100, description="Metric name (e.g., null_ratio, distinct_count)")
    column_name: Optional[str] = Field(default=None, max_length=255, description="Target column or null for table-level")
    metric_value: Optional[float] = Field(default=None, description="Computed numerical metric value")
    threshold_value: Optional[float] = Field(default=None, description="Expected threshold for warning/failure")
    is_anomalous: bool = Field(default=False, description="Flag indicating threshold breach or anomaly")
    details: Optional[str] = Field(default=None, description="JSON string or notes with statistical context")


class QualityMetricCreate(QualityMetricBase):
    profiling_run_id: int


class QualityMetricRead(QualityMetricBase):
    id: int
    profiling_run_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProfilingRunBase(BaseModel):
    dataset_version_id: int = Field(..., description="Target dataset version identifier")


class ProfilingRunCreate(ProfilingRunBase):
    pass


class ProfilingRunUpdate(BaseModel):
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_rows_profiled: Optional[int] = None
    quality_score: Optional[float] = None
    summary_stats: Optional[str] = None
    error_message: Optional[str] = None


class ProfilingRunRead(ProfilingRunBase):
    id: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_rows_profiled: Optional[int] = None
    quality_score: Optional[float] = None
    summary_stats: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime
    metrics: List[QualityMetricRead] = []

    model_config = ConfigDict(from_attributes=True)


class ProfilingSummaryResponse(BaseModel):
    run_id: int
    dataset_version_id: int
    status: str
    quality_score: Optional[float] = None
    total_rows_profiled: Optional[int] = None
    total_columns_profiled: Optional[int] = None
    component_scores: Dict[str, float] = Field(default_factory=dict)
    score_explanation: Optional[str] = None
    issues_count: int = 0
    anomalous_metrics_count: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunComparisonResponse(BaseModel):
    dataset_id: int
    run_id_1: int
    run_id_2: int
    previous_score: Optional[float] = None
    current_score: Optional[float] = None
    score_change: Optional[float] = None
    schema_compatible: bool = True
    schema_change_note: Optional[str] = None
    added_columns: List[str] = Field(default_factory=list)
    removed_columns: List[str] = Field(default_factory=list)
    metric_changes: Dict[str, Any] = Field(default_factory=dict)
    new_issues: List[str] = Field(default_factory=list)
    resolved_issues: List[str] = Field(default_factory=list)
