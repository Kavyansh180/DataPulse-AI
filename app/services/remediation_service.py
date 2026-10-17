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
from app.api.errors import APIError

logger = logging.getLogger("datapulse.remediation")


class RemediationService:
    """Service providing safe, user-controlled data remediation, preview generation, and revalidation."""

    ALLOWED_OPERATIONS = {
        "fill_missing",
        "drop_duplicates",
        "trim_whitespace",
        "convert_type",
        "cap_outliers",
    }

    ALLOWED_TARGET_TYPES = {"integer", "float", "string", "date"}

    @classmethod
    def generate_preview_token(cls, run_id: int, operations: List[RemediationOperation]) -> str:
        """Create a deterministic, cryptographic token binding the preview to the exact run and operations."""
        canonical_ops = [op.model_dump(exclude_none=True) for op in operations]
        payload = json.dumps({"run_id": run_id, "operations": canonical_ops}, sort_keys=True)
        sig = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
        return f"prev_{run_id}_{sig}"

    @classmethod
    def verify_preview_token(cls, token: str, run_id: int, operations: List[RemediationOperation]) -> None:
        """Verify that the approval token strictly matches the requested run and operations."""
        expected_token = cls.generate_preview_token(run_id, operations)
        if not hmac.compare_digest(token, expected_token):
            raise APIError(
                status_code=400,
                message=(
                    f"Preview token validation failed. The provided preview_id does not match "
                    f"the operations or source profiling run #{run_id}."
                ),
                code="PREVIEW_MISMATCH",
            )

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

    @classmethod
    def simulate_operations(
        cls,
        df: pd.DataFrame,
        operations: List[RemediationOperation],
    ) -> Tuple[pd.DataFrame, List[OperationPreview], List[SampleDiff], List[str]]:
        """Simulate remediation operations on a DataFrame copy, collecting metrics and sample diffs."""
        # Deep copy to guarantee no modification of input data
        working_df = df.copy()
        op_previews: List[OperationPreview] = []
        sample_diffs: List[SampleDiff] = []
        global_warnings: List[str] = []

        existing_columns = set(working_df.columns)

        for op_idx, op in enumerate(operations, 1):
            if op.operation_type not in cls.ALLOWED_OPERATIONS:
                raise APIError(
                    status_code=400,
                    message=f"Unsupported operation_type '{op.operation_type}'. Permitted: {sorted(list(cls.ALLOWED_OPERATIONS))}",
                    code="INVALID_OPERATION",
                )

            # -------------------------------------------------------------
            # A. Missing Values Imputation
            # -------------------------------------------------------------
            if op.operation_type == "fill_missing":
                col = op.column
                if not col or col not in existing_columns:
                    raise APIError(
                        status_code=400,
                        message=f"Target column '{col}' for fill_missing not found in dataset.",
                        code="COLUMN_NOT_FOUND",
                    )

                strategy = (op.strategy or "").lower()
                if strategy not in ("constant", "mean", "median", "mode"):
                    raise APIError(
                        status_code=400,
                        message=f"Invalid strategy '{op.strategy}' for fill_missing. Allowed: 'constant', 'mean', 'median', 'mode'.",
                        code="INVALID_STRATEGY",
                    )

                is_numeric = pd.api.types.is_numeric_dtype(working_df[col])
                null_mask = working_df[col].isna()
                affected_count = int(null_mask.sum())
                op_warnings: List[str] = []

                if affected_count == 0:
                    op_previews.append(
                        OperationPreview(
                            operation_type="fill_missing",
                            column=col,
                            affected_rows=0,
                            description=f"No missing values in '{col}'. Left unchanged.",
                        )
                    )
                    continue

                fill_value = None
                if strategy == "constant":
                    if op.fill_value is None:
                        raise APIError(
                            status_code=400,
                            message=f"fill_value must be provided when strategy='constant' for column '{col}'.",
                            code="MISSING_PARAMETER",
                        )
                    if is_numeric:
                        try:
                            fill_value = float(op.fill_value) if "." in str(op.fill_value) else int(op.fill_value)
                        except (ValueError, TypeError):
                            raise APIError(
                                status_code=400,
                                message=f"Constant fill_value '{op.fill_value}' is incompatible with numeric column '{col}'.",
                                code="TYPE_INCOMPATIBILITY",
                            )
                    else:
                        fill_value = str(op.fill_value)

                elif strategy in ("mean", "median"):
                    if not is_numeric:
                        raise APIError(
                            status_code=400,
                            message=f"Cannot compute {strategy} on non-numeric column '{col}'.",
                            code="TYPE_INCOMPATIBILITY",
                        )
                    non_nulls = working_df[col].dropna()
                    if non_nulls.empty:
                        raise APIError(
                            status_code=400,
                            message=f"Cannot compute {strategy} for column '{col}' because all values are missing.",
                            code="ALL_NULL_COLUMN",
                        )
                    if strategy == "mean":
                        fill_value = round(float(non_nulls.mean()), 4)
                    else:
                        fill_value = round(float(non_nulls.median()), 4)

                elif strategy == "mode":
                    non_nulls = working_df[col].dropna()
                    if non_nulls.empty:
                        raise APIError(
                            status_code=400,
                            message=f"Cannot compute mode for column '{col}' because all values are missing.",
                            code="ALL_NULL_COLUMN",
                        )
                    modes = non_nulls.mode()
                    fill_value = modes.iloc[0]

                # Collect sample diffs
                null_indices = working_df.index[null_mask][:5]
                for idx in null_indices:
                    sample_diffs.append(
                        SampleDiff(
                            row_index=int(idx),
                            column=col,
                            original_value="<NULL>",
                            corrected_value=str(fill_value),
                            operation=f"fill_missing ({strategy})",
                        )
                    )

                working_df[col] = working_df[col].fillna(fill_value)

                op_previews.append(
                    OperationPreview(
                        operation_type="fill_missing",
                        column=col,
                        affected_rows=affected_count,
                        description=f"Replaced {affected_count} missing values in '{col}' using {strategy} value: {fill_value}.",
                        warnings=op_warnings,
                    )
                )

            # -------------------------------------------------------------
            # B. Duplicate Rows Removal
            # -------------------------------------------------------------
            elif op.operation_type == "drop_duplicates":
                dup_mask = working_df.duplicated(keep="first")
                dup_count = int(dup_mask.sum())

                if dup_count > 0:
                    dup_indices = working_df.index[dup_mask][:5]
                    for idx in dup_indices:
                        sample_diffs.append(
                            SampleDiff(
                                row_index=int(idx),
                                column="[ALL_COLUMNS]",
                                original_value="Duplicate Row",
                                corrected_value="<DROPPED>",
                                operation="drop_duplicates (preserved first occurrence)",
                            )
                        )
                    working_df = working_df.drop_duplicates(keep="first").reset_index(drop=True)

                op_previews.append(
                    OperationPreview(
                        operation_type="drop_duplicates",
                        column=None,
                        affected_rows=dup_count,
                        description=f"Removed {dup_count} duplicate rows (preserving first occurrence).",
                    )
                )

            # -------------------------------------------------------------
            # C. Whitespace and Text Normalization
            # -------------------------------------------------------------
            elif op.operation_type == "trim_whitespace":
                target_cols = op.columns or ([op.column] if op.column else [])
                if not target_cols:
                    # Target all object/string columns by default
                    target_cols = [
                        c for c in working_df.columns
                        if pd.api.types.is_string_dtype(working_df[c]) or working_df[c].dtype == object
                    ]

                for col in target_cols:
                    if col not in existing_columns:
                        raise APIError(
                            status_code=400,
                            message=f"Target column '{col}' for trim_whitespace not found in dataset.",
                            code="COLUMN_NOT_FOUND",
                        )

                    series = working_df[col]
                    non_null_mask = series.notna()
                    trimmed_count = 0
                    empty_norm_count = 0

                    if non_null_mask.any():
                        str_series = series[non_null_mask].astype(str)
                        trimmed = str_series.str.strip()

                        # Detect diffs
                        changed_mask = str_series != trimmed
                        trimmed_count = int(changed_mask.sum())

                        for idx in str_series.index[changed_mask][:5]:
                            sample_diffs.append(
                                SampleDiff(
                                    row_index=int(idx),
                                    column=col,
                                    original_value=repr(str_series.loc[idx]),
                                    corrected_value=repr(trimmed.loc[idx]),
                                    operation="trim_whitespace",
                                )
                            )

                        working_df.loc[non_null_mask, col] = trimmed

                        # Empty string normalization if requested
                        if op.empty_string_to_null:
                            empty_mask = working_df[col] == ""
                            empty_norm_count = int(empty_mask.sum())
                            if empty_norm_count > 0:
                                for idx in working_df.index[empty_mask][:5]:
                                    sample_diffs.append(
                                        SampleDiff(
                                            row_index=int(idx),
                                            column=col,
                                            original_value='""',
                                            corrected_value="<NULL>",
                                            operation="trim_whitespace (empty_to_null)",
                                        )
                                    )
                                working_df.loc[empty_mask, col] = np.nan

                    desc = f"Trimmed whitespace in '{col}' across {trimmed_count} values."
                    if op.empty_string_to_null:
                        desc += f" Normalized {empty_norm_count} empty strings to NULL."

                    op_previews.append(
                        OperationPreview(
                            operation_type="trim_whitespace",
                            column=col,
                            affected_rows=trimmed_count + empty_norm_count,
                            description=desc,
                        )
                    )

            # -------------------------------------------------------------
            # D. Data Type Corrections
            # -------------------------------------------------------------
            elif op.operation_type == "convert_type":
                col = op.column
                if not col or col not in existing_columns:
                    raise APIError(
                        status_code=400,
                        message=f"Target column '{col}' for convert_type not found in dataset.",
                        code="COLUMN_NOT_FOUND",
                    )

                target_type = (op.target_type or "").lower()
                if target_type not in cls.ALLOWED_TARGET_TYPES:
                    raise APIError(
                        status_code=400,
                        message=f"Invalid target_type '{op.target_type}'. Allowed: {sorted(list(cls.ALLOWED_TARGET_TYPES))}",
                        code="INVALID_TARGET_TYPE",
                    )

                policy = (op.failure_policy or "coerce").lower()
                if policy not in ("reject", "coerce"):
                    raise APIError(
                        status_code=400,
                        message="failure_policy must be 'reject' or 'coerce'.",
                        code="INVALID_POLICY",
                    )

                series = working_df[col]
                non_null_mask = series.notna()
                failed_mask = pd.Series(False, index=working_df.index)
                converted_series = None
                op_warnings = []

                if target_type == "integer":
                    parsed = pd.to_numeric(series, errors="coerce")
                    # Failed if not null originally but parsed is NaN or has non-zero fractional part
                    is_integer_val = parsed.notna() & (parsed % 1 == 0)
                    failed_mask = non_null_mask & (~is_integer_val)
                    converted_series = parsed.astype("Int64")

                elif target_type == "float":
                    parsed = pd.to_numeric(series, errors="coerce")
                    failed_mask = non_null_mask & parsed.isna()
                    converted_series = parsed.astype(float)

                elif target_type == "date":
                    parsed = pd.to_datetime(series, errors="coerce")
                    failed_mask = non_null_mask & parsed.isna()
                    converted_series = parsed.dt.strftime("%Y-%m-%d")

                elif target_type == "string":
                    converted_series = series.astype(str)
                    converted_series.loc[~non_null_mask] = np.nan

                failed_count = int(failed_mask.sum())

                if failed_count > 0:
                    if policy == "reject":
                        sample_failed = working_df.loc[failed_mask, col].head(3).tolist()
                        raise APIError(
                            status_code=400,
                            message=(
                                f"Conversion of column '{col}' to {target_type} rejected: "
                                f"{failed_count} values cannot be converted. Sample values: {sample_failed}"
                            ),
                            code="CONVERSION_FAILED",
                        )
                    else:
                        op_warnings.append(
                            f"{failed_count} unparseable values in '{col}' were coerced to NULL to prevent data corruption."
                        )
                        for idx in working_df.index[failed_mask][:5]:
                            sample_diffs.append(
                                SampleDiff(
                                    row_index=int(idx),
                                    column=col,
                                    original_value=str(working_df.loc[idx, col]),
                                    corrected_value="<NULL>",
                                    operation=f"convert_type ({target_type} coerced)",
                                )
                            )

                working_df[col] = converted_series

                op_previews.append(
                    OperationPreview(
                        operation_type="convert_type",
                        column=col,
                        affected_rows=int(non_null_mask.sum()),
                        description=f"Converted column '{col}' to {target_type} (coerced {failed_count} invalid values).",
                        warnings=op_warnings,
                    )
                )

            # -------------------------------------------------------------
            # E. Outliers Capping
            # -------------------------------------------------------------
            elif op.operation_type == "cap_outliers":
                col = op.column
                if not col or col not in existing_columns:
                    raise APIError(
                        status_code=400,
                        message=f"Target column '{col}' for cap_outliers not found in dataset.",
                        code="COLUMN_NOT_FOUND",
                    )

                if not pd.api.types.is_numeric_dtype(working_df[col]):
                    raise APIError(
                        status_code=400,
                        message=f"Cannot cap outliers on non-numeric column '{col}'.",
                        code="TYPE_INCOMPATIBILITY",
                    )

                if op.lower_bound is None and op.upper_bound is None:
                    raise APIError(
                        status_code=400,
                        message=f"At least one of lower_bound or upper_bound must be specified for cap_outliers on '{col}'.",
                        code="MISSING_PARAMETER",
                    )

                if (
                    op.lower_bound is not None
                    and op.upper_bound is not None
                    and op.lower_bound > op.upper_bound
                ):
                    raise APIError(
                        status_code=400,
                        message=f"lower_bound ({op.lower_bound}) cannot be greater than upper_bound ({op.upper_bound}).",
                        code="INVALID_BOUNDS",
                    )

                series = working_df[col]
                capped_count = 0
                lower_count = 0
                upper_count = 0

                if op.lower_bound is not None:
                    low_mask = series.notna() & (series < op.lower_bound)
                    lower_count = int(low_mask.sum())
                    for idx in series.index[low_mask][:3]:
                        sample_diffs.append(
                            SampleDiff(
                                row_index=int(idx),
                                column=col,
                                original_value=str(series.loc[idx]),
                                corrected_value=str(op.lower_bound),
                                operation=f"cap_outliers (lower: {op.lower_bound})",
                            )
                        )

                if op.upper_bound is not None:
                    up_mask = series.notna() & (series > op.upper_bound)
                    upper_count = int(up_mask.sum())
                    for idx in series.index[up_mask][:3]:
                        sample_diffs.append(
                            SampleDiff(
                                row_index=int(idx),
                                column=col,
                                original_value=str(series.loc[idx]),
                                corrected_value=str(op.upper_bound),
                                operation=f"cap_outliers (upper: {op.upper_bound})",
                            )
                        )

                capped_count = lower_count + upper_count
                working_df[col] = series.clip(lower=op.lower_bound, upper=op.upper_bound)

                op_previews.append(
                    OperationPreview(
                        operation_type="cap_outliers",
                        column=col,
                        affected_rows=capped_count,
                        description=(
                            f"Capped {capped_count} outliers in '{col}' "
                            f"(lower={op.lower_bound}: {lower_count} rows; upper={op.upper_bound}: {upper_count} rows)."
                        ),
                    )
                )

        return working_df, op_previews, sample_diffs, global_warnings

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
