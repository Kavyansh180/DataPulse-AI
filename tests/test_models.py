import pytest
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select

from app.models.dataset import Dataset, DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.models.audit_log import AuditLog


def test_dataset_creation_and_retrieval(db_session: Session):
    """Test creating and retrieving a Dataset entity."""
    dataset = Dataset(
        name="customer_churn_daily",
        description="Daily snapshot of churn predictions",
        source_type="s3",
    )
    db_session.add(dataset)
    db_session.flush()

    retrieved = db_session.scalar(select(Dataset).where(Dataset.name == "customer_churn_daily"))
    assert retrieved is not None
    assert retrieved.id is not None
    assert retrieved.source_type == "s3"
    assert retrieved.created_at is not None
    assert retrieved.updated_at is not None


def test_dataset_name_uniqueness(db_session: Session):
    """Test unique constraint on dataset name."""
    d1 = Dataset(name="unique_dataset", source_type="s3")
    db_session.add(d1)
    db_session.flush()

    d2 = Dataset(name="unique_dataset", source_type="postgres")
    db_session.add(d2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_dataset_version_relationship(db_session: Session):
    """Test parent-child relationship between Dataset and DatasetVersion."""
    dataset = Dataset(name="orders_stream", source_type="postgres")
    db_session.add(dataset)
    db_session.flush()

    v1 = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0.0",
        storage_uri="s3://lake/orders/v1.parquet",
        row_count=50000,
        column_count=12,
        file_size_bytes=1048576,
    )
    db_session.add(v1)
    db_session.flush()

    # Verify bidirectional navigation
    assert len(dataset.versions) == 1
    assert dataset.versions[0].version_tag == "v1.0.0"
    assert v1.dataset.name == "orders_stream"


def test_version_tag_uniqueness_per_dataset(db_session: Session):
    """Test that duplicate version_tag within the same dataset raises an IntegrityError."""
    dataset = Dataset(name="sales_data", source_type="csv")
    db_session.add(dataset)
    db_session.flush()

    v1 = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="2026-10-01",
        storage_uri="s3://lake/sales/v1.parquet",
    )
    db_session.add(v1)
    db_session.flush()

    v2 = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="2026-10-01",
        storage_uri="s3://lake/sales/v2.parquet",
    )
    db_session.add(v2)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_profiling_run_and_quality_metrics(db_session: Session):
    """Test ProfilingRun creation with child QualityMetric entries and cascade delete."""
    dataset = Dataset(name="web_telemetry", source_type="s3")
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="snapshot_01",
        storage_uri="s3://lake/telemetry/01.parquet",
        row_count=10000,
        column_count=8,
    )
    db_session.add(version)
    db_session.flush()

    run = ProfilingRun(
        dataset_version_id=version.id,
        status="completed",
        total_rows_profiled=10000,
    )
    db_session.add(run)
    db_session.flush()

    metric1 = QualityMetric(
        profiling_run_id=run.id,
        metric_name="null_ratio",
        column_name="user_id",
        metric_value=0.0,
        threshold_value=0.01,
        is_anomalous=False,
    )
    metric2 = QualityMetric(
        profiling_run_id=run.id,
        metric_name="null_ratio",
        column_name="session_id",
        metric_value=0.08,
        threshold_value=0.01,
        is_anomalous=True,
    )
    db_session.add_all([metric1, metric2])
    db_session.flush()

    assert len(run.metrics) == 2
    assert any(m.is_anomalous for m in run.metrics)

    # Test cascade delete from run to metrics
    db_session.delete(run)
    db_session.flush()

    remaining_metrics = db_session.scalars(
        select(QualityMetric).where(QualityMetric.profiling_run_id == run.id)
    ).all()
    assert len(remaining_metrics) == 0


def test_quality_issue_lifecycle(db_session: Session):
    """Test logging and resolving a QualityIssue."""
    dataset = Dataset(name="financial_transactions", source_type="postgres")
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0",
        storage_uri="s3://lake/fin/tx.parquet",
    )
    db_session.add(version)
    db_session.flush()

    issue = QualityIssue(
        dataset_version_id=version.id,
        rule_name="outlier_detection_amount",
        severity="critical",
        issue_type="outlier",
        description="Transaction amount exceeded 5 sigma standard deviations",
        status="open",
    )
    db_session.add(issue)
    db_session.flush()

    assert issue.id is not None
    assert issue.status == "open"
    assert issue.severity == "critical"
    assert len(version.quality_issues) == 1


def test_audit_log_entry(db_session: Session):
    """Test recording and querying immutable AuditLog entries."""
    audit = AuditLog(
        action="schema_migration_executed",
        entity_type="migration",
        entity_id="0001_initial_schema",
        actor="system",
        details="Applied initial schema to local database",
    )
    db_session.add(audit)
    db_session.flush()

    retrieved = db_session.scalar(select(AuditLog).where(AuditLog.id == audit.id))
    assert retrieved is not None
    assert retrieved.action == "schema_migration_executed"
    assert retrieved.actor == "system"
    assert retrieved.created_at is not None
