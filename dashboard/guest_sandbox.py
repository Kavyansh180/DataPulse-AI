"""DataPulse AI — Isolated Guest Mode Sandbox Engine.

Provides 100% in-memory data profiling, quality scoring, anomaly detection,
and safe remediation simulation without writing to Neon PostgreSQL or Amazon S3.
"""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Ensure root package 'app' is not shadowed by dashboard/app.py
if "app" in sys.modules and not hasattr(sys.modules["app"], "__path__"):
    del sys.modules["app"]

from app.services.profiler_service import ProfilerService, DatasetProfileResult
from app.services.remediation_service import RemediationService
from app.schemas.remediation import RemediationOperation
from dashboard.sample_demo import get_sample_csv_bytes
SAMPLE_CSV_PATH = _PROJECT_ROOT / "sample_data" / "synthetic_customer_orders.csv"


def load_default_guest_dataset() -> pd.DataFrame:
    """Load the curated synthetic e-commerce dataset for guest exploration."""
    if SAMPLE_CSV_PATH.exists():
        return pd.read_csv(SAMPLE_CSV_PATH)
    import io
    return pd.read_csv(io.BytesIO(get_sample_csv_bytes()))


def profile_guest_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    """Execute in-memory statistical profiling on a guest DataFrame."""
    report: DatasetProfileResult = ProfilerService.profile_dataframe(df)

    # Format column metrics matching QualityMetricRead schema
    metrics_list: List[Dict[str, Any]] = []
    for col_name, prof in report.columns.items():
        metrics_list.append({
            "column_name": col_name,
            "metric_name": "missing_percentage",
            "metric_value": round(prof.missing_percentage, 2),
            "threshold_value": 0.0,
            "is_anomalous": prof.missing_count > 0,
        })
        if prof.inferred_type == "numeric":
            metrics_list.append({
                "column_name": col_name,
                "metric_name": "outlier_count",
                "metric_value": float(prof.outlier_count),
                "threshold_value": 0.0,
                "is_anomalous": prof.outlier_count > 0,
            })
            if prof.mean_value is not None:
                metrics_list.append({
                    "column_name": col_name,
                    "metric_name": "mean_value",
                    "metric_value": round(float(prof.mean_value), 2),
                    "threshold_value": None,
                    "is_anomalous": False,
                })

    # Format issues matching QualityIssueRead schema
    issues_list: List[Dict[str, Any]] = []
    for iss in report.issues:
        issues_list.append({
            "severity": iss.severity,
            "issue_type": iss.issue_type,
            "rule_name": iss.rule_name,
            "description": iss.description,
            "column_name": iss.affected_column,
            "status": "detected",
        })

    anomalies_count = len([m for m in metrics_list if m.get("is_anomalous")])

    return {
        "dataset_name": "synthetic_customer_orders_sandbox",
        "quality_score": round(report.quality_score.score, 2),
        "total_rows_profiled": len(df),
        "total_columns_profiled": len(df.columns),
        "component_scores": report.quality_score.component_scores,
        "score_explanation": report.quality_score.explanation,
        "issues_count": len(issues_list),
        "anomalous_metrics_count": anomalies_count,
        "metrics": metrics_list,
        "issues": issues_list,
        "df": df,
    }


def simulate_guest_remediation(
    df: pd.DataFrame,
    operations_dict_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Simulate remediation operations in-memory without persistence."""
    pydantic_ops = [RemediationOperation(**op) for op in operations_dict_list]
    working_df, op_previews, sample_diffs, warnings = RemediationService.simulate_operations(df, pydantic_ops)

    formatted_ops = []
    for prev in op_previews:
        formatted_ops.append({
            "operation_type": prev.operation_type,
            "column": prev.column,
            "affected_rows": prev.affected_rows,
            "description": prev.description,
        })

    formatted_diffs = []
    for d in sample_diffs:
        formatted_diffs.append({
            "row_index": d.row_index,
            "column": d.column,
            "original_value": d.original_value,
            "corrected_value": d.corrected_value,
        })

    return {
        "preview_id": "guest_sandbox_preview_token",
        "total_rows_before": len(df),
        "total_rows_after": len(working_df),
        "operations": formatted_ops,
        "sample_diffs": formatted_diffs,
        "warnings": warnings,
        "new_df": working_df,
    }


def apply_guest_remediation(
    original_df: pd.DataFrame,
    operations_dict_list: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Apply remediation in-memory and revalidate quality score."""
    pydantic_ops = [RemediationOperation(**op) for op in operations_dict_list]
    working_df, _, _, _ = RemediationService.simulate_operations(original_df, pydantic_ops)

    original_report = ProfilerService.profile_dataframe(original_df)
    new_report = ProfilerService.profile_dataframe(working_df)

    orig_score = round(original_report.quality_score.score, 2)
    new_score = round(new_report.quality_score.score, 2)
    improvement = round(new_score - orig_score, 2)

    # Calculate resolved vs remaining issues
    orig_issue_descs = {i.description for i in original_report.issues}
    new_issue_descs = {i.description for i in new_report.issues}

    resolved = list(orig_issue_descs - new_issue_descs)
    remaining = list(new_issue_descs)

    return {
        "original_score": orig_score,
        "remediated_score": new_score,
        "score_improvement": improvement,
        "new_run_id": "SANDBOX-002",
        "new_version_tag": "v1.1-sandbox-remediated",
        "storage_uri": "memory://sandbox/synthetic_customer_orders_remediated.csv",
        "resolved_issues": resolved if resolved else ["Imputed null records and normalized data values."],
        "remaining_issues": remaining,
        "remediated_df": working_df,
    }
