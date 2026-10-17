import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Set
import numpy as np
import pandas as pd

logger = logging.getLogger("datapulse.profiler")


@dataclass
class DetectedIssue:
    rule_name: str
    severity: str  # low, medium, high, critical
    issue_type: str  # missing_values, duplicate_rows, outlier, invalid_date, empty_column, constant_column, schema_mismatch, unexpected_column
    description: str
    affected_column: Optional[str] = None
    affected_count: int = 0
    evidence: Optional[Dict[str, Any]] = None


@dataclass
class ColumnProfile:
    column_name: str
    inferred_type: str  # numeric, string, datetime, boolean
    missing_count: int
    missing_percentage: float
    distinct_count: int
    distinct_ratio: float
    is_candidate_identifier: bool = False
    # Numeric stats
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    mean_value: Optional[float] = None
    median_value: Optional[float] = None
    std_value: Optional[float] = None
    outlier_count: int = 0
    outlier_percentage: float = 0.0
    # String stats
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    avg_length: Optional[float] = None
    # Date stats
    valid_date_count: int = 0
    invalid_date_count: int = 0
    min_date: Optional[str] = None
    max_date: Optional[str] = None


@dataclass
class QualityScoreResult:
    score: float
    completeness_score: float
    uniqueness_score: float
    validity_score: float
    consistency_score: float
    component_scores: Dict[str, float]
    penalties: Dict[str, float]
    explanation: str


@dataclass
class DatasetProfileResult:
    row_count: int
    column_count: int
    column_names: List[str]
    inferred_types: Dict[str, str]
    memory_usage_bytes: int
    total_cells: int
    total_missing_cells: int
    missing_percentage: float
    total_duplicate_rows: int
    duplicate_percentage: float
    columns: Dict[str, ColumnProfile]
    issues: List[DetectedIssue]
    quality_score: QualityScoreResult


