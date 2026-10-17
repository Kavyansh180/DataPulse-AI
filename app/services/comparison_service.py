import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple

from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.schemas.profiling import RunComparisonResponse
from app.api.errors import APIError

logger = logging.getLogger("datapulse.comparison")


class ComparisonService:
    """Service providing historical comparison between two profiling runs of a dataset."""

    @classmethod
    def compare_runs(
        cls,
        run_1: ProfilingRun,
        run_2: ProfilingRun,
    ) -> RunComparisonResponse:
        """Compare a baseline/previous run (run_1) with a current/comparison run (run_2).

        Detects schema evolution, score progression, metric shifts, newly emerged issues,
        and resolved issues without falsely attributing removed columns to resolved issues.
        """
        # Ensure runs belong to the same parent dataset
        dataset_id_1 = run_1.dataset_version.dataset_id
        dataset_id_2 = run_2.dataset_version.dataset_id
        if dataset_id_1 != dataset_id_2:
            raise APIError(
                status_code=400,
                message=(
                    f"Cannot compare runs from different datasets. "
                    f"Run {run_1.id} belongs to dataset {dataset_id_1}, "
                    f"while Run {run_2.id} belongs to dataset {dataset_id_2}."
                ),
                code="DATASET_MISMATCH",
            )

        # 1. Quality score comparison
        score_1 = run_1.quality_score
        score_2 = run_2.quality_score
        score_change = None
        if score_1 is not None and score_2 is not None:
            score_change = round(score_2 - score_1, 2)

        # 2. Extract column sets to evaluate schema compatibility
        cols_1 = cls._extract_columns_from_run(run_1)
        cols_2 = cls._extract_columns_from_run(run_2)

        added_cols = sorted(list(cols_2 - cols_1))
        removed_cols = sorted(list(cols_1 - cols_2))
        schema_compatible = len(added_cols) == 0 and len(removed_cols) == 0

        schema_change_note = None
        if not schema_compatible:
            parts = []
            if added_cols:
                parts.append(f"added columns: {', '.join(added_cols)}")
            if removed_cols:
                parts.append(f"removed columns: {', '.join(removed_cols)}")
            schema_change_note = f"Schema evolved ({'; '.join(parts)})."

        # 3. Metric changes
        metrics_1 = cls._index_metrics(run_1)
        metrics_2 = cls._index_metrics(run_2)

        metric_changes: Dict[str, Any] = {
            "total_rows_previous": run_1.total_rows_profiled,
            "total_rows_current": run_2.total_rows_profiled,
            "row_count_diff": (
                (run_2.total_rows_profiled or 0) - (run_1.total_rows_profiled or 0)
                if run_1.total_rows_profiled is not None and run_2.total_rows_profiled is not None
                else None
            ),
        }

        # Compare table-level metrics if available
        for key in ["missing_percentage", "duplicate_percentage"]:
            m1 = metrics_1.get((key, None))
            m2 = metrics_2.get((key, None))
            if m1 is not None and m2 is not None:
                metric_changes[f"{key}_previous"] = m1.metric_value
                metric_changes[f"{key}_current"] = m2.metric_value
                metric_changes[f"{key}_diff"] = (
                    round(m2.metric_value - m1.metric_value, 2)
                    if m1.metric_value is not None and m2.metric_value is not None
                    else None
                )

        # 4. Compare issues
        # Distinguish truly resolved issues from issues where the entire column was dropped!
        issues_1 = run_1.dataset_version.quality_issues
        issues_2 = run_2.dataset_version.quality_issues

        sigs_1: Dict[str, QualityIssue] = {
            cls._issue_signature(i): i for i in issues_1
        }
        sigs_2: Dict[str, QualityIssue] = {
            cls._issue_signature(i): i for i in issues_2
        }

        new_issue_sigs = set(sigs_2.keys()) - set(sigs_1.keys())
        potential_resolved = set(sigs_1.keys()) - set(sigs_2.keys())

        new_issues: List[str] = [
            f"[{sigs_2[s].severity.upper()}] {sigs_2[s].issue_type} in {sigs_2[s].rule_name}: {sigs_2[s].description}"
            for s in sorted(new_issue_sigs)
        ]

        resolved_issues: List[str] = []
        for s in sorted(potential_resolved):
            old_issue = sigs_1[s]
            # Check if column was dropped
            affected_col = None
            if hasattr(old_issue, "description") and "Column '" in old_issue.description:
                try:
                    affected_col = old_issue.description.split("Column '")[1].split("'")[0]
                except Exception:
                    pass

            if affected_col and affected_col in removed_cols:
                # Column was deleted, not resolved
                logger.info(f"Issue {s} not marked resolved because column {affected_col} was dropped.")
            else:
                resolved_issues.append(
                    f"Resolved [{old_issue.severity.upper()}]: {old_issue.rule_name} ({old_issue.issue_type})"
                )

        return RunComparisonResponse(
            dataset_id=dataset_id_1,
            run_id_1=run_1.id,
            run_id_2=run_2.id,
            previous_score=score_1,
            current_score=score_2,
            score_change=score_change,
            schema_compatible=schema_compatible,
            schema_change_note=schema_change_note,
            added_columns=added_cols,
            removed_columns=removed_cols,
            metric_changes=metric_changes,
            new_issues=new_issues,
            resolved_issues=resolved_issues,
        )

    @staticmethod
    def _extract_columns_from_run(run: ProfilingRun) -> Set[str]:
        """Extract set of column names present during the profiling run."""
        cols = set()
        # 1. From summary_stats JSON if present
        if run.summary_stats:
            try:
                data = json.loads(run.summary_stats)
                if "column_names" in data:
                    return set(data["column_names"])
            except Exception:
                pass

        # 2. From QualityMetrics column names
        for metric in run.metrics:
            if metric.column_name:
                cols.add(metric.column_name)

        return cols

    @staticmethod
    def _index_metrics(run: ProfilingRun) -> Dict[Tuple[str, Optional[str]], QualityMetric]:
        """Index metrics by (metric_name, column_name)."""
        indexed = {}
        for m in run.metrics:
            indexed[(m.metric_name, m.column_name)] = m
        return indexed

    @staticmethod
    def _issue_signature(issue: QualityIssue) -> str:
        """Create canonical signature for issue comparison."""
        return f"{issue.issue_type}:{issue.rule_name}"
