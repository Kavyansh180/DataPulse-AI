import pytest
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.dataset import Dataset, DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.models.audit_log import AuditLog
from app.services.profiling_service import ProfilingService
from app.api.errors import APIError


def test_profiling_execution_and_persistence(db_session: Session):
    """Verify that profiling executes, calculates score, and persists metrics and issues."""
    dataset = Dataset(name="telemetry_logs", source_type="s3")
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0.0",
        storage_uri="s3://test/telemetry.csv",
    )
    db_session.add(version)
    db_session.flush()

    df = pd.DataFrame({
        "device_id": [101, 102, 103, 104, 105],
        "temperature": [22.4, 23.1, 22.8, 23.5, 99.9],  # 99.9 is outlier
        "status": ["OK", "OK", "OK", "OK", "OK"],        # Constant column
    })

    run = ProfilingService.execute_and_persist_profiling(
        db=db_session,
        version=version,
        df=df,
    )

    assert run.status == "completed"
    assert run.completed_at is not None
    assert run.total_rows_profiled == 5
    assert run.quality_score is not None
    assert 0.0 <= run.quality_score <= 100.0

    # Verify metrics persisted
    metrics = db_session.scalars(
        select(QualityMetric).where(QualityMetric.profiling_run_id == run.id)
    ).all()
    assert len(metrics) > 0
    metric_names = [m.metric_name for m in metrics]
    assert "overall_quality_score" in metric_names
    assert "missing_percentage" in metric_names

    # Verify issues persisted
    issues = db_session.scalars(
        select(QualityIssue).where(QualityIssue.dataset_version_id == version.id)
    ).all()
    assert len(issues) > 0

    # Verify AuditLog event recorded
    audit = db_session.scalar(
        select(AuditLog).where(AuditLog.entity_id == str(run.id))
    )
    assert audit is not None
    assert audit.action == "profiling_completed"


def test_failed_profiling_run_records_failure_state(db_session: Session):
    """Verify that an unexpected error during profiling sets status to 'failed' and logs the event."""
    dataset = Dataset(name="failing_dataset", source_type="s3")
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0.0",
        storage_uri="s3://test/fail.csv",
    )
    db_session.add(version)
    db_session.flush()

    # Pass an object that causes an intentional exception during profiling
    with pytest.raises(APIError) as exc_info:
        ProfilingService.execute_and_persist_profiling(
            db=db_session,
            version=version,
            df=None,  # Intentionally triggers error in profiler
        )
    assert exc_info.value.status_code == 500

    # Verify run is recorded as failed in DB
    run = db_session.scalar(
        select(ProfilingRun).where(ProfilingRun.dataset_version_id == version.id)
    )
    assert run is not None
    assert run.status == "failed"
    assert run.completed_at is not None
    assert run.error_message is not None