class ProfilerService:
    """Core profiling engine for analyzing DataFrames, detecting anomalies, and calculating quality scores."""

    @classmethod
    def profile_dataframe(
        cls,
        df: pd.DataFrame,
        expected_schema: Optional[Dict[str, Any]] = None,
    ) -> DatasetProfileResult:
        """Execute full profiling on a DataFrame without mutating the original data."""
        row_count, col_count = df.shape
        column_names = list(df.columns)
        total_cells = row_count * col_count

        # Handle edge cases: 0 rows or 0 columns
        if row_count == 0 or col_count == 0:
            score_res = cls._calculate_score_for_empty_dataset(row_count, col_count)
            empty_issues = []
            if row_count == 0:
                empty_issues.append(
                    DetectedIssue(
                        rule_name="empty_dataset_check",
                        severity="critical",
                        issue_type="missing_values",
                        description="Dataset contains 0 rows.",
                        affected_count=0,
                    )
                )
            if col_count == 0:
                empty_issues.append(
                    DetectedIssue(
                        rule_name="zero_columns_check",
                        severity="critical",
                        issue_type="schema_mismatch",
                        description="Dataset contains 0 columns.",
                        affected_count=0,
                    )
                )

            return DatasetProfileResult(
                row_count=row_count,
                column_count=col_count,
                column_names=column_names,
                inferred_types={},
                memory_usage_bytes=0,
                total_cells=0,
                total_missing_cells=0,
                missing_percentage=100.0,
                total_duplicate_rows=0,
                duplicate_percentage=0.0,
                columns={},
                issues=empty_issues,
                quality_score=score_res,
            )

        # 1. General statistics
        memory_usage_bytes = int(df.memory_usage(deep=True).sum())
        total_missing_cells = int(df.isna().sum().sum())
        missing_percentage = round((total_missing_cells / total_cells) * 100.0, 2) if total_cells > 0 else 0.0

        total_duplicate_rows = int(df.duplicated().sum())
        duplicate_percentage = round((total_duplicate_rows / row_count) * 100.0, 2) if row_count > 0 else 0.0

        # 2. Column profiling and issue detection
        inferred_types: Dict[str, str] = {}
        columns: Dict[str, ColumnProfile] = {}
        issues: List[DetectedIssue] = []

        # Check duplicate rows issue
        if total_duplicate_rows > 0:
            sev = "medium" if duplicate_percentage < 10.0 else "high"
            issues.append(
                DetectedIssue(
                    rule_name="duplicate_rows_check",
                    severity=sev,
                    issue_type="duplicate_rows",
                    description=(
                        f"Found {total_duplicate_rows} duplicate rows "
                        f"({duplicate_percentage}% of total {row_count} rows)."
                    ),
                    affected_count=total_duplicate_rows,
                    evidence={"duplicate_count": total_duplicate_rows, "percentage": duplicate_percentage},
                )
            )

        # Profile each column
        for col in column_names:
            series = df[col]
            col_prof, col_issues = cls._profile_single_column(series, row_count)
            inferred_types[col] = col_prof.inferred_type
            columns[col] = col_prof
            issues.extend(col_issues)

        # 3. Expected schema validation (if provided)
        if expected_schema:
            schema_issues = cls._validate_expected_schema(df, inferred_types, expected_schema)
            issues.extend(schema_issues)

        # 4. Compute transparent, explainable quality score
        quality_score = cls._calculate_quality_score(
            row_count=row_count,
            col_count=col_count,
            total_cells=total_cells,
            total_missing_cells=total_missing_cells,
            total_duplicate_rows=total_duplicate_rows,
            columns=columns,
            issues=issues,
            has_expected_schema=bool(expected_schema),
        )

        return DatasetProfileResult(
            row_count=row_count,
            column_count=col_count,
            column_names=column_names,
            inferred_types=inferred_types,
            memory_usage_bytes=memory_usage_bytes,
            total_cells=total_cells,
            total_missing_cells=total_missing_cells,
            missing_percentage=missing_percentage,
            total_duplicate_rows=total_duplicate_rows,
            duplicate_percentage=duplicate_percentage,
            columns=columns,
            issues=issues,
            quality_score=quality_score,
        )

    @classmethod
    def _profile_single_column(cls, series: pd.Series, row_count: int) -> Tuple[ColumnProfile, List[DetectedIssue]]:
        """Profile an individual column with type-appropriate metrics and issue detection."""
        col_name = str(series.name)
        col_issues: List[DetectedIssue] = []

        missing_count = int(series.isna().sum())
        missing_pct = round((missing_count / row_count) * 100.0, 2) if row_count > 0 else 0.0

        non_null_series = series.dropna()
        distinct_count = int(non_null_series.nunique())
        distinct_ratio = round(distinct_count / row_count, 4) if row_count > 0 else 0.0

        # Detect candidate identifier (unique, zero nulls, not empty)
        is_candidate_identifier = bool(missing_count == 0 and distinct_count == row_count and row_count > 0)

        # Detect empty column (100% missing)
        if missing_count == row_count:
            col_issues.append(
                DetectedIssue(
                    rule_name="empty_column_check",
                    severity="high",
                    issue_type="empty_column",
                    description=f"Column '{col_name}' is completely empty (100% null values).",
                    affected_column=col_name,
                    affected_count=row_count,
                )
            )
        elif missing_count > 0:
            # Missing values issue
            sev = "low" if missing_pct < 5.0 else ("medium" if missing_pct < 20.0 else "high")
            col_issues.append(
                DetectedIssue(
                    rule_name="missing_values_check",
                    severity=sev,
                    issue_type="missing_values",
                    description=f"Column '{col_name}' has {missing_count} missing values ({missing_pct}%).",
                    affected_column=col_name,
                    affected_count=missing_count,
                    evidence={"missing_count": missing_count, "missing_percentage": missing_pct},
                )
            )

        # Detect constant value column (all non-null rows have same value)
        if distinct_count == 1 and row_count > 1 and missing_count < row_count:
            col_issues.append(
                DetectedIssue(
                    rule_name="constant_column_check",
                    severity="low",
                    issue_type="constant_column",
                    description=f"Column '{col_name}' contains a constant value across all valid rows.",
                    affected_column=col_name,
                    affected_count=row_count - missing_count,
                    evidence={"constant_value": str(non_null_series.iloc[0])},
                )
            )

        # Infer general data type
        inferred_type = cls._infer_column_type(non_null_series, col_name=col_name)

        col_profile = ColumnProfile(
            column_name=col_name,
            inferred_type=inferred_type,
            missing_count=missing_count,
            missing_percentage=missing_pct,
            distinct_count=distinct_count,
            distinct_ratio=distinct_ratio,
            is_candidate_identifier=is_candidate_identifier,
        )

        # Profile numeric columns
        if inferred_type == "numeric":
            cls._populate_numeric_stats(col_profile, non_null_series, col_issues)
        elif inferred_type == "datetime":
            cls._populate_datetime_stats(col_profile, non_null_series, col_issues)
        else:
            cls._populate_string_stats(col_profile, non_null_series, col_issues)

        return col_profile, col_issues

    @classmethod
    def _infer_column_type(cls, non_null_series: pd.Series, col_name: str = "") -> str:
        """Infer type category without mutating original data."""
        if non_null_series.empty:
            return "string"

        # Check native numeric
        if pd.api.types.is_numeric_dtype(non_null_series):
            if pd.api.types.is_bool_dtype(non_null_series):
                return "boolean"
            return "numeric"

        if pd.api.types.is_datetime64_any_dtype(non_null_series):
            return "datetime"

        # Check sample strings for numeric or datetime representation
        sample = non_null_series.head(50).astype(str).str.strip()

        # Check boolean strings
        bool_set = {"true", "false", "yes", "no", "0", "1", "t", "f"}
        if all(val.lower() in bool_set for val in sample if val):
            if set(sample.str.lower()).issubset({"true", "false", "yes", "no"}):
                return "boolean"

        # Check if convertible to numeric
        numeric_converted = pd.to_numeric(sample, errors="coerce")
        if numeric_converted.notna().sum() / len(sample) >= 0.8:
            return "numeric"

        # Check if convertible to datetime
        try:
            date_converted = pd.to_datetime(sample, errors="coerce", format="mixed")
            ratio = date_converted.notna().sum() / len(sample)
            col_lower = col_name.lower()
            date_keywords = ("date", "time", "timestamp", "year", "month", "day", "created", "updated", "signup")
            has_date_name = any(kw in col_lower for kw in date_keywords)
            if (has_date_name and ratio >= 0.3) or ratio >= 0.6:
                return "datetime"
        except Exception:
            pass

        return "string"

    @classmethod
    def _populate_numeric_stats(
        cls,
        prof: ColumnProfile,
        series: pd.Series,
        col_issues: List[DetectedIssue],
    ) -> None:
        """Calculate numeric statistics and detect IQR outliers."""
        # Convert non-numeric values gracefully for statistical analysis
        numeric_series = pd.to_numeric(series, errors="coerce").dropna()
        if numeric_series.empty:
            return

        # Check for values that failed numeric conversion
        conversion_failures = len(series) - len(numeric_series)
        if conversion_failures > 0:
            col_issues.append(
                DetectedIssue(
                    rule_name="invalid_numeric_type_check",
                    severity="medium",
                    issue_type="invalid_type",
                    description=(
                        f"Column '{prof.column_name}' expected numeric values but encountered "
                        f"{conversion_failures} unparseable values."
                    ),
                    affected_column=prof.column_name,
                    affected_count=conversion_failures,
                )
            )

        prof.min_value = float(numeric_series.min())
        prof.max_value = float(numeric_series.max())
        prof.mean_value = round(float(numeric_series.mean()), 4)
        prof.median_value = round(float(numeric_series.median()), 4)
        prof.std_value = round(float(numeric_series.std()), 4) if len(numeric_series) > 1 else 0.0

        # IQR Outlier Detection
        q1 = float(numeric_series.quantile(0.25))
        q3 = float(numeric_series.quantile(0.75))
        iqr = q3 - q1

        if iqr > 0:
            lower_bound = q1 - (1.5 * iqr)
            upper_bound = q3 + (1.5 * iqr)
            outliers = numeric_series[(numeric_series < lower_bound) | (numeric_series > upper_bound)]
            outlier_count = int(len(outliers))
            prof.outlier_count = outlier_count
            prof.outlier_percentage = round((outlier_count / len(numeric_series)) * 100.0, 2)

            if outlier_count > 0:
                col_issues.append(
                    DetectedIssue(
                        rule_name="iqr_numeric_outlier_check",
                        severity="low",  # Candidate anomaly, not automatically a confirmed error
                        issue_type="outlier",
                        description=(
                            f"Column '{prof.column_name}' has {outlier_count} candidate outliers "
                            f"via IQR rule (bounds: [{round(lower_bound, 2)}, {round(upper_bound, 2)}])."
                        ),
                        affected_column=prof.column_name,
                        affected_count=outlier_count,
                        evidence={
                            "outlier_count": outlier_count,
                            "lower_bound": lower_bound,
                            "upper_bound": upper_bound,
                            "q1": q1,
                            "q3": q3,
                            "iqr": iqr,
                        },
                    )
                )

    @classmethod
    def _populate_datetime_stats(
        cls,
        prof: ColumnProfile,
        series: pd.Series,
        col_issues: List[DetectedIssue],
    ) -> None:
        """Parse datetime information and record invalid dates."""
        parsed = pd.to_datetime(series, errors="coerce")
        valid_count = int(parsed.notna().sum())
        invalid_count = int(parsed.isna().sum())

        prof.valid_date_count = valid_count
        prof.invalid_date_count = invalid_count

        if valid_count > 0:
            prof.min_date = str(parsed.dropna().min())
            prof.max_date = str(parsed.dropna().max())

        if invalid_count > 0:
            col_issues.append(
                DetectedIssue(
                    rule_name="invalid_date_check",
                    severity="medium",
                    issue_type="invalid_date",
                    description=(
                        f"Column '{prof.column_name}' identified as date-like had {invalid_count} "
                        f"values that failed date parsing."
                    ),
                    affected_column=prof.column_name,
                    affected_count=invalid_count,
                )
            )

    @classmethod
    def _populate_string_stats(
        cls,
        prof: ColumnProfile,
        series: pd.Series,
        col_issues: List[DetectedIssue],
    ) -> None:
        """Calculate string length statistics."""
        str_series = series.astype(str)
        lengths = str_series.str.len()

        if not lengths.empty:
            prof.min_length = int(lengths.min())
            prof.max_length = int(lengths.max())
            prof.avg_length = round(float(lengths.mean()), 2)

    @classmethod
    def _validate_expected_schema(
        cls,
        df: pd.DataFrame,
        inferred_types: Dict[str, str],
        expected_schema: Dict[str, Any],
    ) -> List[DetectedIssue]:
        """Validate DataFrame against an expected schema dictionary.

        Example expected_schema:
        {
            "columns": {
                "user_id": "numeric",
                "email": "string",
                "created_at": "datetime"
            },
            "allow_unexpected": False
        }
        """
        issues: List[DetectedIssue] = []
        expected_cols = expected_schema.get("columns", {})
        allow_unexpected = expected_schema.get("allow_unexpected", True)

        actual_cols = set(df.columns)
        expected_set = set(expected_cols.keys())

        # Check missing expected columns
        missing_expected = expected_set - actual_cols
        for missing in sorted(missing_expected):
            issues.append(
                DetectedIssue(
                    rule_name="schema_missing_column_check",
                    severity="high",
                    issue_type="schema_mismatch",
                    description=f"Expected column '{missing}' was not found in the dataset.",
                    affected_column=missing,
                )
            )

        # Check unexpected extra columns
        if not allow_unexpected:
            unexpected = actual_cols - expected_set
            for unexp in sorted(unexpected):
                issues.append(
                    DetectedIssue(
                        rule_name="schema_unexpected_column_check",
                        severity="medium",
                        issue_type="unexpected_column",
                        description=f"Unexpected column '{unexp}' found in dataset.",
                        affected_column=unexp,
                    )
                )

        # Check data type alignment for present columns
        for col, expected_type in expected_cols.items():
            if col in inferred_types:
                actual_type = inferred_types[col]
                # Allow equivalent type matches
                if expected_type.lower() != actual_type.lower():
                    issues.append(
                        DetectedIssue(
                            rule_name="schema_datatype_mismatch_check",
                            severity="medium",
                            issue_type="schema_mismatch",
                            description=(
                                f"Column '{col}' expected type '{expected_type}' "
                                f"but inferred as '{actual_type}'."
                            ),
                            affected_column=col,
                            evidence={"expected_type": expected_type, "actual_type": actual_type},
                        )
                    )

        return issues

    @classmethod
    def _calculate_score_for_empty_dataset(cls, row_count: int, col_count: int) -> QualityScoreResult:
        """Return zero score for completely empty datasets."""
        explanation = (
            f"Dataset is completely empty ({row_count} rows, {col_count} columns). "
            f"Overall quality score is clamped to 0.0."
        )
        return QualityScoreResult(
            score=0.0,
            completeness_score=0.0,
            uniqueness_score=0.0,
            validity_score=0.0,
            consistency_score=0.0,
            component_scores={
                "completeness": 0.0,
                "uniqueness": 0.0,
                "validity": 0.0,
                "consistency": 0.0,
            },
            penalties={"empty_dataset": 100.0},
            explanation=explanation,
        )

    @classmethod
    def _calculate_quality_score(
        cls,
        row_count: int,
        col_count: int,
        total_cells: int,
        total_missing_cells: int,
        total_duplicate_rows: int,
        columns: Dict[str, ColumnProfile],
        issues: List[DetectedIssue],
        has_expected_schema: bool = False,
    ) -> QualityScoreResult:
        """Calculate explainable, normalized quality score from 0 to 100.

        Scoring Model:
        - Starts at 100.0.
        - Completeness (up to 30 pts deduction):
          - Cell missingness ratio * 25.
          - 5 pts deduction per completely empty column (up to 15 max).
        - Uniqueness (up to 20 pts deduction):
          - Duplicate row ratio * 20.
        - Validity (up to 25 pts deduction):
          - Invalid date / type conversions * 15.
          - Outlier candidate density * 10.
        - Consistency & Schema (up to 25 pts deduction):
          - Constant non-id columns: 3 pts each (up to 10 max).
          - Schema mismatch / missing expected columns: 10 pts each (up to 25 max).
        - Clamped: min 0.0, max 100.0.
        """
        penalties: Dict[str, float] = {}
        explanations: List[str] = []

        # 1. Completeness penalty
        missing_ratio = (total_missing_cells / total_cells) if total_cells > 0 else 0.0
        missing_cell_penalty = round(min(25.0, missing_ratio * 35.0), 2)
        if missing_cell_penalty > 0:
            penalties["missing_values"] = missing_cell_penalty
            explanations.append(
                f"-{missing_cell_penalty} pts for missing values ({round(missing_ratio * 100, 2)}% of cells)"
            )

        empty_cols = sum(1 for p in columns.values() if p.missing_count == row_count)
        empty_col_penalty = round(min(15.0, empty_cols * 5.0), 2)
        if empty_col_penalty > 0:
            penalties["empty_columns"] = empty_col_penalty
            explanations.append(f"-{empty_col_penalty} pts for {empty_cols} completely empty column(s)")

        completeness_deduction = missing_cell_penalty + empty_col_penalty
        completeness_score = round(max(0.0, 100.0 - (completeness_deduction * (100.0 / 40.0))), 2)

        # 2. Uniqueness penalty
        dup_ratio = (total_duplicate_rows / row_count) if row_count > 0 else 0.0
        duplicate_penalty = round(min(20.0, dup_ratio * 30.0), 2)
        if duplicate_penalty > 0:
            penalties["duplicate_rows"] = duplicate_penalty
            explanations.append(
                f"-{duplicate_penalty} pts for duplicate rows ({round(dup_ratio * 100, 2)}% of rows)"
            )

        uniqueness_score = round(max(0.0, 100.0 - (duplicate_penalty * (100.0 / 20.0))), 2)

        # 3. Validity penalty
        invalid_cells = sum(
            issue.affected_count
            for issue in issues
            if issue.issue_type in ("invalid_type", "invalid_date")
        )
        invalid_ratio = (invalid_cells / total_cells) if total_cells > 0 else 0.0
        invalid_type_penalty = round(min(15.0, invalid_ratio * 50.0), 2)
        if invalid_type_penalty > 0:
            penalties["invalid_types_dates"] = invalid_type_penalty
            explanations.append(f"-{invalid_type_penalty} pts for unparseable data types or invalid dates")

        outlier_cells = sum(p.outlier_count for p in columns.values())
        outlier_ratio = (outlier_cells / total_cells) if total_cells > 0 else 0.0
        outlier_penalty = round(min(10.0, outlier_ratio * 25.0), 2)
        if outlier_penalty > 0:
            penalties["outliers"] = outlier_penalty
            explanations.append(f"-{outlier_penalty} pts for IQR candidate numeric outliers")

        validity_deduction = invalid_type_penalty + outlier_penalty
        validity_score = round(max(0.0, 100.0 - (validity_deduction * (100.0 / 25.0))), 2)

        # 4. Consistency & Schema penalty
        constant_cols = sum(
            1 for p in columns.values()
            if p.distinct_count == 1 and row_count > 1 and p.missing_count < row_count
        )
        constant_penalty = round(min(10.0, constant_cols * 3.0), 2)
        if constant_penalty > 0:
            penalties["constant_columns"] = constant_penalty
            explanations.append(f"-{constant_penalty} pts for {constant_cols} constant-value column(s)")

        schema_issues_count = sum(
            1 for issue in issues
            if issue.issue_type in ("schema_mismatch", "unexpected_column")
        )
        schema_penalty = round(min(20.0, schema_issues_count * 5.0), 2)
        if schema_penalty > 0:
            penalties["schema_violations"] = schema_penalty
            explanations.append(f"-{schema_penalty} pts for {schema_issues_count} schema violation(s)")

        consistency_deduction = constant_penalty + schema_penalty
        consistency_score = round(max(0.0, 100.0 - (consistency_deduction * (100.0 / 30.0))), 2)

        # Compute total deduction and clamp
        total_deduction = sum(penalties.values())
        final_score = round(max(0.0, min(100.0, 100.0 - total_deduction)), 2)

        if not explanations:
            explanation_str = "Clean dataset: All quality checks passed with zero deductions."
        else:
            explanation_str = (
                f"Base score: 100.0. Applied deductions: {'; '.join(explanations)}. "
                f"Calculated quality score: {final_score}/100."
            )

        component_scores = {
            "completeness": completeness_score,
            "uniqueness": uniqueness_score,
            "validity": validity_score,
            "consistency": consistency_score,
        }

        return QualityScoreResult(
            score=final_score,
            completeness_score=completeness_score,
            uniqueness_score=uniqueness_score,
            validity_score=validity_score,
            consistency_score=consistency_score,
            component_scores=component_scores,
            penalties=penalties,
            explanation=explanation_str,
        )
