import io
from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException, Query, Body
from sqlalchemy.orm import Session
from sqlalchemy import select
import pandas as pd

from app.core.database import get_db
from app.models.dataset import DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.models.user import User
from app.api.deps import get_current_user
from app.schemas.profiling import (
    ProfilingRunCreate,
    ProfilingRunRead,
    ProfilingSummaryResponse,
    QualityMetricRead,
    RunComparisonResponse,
)
from app.schemas.quality_issue import QualityIssueRead
from app.schemas.ai_analysis import (
    AnalysisRequest,
    RootCauseAnalysisResponse,
)
from app.schemas.remediation import (
    RemediationPreviewRequest,
    RemediationPreviewResponse,
    RemediationApplyRequest,
    RemediationApplyResponse,
)
from app.services.profiling_service import ProfilingService
from app.services.comparison_service import ComparisonService
from app.services.ai_analysis_service import AIAnalysisService
from app.services.remediation_service import RemediationService
from app.services.s3_service import S3Service
from app.services.csv_service import CSVValidationService
from app.api.errors import APIError

router = APIRouter()


def _verify_run_owner(run: Optional[ProfilingRun], current_user: User) -> ProfilingRun:
    """Ensure run exists and its parent dataset is owned by current_user, else 404."""
    if (
        not run
        or not run.dataset_version
        or not run.dataset_version.dataset
        or run.dataset_version.dataset.user_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profiling run not found.",
        )
    return run


@router.post(
    "/runs",
    response_model=ProfilingRunRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start profiling run",
    description="Initiate and execute synchronous data profiling for an existing dataset version snapshot owned by user.",
)
def start_profiling_run(
    payload: ProfilingRunCreate,
    expected_schema: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    version = db.scalar(select(DatasetVersion).where(DatasetVersion.id == payload.dataset_version_id))
    if not version or not version.dataset or version.dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DatasetVersion {payload.dataset_version_id} not found.",
        )

    # Fetch file data from storage URI
    if version.storage_uri.startswith("s3://"):
        file_bytes = S3Service.download_file_bytes(version.storage_uri)
    elif version.storage_uri.startswith("memory://") or version.storage_uri.startswith("local://"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Dataset version was registered without persistent storage artifact.",
        )
    else:
        # Try local path or S3 key
        try:
            file_bytes = S3Service.download_file_bytes(version.storage_uri)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot load dataset file from {version.storage_uri}: {str(exc)}",
            )

    df, _, _ = CSVValidationService.parse_and_validate_csv(file_bytes, f"version_{version.id}.csv")
    schema_dict = None
    if expected_schema:
        import json
        try:
            schema_dict = json.loads(expected_schema)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="expected_schema query param must be valid JSON.",
            )

    run = ProfilingService.execute_and_persist_profiling(
        db=db,
        version=version,
        df=df,
        expected_schema=schema_dict,
    )
    return run


@router.get(
    "/compare",
    response_model=RunComparisonResponse,
    summary="Compare two profiling runs",
    description="Compare historical profiling runs for score progression, schema evolution, and issue resolution.",
)
def compare_runs(
    run_id_1: int = Query(..., description="Baseline or previous run ID"),
    run_id_2: int = Query(..., description="Current or comparison run ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run_1 = _verify_run_owner(ProfilingService.get_run_by_id(db, run_id_1), current_user)
    run_2 = _verify_run_owner(ProfilingService.get_run_by_id(db, run_id_2), current_user)
    return ComparisonService.compare_runs(run_1, run_2)


@router.get(
    "/{run_id}",
    response_model=ProfilingRunRead,
    summary="Get profiling run",
    description="Retrieve profiling run status, execution details, quality score, and metrics.",
)
def get_profiling_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)
    return run


@router.get(
    "/{run_id}/summary",
    response_model=ProfilingSummaryResponse,
    summary="Get quality score and summary",
    description="Retrieve the explainable quality score, component scores, and summary deductions.",
)
def get_run_summary(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)

    import json
    stats = {}
    if run.summary_stats:
        try:
            stats = json.loads(run.summary_stats)
        except Exception:
            pass

    anomalies_count = len([m for m in run.metrics if m.is_anomalous])
    issues_count = len(run.dataset_version.quality_issues) if run.dataset_version else 0

    return ProfilingSummaryResponse(
        run_id=run.id,
        dataset_version_id=run.dataset_version_id,
        status=run.status,
        quality_score=run.quality_score,
        total_rows_profiled=run.total_rows_profiled,
        total_columns_profiled=stats.get("column_count"),
        component_scores=stats.get("component_scores", {}),
        score_explanation=stats.get("explanation"),
        issues_count=issues_count,
        anomalous_metrics_count=anomalies_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get(
    "/{run_id}/metrics",
    response_model=List[QualityMetricRead],
    summary="Get profiling metrics",
    description="Retrieve granular statistical quality metrics, optionally filtered by column name.",
)
def get_run_metrics(
    run_id: int,
    column_name: Optional[str] = Query(None, description="Optional column name filter"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)

    if column_name:
        return [m for m in run.metrics if m.column_name == column_name]
    return run.metrics


@router.get(
    "/{run_id}/issues",
    response_model=List[QualityIssueRead],
    summary="Get quality issues",
    description="Retrieve aggregated quality issues detected during the profiling run.",
)
def get_run_issues(
    run_id: int,
    severity: Optional[str] = Query(None, description="Optional severity filter (low, medium, high, critical)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)

    issues = run.dataset_version.quality_issues if run.dataset_version else []
    if severity:
        return [i for i in issues if i.severity.lower() == severity.lower()]
    return issues


@router.post(
    "/{run_id}/analyze",
    response_model=RootCauseAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="AI root-cause analysis",
    description="Analyze profiling metrics, anomalies, and quality issues using an LLM to generate an explainable diagnosis and prioritized remediation steps.",
)
def analyze_profiling_run(
    run_id: int,
    payload: Optional[AnalysisRequest] = Body(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)
    return AIAnalysisService.analyze_run(
        db=db,
        run_id=run_id,
        request_data=payload,
    )


@router.post(
    "/{run_id}/remediation/preview",
    response_model=RemediationPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview data remediation",
    description="Simulate and preview data quality remediation operations without modifying source data or artifacts.",
)
def preview_remediation(
    run_id: int,
    payload: RemediationPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)
    return RemediationService.preview_remediation(
        db=db,
        run_id=run_id,
        operations=payload.operations,
    )


@router.post(
    "/{run_id}/remediation/apply",
    response_model=RemediationApplyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Apply data remediation & revalidate",
    description="Apply approved remediation operations, save a new immutable CSV artifact, and execute revalidation.",
)
def apply_remediation(
    run_id: int,
    payload: RemediationApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _verify_run_owner(ProfilingService.get_run_by_id(db, run_id), current_user)
    return RemediationService.apply_remediation(
        db=db,
        run_id=run_id,
        preview_id=payload.preview_id,
        operations=payload.operations,
        new_version_tag=payload.new_version_tag,
    )
