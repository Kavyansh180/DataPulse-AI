from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class QualityIssueBase(BaseModel):
    rule_name: str = Field(..., max_length=150, description="Rule that was breached")
    severity: str = Field(default="medium", max_length=50, description="Severity: low, medium, high, critical")
    issue_type: str = Field(..., max_length=100, description="Category: missing_values, schema_drift, outlier, etc.")
    description: str = Field(..., description="Actionable summary of the quality issue")
    status: str = Field(default="open", max_length=50, description="Status: open, acknowledged, resolved, ignored")


class QualityIssueCreate(QualityIssueBase):
    dataset_version_id: int = Field(..., description="Target dataset version identifier")


class QualityIssueUpdate(BaseModel):
    severity: Optional[str] = None
    status: Optional[str] = None
    resolved_at: Optional[datetime] = None


class QualityIssueRead(QualityIssueBase):
    id: int
    dataset_version_id: int
    created_at: datetime
    resolved_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)
