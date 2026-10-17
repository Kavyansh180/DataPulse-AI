from typing import List, Optional
from fastapi import APIRouter, Depends, status, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.database import get_db
from app.models.dataset import Dataset, DatasetVersion
from app.models.user import User
from app.api.deps import get_current_user
from app.services.dataset_service import DatasetService
from app.services.audit_service import AuditService
from app.services.csv_service import CSVValidationService
from app.services.s3_service import S3Service
from app.services.profiling_service import ProfilingService
from app.services.comparison_service import ComparisonService
from app.schemas.dataset import (
    DatasetCreate,
    DatasetRead,
    DatasetDetailRead,
    DatasetVersionCreate,
    DatasetVersionRead,
)
from app.schemas.profiling import ProfilingRunRead, RunComparisonResponse
from app.schemas.remediation import RemediationHistoryItem
from app.services.remediation_service import RemediationService

router = APIRouter()


@router.get(
    "",
    response_model=List[DatasetRead],
    summary="List datasets",
    description="Retrieve a paginated list of registered datasets owned by the authenticated user.",
)
def list_datasets(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return DatasetService.list_datasets(db=db, user_id=current_user.id, skip=skip, limit=limit)


@router.post(
    "",
    response_model=DatasetRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create dataset (metadata only)",
    description="Register a new dataset entry in the monitoring catalog without file upload.",
)
def create_dataset(
    dataset_in: DatasetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = DatasetService.get_by_name(db=db, name=dataset_in.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Dataset with name '{dataset_in.name}' already exists.",
        )

    dataset = DatasetService.create(db=db, dataset_in=dataset_in, user_id=current_user.id)
    AuditService.log_event(
        db=db,
        action="dataset_created",
        entity_type="dataset",
        entity_id=str(dataset.id),
        details=f"Created dataset '{dataset.name}' by user {current_user.email}",
    )
    return dataset


@router.post(
    "/upload",
    response_model=DatasetDetailRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload CSV and profile dataset",
    description="Upload a CSV file, validate structure, store in S3 if configured, and trigger profiling.",
)
async def upload_csv_dataset(
    name: str = Form(..., description="Unique dataset catalog name"),
    description: Optional[str] = Form(None, description="Optional description of dataset"),
    version_tag: Optional[str] = Form(None, description="Optional version identifier (defaults to v1.0.0)"),
    file: UploadFile = File(..., description="CSV file to upload and profile"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Validate file metadata
    CSVValidationService.validate_file_metadata(file.filename, file.content_type)

    # 2. Read bytes into memory bounded by size limits
    content = await file.read()

    # 3. Parse and validate CSV content
    df, row_count, col_count = CSVValidationService.parse_and_validate_csv(content, file.filename or "data.csv")

    # 4. Check if dataset already exists or create new
    dataset = DatasetService.get_by_name(db=db, name=name)
    if not dataset:
        dataset = DatasetService.create(
            db=db,
            dataset_in=DatasetCreate(name=name, description=description, source_type="s3"),
            user_id=current_user.id,
        )
        AuditService.log_event(
            db=db,
            action="dataset_created",
            entity_type="dataset",
            entity_id=str(dataset.id),
            details=f"Created dataset '{dataset.name}' via CSV upload by user {current_user.email}.",
        )
    else:
        # Enforce dataset ownership: unauthorized users cannot append versions to another user's dataset
        if dataset.user_id is not None and dataset.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to append versions to this dataset.",
            )
        elif dataset.user_id is None:
            # Unowned legacy dataset remains protected from modification by ordinary users
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot append versions to unowned system dataset.",
            )

    # 5. Determine storage URI (S3 or safe local/memory key)
    v_tag = version_tag.strip() if version_tag else f"v{len(dataset.versions) + 1}.0.0"

    # Check duplicate version tag
    for v in dataset.versions:
        if v.version_tag == v_tag:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Version '{v_tag}' already exists for dataset '{name}'.",
            )

    safe_object_key = S3Service.generate_safe_object_key(dataset.id, file.filename or "data.csv")
    if S3Service.is_configured():
        storage_uri = S3Service.upload_file_bytes(content, safe_object_key)
    else:
        storage_uri = f"s3://datapulse-local/{safe_object_key}"

    # 6. Create DatasetVersion
    version_in = DatasetVersionCreate(
        dataset_id=dataset.id,
        version_tag=v_tag,
        storage_uri=storage_uri,
        row_count=row_count,
        column_count=col_count,
        file_size_bytes=len(content),
    )
    version = DatasetService.create_version(db=db, version_in=version_in)

    # 7. Execute profiling and persistence
    ProfilingService.execute_and_persist_profiling(
        db=db,
        version=version,
        df=df,
    )

    db.refresh(dataset)
    return dataset


@router.get(
    "/{dataset_id}",
    response_model=DatasetDetailRead,
    summary="Get dataset details",
    description="Retrieve dataset metadata and all associated ingestion versions.",
)
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dataset = DatasetService.get_by_id(db=db, dataset_id=dataset_id)
    if not dataset or dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Dataset with id {dataset_id} not found.",
        )
    return dataset


