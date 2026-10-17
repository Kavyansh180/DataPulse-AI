import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import get_settings
from app.models.dataset import Dataset, DatasetVersion
from app.models.profiling import ProfilingRun
from app.models.audit_log import AuditLog
from app.schemas.remediation import (
    OperationPreview,
    RemediationApplyResponse,
    RemediationHistoryItem,
    RemediationOperation,
    RemediationPreviewResponse,
    SampleDiff,
)
from app.services.s3_service import S3Service
from app.services.csv_service import CSVValidationService
from app.services.profiling_service import ProfilingService
from app.services.comparison_service import ComparisonService
from app.services.audit_service import AuditService
from app.services.remediation_engine import RemediationEngine
from app.api.errors import APIError

logger = logging.getLogger("datapulse.remediation")


class RemediationService(RemediationEngine):
    """Service providing safe, user-controlled data remediation, preview generation, and revalidation."""

    @classmethod
    def load_run_dataframe(cls, run: ProfilingRun) -> Tuple[pd.DataFrame, bytes]:
        """Download raw CSV bytes from storage and parse into a DataFrame without modifying storage."""
        version = run.dataset_version
        if not version or not version.storage_uri:
            raise APIError(
                status_code=400,
                message=f"Profiling run #{run.id} does not have an associated storage URI.",
                code="STORAGE_URI_MISSING",
            )

        storage_uri = version.storage_uri

        # Handle S3 storage
        if storage_uri.startswith("s3://") or not storage_uri.startswith("memory://"):
            try:
                file_bytes = S3Service.download_file_bytes(storage_uri)
            except APIError:
                raise
            except Exception as exc:
                raise APIError(
                    status_code=400,
                    message=f"Cannot download source CSV from {storage_uri}: {exc}",
                    code="DOWNLOAD_FAILED",
                )
        else:
            raise APIError(
                status_code=400,
                message="Dataset version was registered without persistent storage artifact.",
                code="STORAGE_NOT_PERSISTENT",
            )

        df, _, _ = CSVValidationService.parse_and_validate_csv(file_bytes, f"version_{version.id}.csv")
        return df, file_bytes

    # simulate_operations is inherited from RemediationEngine
    @classmethod
    def preview_remediation(
        cls,
        db: Session,
        run_id: int,
        operations: List[RemediationOperation],
    ) -> RemediationPreviewResponse:
        """Simulate and preview remediation operations without altering stored artifacts or database state."""
        run = ProfilingService.get_run_by_id(db, run_id)
        if not run:
            raise APIError(status_code=404, message=f"Profiling run #{run_id} not found.", code="NOT_FOUND")

        if run.status != "completed":
            raise APIError(
                status_code=400,
                message=f"Profiling run #{run_id} has status '{run.status}'. Only completed runs can be remediated.",
                code="RUN_NOT_COMPLETED",
            )

        # Load DataFrame from storage artifact
        df, _ = cls.load_run_dataframe(run)

        # Simulate operations on DataFrame copy
        simulated_df, op_previews, sample_diffs, warnings = cls.simulate_operations(df, operations)

        preview_token = cls.generate_preview_token(run.id, operations)
        dataset_id = run.dataset_version.dataset_id if run.dataset_version else 0

        return RemediationPreviewResponse(
            preview_id=preview_token,
            run_id=run.id,
            dataset_id=dataset_id,
            total_rows_before=len(df),
            total_rows_after=len(simulated_df),
            operations=op_previews,
            sample_diffs=sample_diffs,
            warnings=warnings,
            created_at=datetime.utcnow(),
        )

    @classmethod
    def apply_remediation(
        cls,
        db: Session,
        run_id: int,
        preview_id: str,
        operations: List[RemediationOperation],
        new_version_tag: Optional[str] = None,
    ) -> RemediationApplyResponse:
        """Apply approved remediation, store the corrected CSV as a new S3 artifact, and revalidate."""
        # 1. Verify preview token
        cls.verify_preview_token(token=preview_id, run_id=run_id, operations=operations)

        # 2. Verify run state
        source_run = ProfilingService.get_run_by_id(db, run_id)
        if not source_run:
            raise APIError(status_code=404, message=f"Profiling run #{run_id} not found.", code="NOT_FOUND")

        if source_run.status != "completed":
            raise APIError(
                status_code=400,
                message=f"Profiling run #{run_id} has status '{source_run.status}'. Only completed runs can be remediated.",
                code="RUN_NOT_COMPLETED",
            )

        source_version = source_run.dataset_version
        dataset = source_version.dataset if source_version else None
        if not dataset:
            raise APIError(status_code=404, message="Associated dataset not found.", code="DATASET_NOT_FOUND")

        # 3. Load source data
        df_source, _ = cls.load_run_dataframe(source_run)

        # 4. Apply operations to create remediated DataFrame
        df_corrected, op_previews, _, _ = cls.simulate_operations(df_source, operations)

        # 5. Export corrected CSV bytes
        corrected_csv_bytes = df_corrected.to_csv(index=False).encode("utf-8")

        # 6. Upload corrected CSV to Amazon S3 (Never overwrite original!)
        settings = get_settings()
        clean_tag = new_version_tag or f"v{source_version.version_tag}_remediated_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        safe_key = S3Service.generate_safe_object_key(dataset.id, f"{clean_tag}.csv")

        # Upload to S3 (raises 503 if S3 not configured)
        S3Service.upload_file_bytes(corrected_csv_bytes, safe_key, content_type="text/csv")
        storage_uri = f"s3://{settings.S3_BUCKET_NAME}/{safe_key}" if settings.S3_BUCKET_NAME else f"s3://datapulse/{safe_key}"

        # 7. Create new immutable DatasetVersion entity
        new_version = DatasetVersion(
            dataset_id=dataset.id,
            version_tag=clean_tag,
            storage_uri=storage_uri,
            row_count=len(df_corrected),
            column_count=len(df_corrected.columns),
            file_size_bytes=len(corrected_csv_bytes),
        )
        db.add(new_version)
        db.flush()

        # 8. Revalidate by executing existing profiler on new version
        new_run = ProfilingService.execute_and_persist_profiling(
            db=db,
            version=new_version,
            df=df_corrected,
        )

        # 9. Historical comparison between source run and remediated run
        comparison = ComparisonService.compare_runs(source_run, new_run)

        # 10. Audit log entry capturing operations and improvement
        orig_score = float(source_run.quality_score or 0.0)
        new_score = float(new_run.quality_score or 0.0)
        score_diff = round(new_score - orig_score, 2)

        ops_summary = "; ".join([p.description for p in op_previews])
        AuditService.log_event(
            db=db,
            action="remediation_applied",
            entity_type="dataset_version",
            entity_id=str(new_version.id),
            details=json.dumps({
                "source_run_id": source_run.id,
                "new_run_id": new_run.id,
                "dataset_id": dataset.id,
                "original_score": orig_score,
                "remediated_score": new_score,
                "score_improvement": score_diff,
                "operations_count": len(operations),
                "operations": [op.model_dump(exclude_none=True) for op in operations],
                "operations_summary": ops_summary,
            }),
            commit=False,
        )

        db.commit()
        db.refresh(new_run)
        db.refresh(new_version)

        # Categorize remaining issues from new run
        remaining_issues = [
            f"[{i.severity.upper()}] {i.rule_name}: {i.description}"
            for i in new_version.quality_issues
        ]

        return RemediationApplyResponse(
            source_run_id=source_run.id,
            new_run_id=new_run.id,
            dataset_id=dataset.id,
            new_dataset_version_id=new_version.id,
            new_version_tag=new_version.version_tag,
            storage_uri=storage_uri,
            original_score=orig_score,
            remediated_score=new_score,
            score_improvement=score_diff,
            rows_before=len(df_source),
            rows_after=len(df_corrected),
            applied_operations_count=len(operations),
            resolved_issues=comparison.resolved_issues,
            remaining_issues=remaining_issues,
            new_issues=comparison.new_issues,
            metric_changes=comparison.metric_changes,
            applied_at=datetime.utcnow(),
        )

    @classmethod
    def list_dataset_remediation_history(
        cls,
        db: Session,
        dataset_id: int,
    ) -> List[RemediationHistoryItem]:
        """Fetch audit log history of applied remediations for a dataset."""
        # Find all versions belonging to this dataset
        stmt_versions = select(DatasetVersion.id, DatasetVersion.version_tag).where(DatasetVersion.dataset_id == dataset_id)
        version_map = {row[0]: row[1] for row in db.execute(stmt_versions).all()}

        if not version_map:
            return []

        # Find audit logs for these versions
        stmt_audits = (
            select(AuditLog)
            .where(
                AuditLog.action == "remediation_applied",
                AuditLog.entity_type == "dataset_version",
            )
            .order_by(AuditLog.created_at.desc())
        )
        logs = db.scalars(stmt_audits).all()

        history_items: List[RemediationHistoryItem] = []
        for log in logs:
            try:
                v_id = int(log.entity_id) if log.entity_id else 0
            except ValueError:
                continue

            if v_id not in version_map:
                continue

            # Parse details JSON
            details = {}
            if log.details:
                try:
                    details = json.loads(log.details)
                except Exception:
                    pass

            history_items.append(
                RemediationHistoryItem(
                    audit_id=log.id,
                    source_run_id=details.get("source_run_id"),
                    new_run_id=details.get("new_run_id"),
                    dataset_version_id=v_id,
                    version_tag=version_map.get(v_id, f"v{v_id}"),
                    operations_summary=details.get("operations_summary", "Remediation applied"),
                    original_score=details.get("original_score"),
                    remediated_score=details.get("remediated_score"),
                    applied_at=log.created_at,
                )
            )

        return history_items
