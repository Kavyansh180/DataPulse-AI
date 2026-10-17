from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class RemediationOperation(BaseModel):
    """Specification of a deterministic correction operation to apply to a dataset."""

    operation_type: str = Field(
        ...,
        description="Type of remediation operation: 'fill_missing', 'drop_duplicates', 'trim_whitespace', 'convert_type', or 'cap_outliers'",
    )
    column: Optional[str] = Field(
        default=None,
        description="Target column name for column-specific operations",
    )
    columns: Optional[List[str]] = Field(
        default=None,
        description="List of target columns (e.g. for bulk whitespace trimming)",
    )
    strategy: Optional[str] = Field(
        default=None,
        description="Imputation strategy for fill_missing: 'constant', 'mean', 'median', or 'mode'",
    )
    fill_value: Optional[Any] = Field(
        default=None,
        description="Constant value to impute when strategy='constant'",
    )
    target_type: Optional[str] = Field(
        default=None,
        description="Target data type for convert_type: 'integer', 'float', 'string', or 'date'",
    )
    failure_policy: Optional[str] = Field(
        default="coerce",
        description="Policy for unconvertible values: 'coerce' (set to null) or 'reject' (abort operation)",
    )
    lower_bound: Optional[float] = Field(
        default=None,
        description="Minimum numeric boundary for cap_outliers (values below are clipped to this value)",
    )
    upper_bound: Optional[float] = Field(
        default=None,
        description="Maximum numeric boundary for cap_outliers (values above are clipped to this value)",
    )
    empty_string_to_null: Optional[bool] = Field(
        default=False,
        description="For trim_whitespace, whether whitespace-only or empty strings are normalized to null",
    )


class RemediationPreviewRequest(BaseModel):
    """Request payload to simulate and preview proposed remediation operations."""

    operations: List[RemediationOperation] = Field(
        ...,
        min_length=1,
        description="List of one or more remediation operations to preview",
    )


class SampleDiff(BaseModel):
    """Representative row change demonstrating a before-and-after modification."""

    row_index: int = Field(..., description="Zero-based row index in dataset")
    column: str = Field(..., description="Column modified")
    original_value: Optional[str] = Field(default=None, description="Original raw value string representation")
    corrected_value: Optional[str] = Field(default=None, description="Corrected value string representation")
    operation: str = Field(..., description="Operation responsible for this change")


class OperationPreview(BaseModel):
    """Summary of changes and affected rows for a single operation."""

    operation_type: str = Field(..., description="Operation type")
    column: Optional[str] = Field(default=None, description="Target column, if applicable")
    affected_rows: int = Field(default=0, description="Total rows affected by this operation")
    description: str = Field(..., description="Human-readable description of the simulated change")
    warnings: List[str] = Field(default_factory=list, description="Warnings or potential information loss notices")


class RemediationPreviewResponse(BaseModel):
    """Structured response containing proposed changes and validation preview."""

    preview_id: str = Field(..., description="Cryptographically signed preview identifier binding approval to this run and operations")
    run_id: int = Field(..., description="Source profiling run identifier")
    dataset_id: int = Field(..., description="Source dataset identifier")
    total_rows_before: int = Field(..., description="Original total row count")
    total_rows_after: int = Field(..., description="Projected total row count after remediation")
    operations: List[OperationPreview] = Field(default_factory=list, description="List of operation previews")
    sample_diffs: List[SampleDiff] = Field(default_factory=list, description="Sample of representative row modifications")
    warnings: List[str] = Field(default_factory=list, description="Global warnings or risk notices")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp of preview generation")


class RemediationApplyRequest(BaseModel):
    """Request payload to approve and apply previously previewed remediation operations."""

    preview_id: str = Field(..., description="Signed preview token generated during preview step")
    operations: List[RemediationOperation] = Field(..., min_length=1, description="Exact operations that were previewed")
    new_version_tag: Optional[str] = Field(default=None, description="Custom version tag for the remediated dataset version")


class RemediationApplyResponse(BaseModel):
    """Result of applying approved remediation, saving a new artifact, and re-profiling."""

    source_run_id: int = Field(..., description="Original profiling run identifier")
    new_run_id: int = Field(..., description="New profiling run identifier for remediated dataset")
    dataset_id: int = Field(..., description="Parent dataset identifier")
    new_dataset_version_id: int = Field(..., description="Identifier of the newly created DatasetVersion")
    new_version_tag: str = Field(..., description="Version tag of the remediated dataset snapshot")
    storage_uri: str = Field(..., description="S3 storage URI where the new corrected CSV is saved")
    original_score: float = Field(..., description="Quality score prior to remediation")
    remediated_score: float = Field(..., description="Quality score after remediation")
    score_improvement: float = Field(..., description="Net quality score change (remediated - original)")
    rows_before: int = Field(..., description="Total rows in original dataset")
    rows_after: int = Field(..., description="Total rows in remediated dataset")
    applied_operations_count: int = Field(..., description="Total number of operations executed")
    resolved_issues: List[str] = Field(default_factory=list, description="Quality issues resolved by remediation")
    remaining_issues: List[str] = Field(default_factory=list, description="Quality issues still present after remediation")
    new_issues: List[str] = Field(default_factory=list, description="Newly emerged quality issues or regressions")
    metric_changes: Dict[str, Any] = Field(default_factory=dict, description="Key metric changes (missing %, duplicate %)")
    applied_at: datetime = Field(default_factory=datetime.utcnow, description="Timestamp when remediation was applied")


class RemediationHistoryItem(BaseModel):
    """Historical record of an applied remediation."""

    audit_id: int
    source_run_id: Optional[int] = None
    new_run_id: Optional[int] = None
    dataset_version_id: int
    version_tag: str
    operations_summary: str
    original_score: Optional[float] = None
    remediated_score: Optional[float] = None
    applied_at: datetime