@router.post(
    "/{dataset_id}/versions",
    response_model=DatasetVersionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create dataset version (metadata only)",
    description="Record a new version snapshot for a given dataset.",
)
def create_dataset_version(
    dataset_id: int,
    version_payload: DatasetVersionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if version_payload.dataset_id != dataset_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mismatched dataset_id in URL path and request body.",
        )

    dataset = DatasetService.get_by_id(db=db, dataset_id=dataset_id)
    if not dataset or dataset.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Parent dataset with id {dataset_id} not found.",
        )

    version = DatasetService.create_version(db=db, version_in=version_payload)
    AuditService.log_event(
        db=db,
        action="version_created",
        entity_type="dataset_version",
        entity_id=str(version.id),
        details=f"Version '{version.version_tag}' created for dataset {dataset_id}",
    )
    return version


@router.get(
    "/{dataset_id}/runs",
    response_model=List[ProfilingRunRead],
    summary="List profiling runs for dataset",
    description="Retrieve previous profiling runs and quality score history for a dataset.",
)
def list_dataset_profiling_runs(
    dataset_id: int,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dataset = DatasetService.get_by_id(db=db, dataset_id=dataset_id)
    if not dataset or dataset.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset {dataset_id} not found.")

    return ProfilingService.list_runs_for_dataset(db=db, dataset_id=dataset_id, skip=skip, limit=limit)


@router.get(
    "/{dataset_id}/compare-runs",
    response_model=RunComparisonResponse,
    summary="Compare dataset runs",
    description="Compare two historical profiling runs for this dataset.",
)
def compare_dataset_runs(
    dataset_id: int,
    run_id_1: int = Query(..., description="First run ID (baseline)"),
    run_id_2: int = Query(..., description="Second run ID (comparison)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dataset = DatasetService.get_by_id(db=db, dataset_id=dataset_id)
    if not dataset or dataset.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset {dataset_id} not found.")

    run_1 = ProfilingService.get_run_by_id(db, run_id_1)
    if not run_1 or not run_1.dataset_version or run_1.dataset_version.dataset_id != dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id_1} not found for this dataset.")

    run_2 = ProfilingService.get_run_by_id(db, run_id_2)
    if not run_2 or not run_2.dataset_version or run_2.dataset_version.dataset_id != dataset_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run {run_id_2} not found for this dataset.")

    return ComparisonService.compare_runs(run_1, run_2)


@router.get(
    "/{dataset_id}/remediation-history",
    response_model=List[RemediationHistoryItem],
    summary="List dataset remediation history",
    description="Retrieve historical data remediation events and improvements for this dataset.",
)
def get_dataset_remediation_history(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    dataset = DatasetService.get_by_id(db=db, dataset_id=dataset_id)
    if not dataset or dataset.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Dataset {dataset_id} not found.")

    return RemediationService.list_dataset_remediation_history(db=db, dataset_id=dataset_id)
