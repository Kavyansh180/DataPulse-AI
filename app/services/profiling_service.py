import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.dataset import DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.services.profiler_service import ProfilerService, DatasetProfileResult
from app.services.audit_service import AuditService
from app.core.database import _sanitize_db_error
from app.api.errors import APIError

logger = logging.getLogger("datapulse.profiling_service")


class ProfilingService:
    """Service managing database persistence, execution lifecycles, and retrieval of profiling runs."""

    @staticmethod
    def get_run_by_id(db: Session, run_id: int) -> Optional[ProfilingRun]:
        stmt = select(ProfilingRun).where(ProfilingRun.id == run_id)
        return db.scalars(stmt).first()

    @staticmethod
    def list_runs_for_dataset(db: Session, dataset_id: int, skip: int = 0, limit: int = 50) -> List[ProfilingRun]:
        stmt = (
            select(ProfilingRun)
            .join(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(ProfilingRun.id.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(db.scalars(stmt).all())

    @classmethod
    def execute_and_persist_profiling(
        cls,
        db: Session,
        version: DatasetVersion,
        df: Any,
        expected_schema: Optional[Dict[str, Any]] = None,
        run_id: Optional[int] = None,
    ) -> ProfilingRun:
        """Run profiling on DataFrame and persist metrics, issues, score, and audit logs.

        Guarantees that a failed run status is recorded on error rather than left hanging.
        """
        # Create or fetch run entity
        if run_id:
            run = cls.get_run_by_id(db, run_id)
            if not run:
                raise APIError(status_code=404, message=f"Profiling run {run_id} not found.", code="NOT_FOUND")
        else:
            run = ProfilingRun(
                dataset_version_id=version.id,
                status="running",
                started_at=datetime.utcnow(),
            )
            db.add(run)
            db.flush()

        try:
            # 1. Profile with pure ProfilerService
            result: DatasetProfileResult = ProfilerService.profile_dataframe(
                df=df,
                expected_schema=expected_schema,
            )

            # 2. Persist metrics
            # Table-level metrics
            table_metrics = [
                QualityMetric(
                    profiling_run_id=run.id,
                    metric_name="overall_quality_score",
                    column_name=None,
                    metric_value=result.quality_score.score,
                    threshold_value=70.0,
                    is_anomalous=result.quality_score.score < 70.0,
                    details=result.quality_score.explanation,
                ),
                QualityMetric(
                    profiling_run_id=run.id,
                    metric_name="missing_percentage",
                    column_name=None,
                    metric_value=result.missing_percentage,
                    threshold_value=5.0,
                    is_anomalous=result.missing_percentage > 5.0,
                ),
                QualityMetric(
                    profiling_run_id=run.id,
                    metric_name="duplicate_percentage",
                    column_name=None,
                    metric_value=result.duplicate_percentage,
                    threshold_value=1.0,
                    is_anomalous=result.duplicate_percentage > 1.0,
                ),
            ]
            db.add_all(table_metrics)

            # Column-level metrics
            for col_name, prof in result.columns.items():
                col_metrics = [
                    QualityMetric(
                        profiling_run_id=run.id,
                        metric_name="missing_percentage",
                        column_name=col_name,
                        metric_value=prof.missing_percentage,
                        threshold_value=5.0,
                        is_anomalous=prof.missing_percentage > 5.0,
                    ),
                    QualityMetric(
                        profiling_run_id=run.id,
                        metric_name="distinct_count",
                        column_name=col_name,
                        metric_value=float(prof.distinct_count),
                        is_anomalous=False,
                    ),
                ]
                if prof.inferred_type == "numeric" and prof.mean_value is not None:
                    col_metrics.extend([
                        QualityMetric(
                            profiling_run_id=run.id,
                            metric_name="numeric_mean",
                            column_name=col_name,
                            metric_value=prof.mean_value,
                        ),
                        QualityMetric(
                            profiling_run_id=run.id,
                            metric_name="numeric_median",
                            column_name=col_name,
                            metric_value=prof.median_value,
                        ),
                        QualityMetric(
                            profiling_run_id=run.id,
                            metric_name="outlier_count",
                            column_name=col_name,
                            metric_value=float(prof.outlier_count),
                            is_anomalous=prof.outlier_count > 0,
                        ),
                    ])
                db.add_all(col_metrics)

            # 3. Persist Quality Issues linked to the dataset version
            for issue in result.issues:
                issue_record = QualityIssue(
                    dataset_version_id=version.id,
                    rule_name=issue.rule_name,
                    severity=issue.severity,
                    issue_type=issue.issue_type,
                    description=issue.description,
                    status="open",
                )
                db.add(issue_record)

            # 4. Update Run and DatasetVersion metadata
            run.status = "completed"
            run.completed_at = datetime.utcnow()
            run.total_rows_profiled = result.row_count
            run.quality_score = result.quality_score.score
            run.summary_stats = json.dumps({
                "column_names": result.column_names,
                "column_count": result.column_count,
                "row_count": result.row_count,
                "component_scores": result.quality_score.component_scores,
                "penalties": result.quality_score.penalties,
                "explanation": result.quality_score.explanation,
                "issues_count": len(result.issues),
            })

            version.row_count = result.row_count
            version.column_count = result.column_count

            # Audit event
            AuditService.log_event(
                db=db,
                action="profiling_completed",
                entity_type="profiling_run",
                entity_id=str(run.id),
                details=(
                    f"Completed profiling run {run.id}. "
                    f"Score: {result.quality_score.score}/100 across {result.row_count} rows."
                ),
                commit=False,
            )

            db.commit()
            db.refresh(run)
            return run

        except Exception as exc:
            err_msg = _sanitize_db_error(str(exc))
            logger.exception(f"Profiling run failed: {exc}")

            db.rollback()

            # Record failed state safely
            failed_run = ProfilingRun(
                dataset_version_id=version.id,
                status="failed",
                started_at=datetime.utcnow(),
                completed_at=datetime.utcnow(),
                error_message=err_msg,
            )
            db.add(failed_run)
            db.flush()

            AuditService.log_event(
                db=db,
                action="profiling_failed",
                entity_type="profiling_run",
                entity_id=str(failed_run.id),
                details=f"Run failed: {err_msg}",
                commit=False,
            )
            db.commit()
            db.refresh(failed_run)

            raise APIError(
                status_code=500,
                message=f"Profiling execution failed: {err_msg}",
                code="PROFILING_FAILED",
            )
