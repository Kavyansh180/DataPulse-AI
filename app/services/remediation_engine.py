"""DataPulse AI — In-Memory Remediation Engine.

Provides database-independent, safe, and deterministic DataFrame remediation operations,
preview generation, and sample diff calculation. Zero database, S3, or network dependencies.
"""

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd

from app.core.exceptions import APIError
from app.schemas.remediation import (
    OperationPreview,
    RemediationOperation,
    SampleDiff,
)

logger = logging.getLogger("datapulse.remediation_engine")


class RemediationEngine:
    """In-memory data remediation engine executing deterministic DataFrame transformations."""

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
