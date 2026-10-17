import pytest
import numpy as np
import pandas as pd
from app.services.profiler_service import ProfilerService


def test_clean_dataset_quality_score():
    """Verify a clean dataset receives a high/perfect score of 100 with zero penalties."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
        "score": [85.0, 92.0, 78.0, 88.0, 95.0],
    })
    result = ProfilerService.profile_dataframe(df)

    assert result.row_count == 5
    assert result.column_count == 3
    assert result.total_missing_cells == 0
    assert result.total_duplicate_rows == 0
    assert result.quality_score.score == 100.0
    assert result.columns["id"].is_candidate_identifier is True
    assert len(result.issues) == 0


def test_missing_values_detection_and_empty_column():
    """Verify missing values are accurately tallied and empty columns are flagged."""
    df = pd.DataFrame({
        "id": [1, 2, 3, 4, 5],
        "partial_null": ["A", None, "C", None, "E"],  # 40% null
        "all_null": [None, None, None, None, None],     # 100% null
    })
    result = ProfilerService.profile_dataframe(df)

    assert result.columns["partial_null"].missing_count == 2
    assert result.columns["partial_null"].missing_percentage == 40.0
    assert result.columns["all_null"].missing_count == 5
    assert result.columns["all_null"].missing_percentage == 100.0

    issue_types = [i.issue_type for i in result.issues]
    assert "missing_values" in issue_types
    assert "empty_column" in issue_types
    assert result.quality_score.score < 100.0
    assert "missing_values" in result.quality_score.penalties


def test_duplicate_rows_detection():
    """Verify duplicate row detection and penalty assignment."""
    df = pd.DataFrame({
        "col_a": [1, 2, 1, 2, 3],
        "col_b": ["x", "y", "x", "y", "z"],
    })
    result = ProfilerService.profile_dataframe(df)

    assert result.total_duplicate_rows == 2
    assert result.duplicate_percentage == 40.0

    duplicate_issues = [i for i in result.issues if i.issue_type == "duplicate_rows"]
    assert len(duplicate_issues) == 1
    assert duplicate_issues[0].affected_count == 2
    assert "duplicate_rows" in result.quality_score.penalties


def test_iqr_numeric_outlier_detection():
    """Verify IQR outlier detection detects extreme values and labels them as candidate anomalies."""
    # Data with median around 50 and one extreme value 1000
    df = pd.DataFrame({
        "measurement": [48.0, 49.0, 50.0, 51.0, 52.0, 49.5, 50.5, 48.5, 51.5, 1000.0],
    })
    result = ProfilerService.profile_dataframe(df)

    col_prof = result.columns["measurement"]
    assert col_prof.outlier_count == 1
    assert col_prof.outlier_percentage == 10.0

    outlier_issues = [i for i in result.issues if i.issue_type == "outlier"]
    assert len(outlier_issues) == 1
    assert outlier_issues[0].severity == "low"  # Labeled as candidate anomaly
    assert "candidate outliers via IQR rule" in outlier_issues[0].description


def test_invalid_date_parsing_detection():
    """Verify date-like column detects conversion failures."""
    df = pd.DataFrame({
        "timestamp_col": ["2026-01-01", "2026-02-15", "not-a-valid-date", "2026-03-30", "invalid_timestamp"],
    })
    result = ProfilerService.profile_dataframe(df)

    col_prof = result.columns["timestamp_col"]
    assert col_prof.inferred_type == "datetime"
    assert col_prof.valid_date_count == 3
    assert col_prof.invalid_date_count == 2

    date_issues = [i for i in result.issues if i.issue_type == "invalid_date"]
    assert len(date_issues) == 1
    assert date_issues[0].affected_count == 2


def test_constant_value_column_detection():
    """Verify columns with a single repeated value are flagged as constant."""
    df = pd.DataFrame({
        "user_id": [101, 102, 103, 104],
        "status": ["ACTIVE", "ACTIVE", "ACTIVE", "ACTIVE"],
    })
    result = ProfilerService.profile_dataframe(df)

    constant_issues = [i for i in result.issues if i.issue_type == "constant_column"]
    assert len(constant_issues) == 1
    assert constant_issues[0].affected_column == "status"
    assert "constant_columns" in result.quality_score.penalties


def test_expected_schema_validation():
    """Verify expected schema validation flags missing columns and type mismatches."""
    df = pd.DataFrame({
        "user_id": [1, 2, 3],
        "full_name": ["Alice", "Bob", "Charlie"],
        "unexpected_field": [True, False, True],
    })
    expected_schema = {
        "columns": {
            "user_id": "numeric",
            "full_name": "string",
            "required_email": "string",  # Missing in df
        },
        "allow_unexpected": False,
    }
    result = ProfilerService.profile_dataframe(df, expected_schema=expected_schema)

    missing_schema = [i for i in result.issues if i.rule_name == "schema_missing_column_check"]
    assert len(missing_schema) == 1
    assert missing_schema[0].affected_column == "required_email"

    unexp_schema = [i for i in result.issues if i.rule_name == "schema_unexpected_column_check"]
    assert len(unexp_schema) == 1
    assert unexp_schema[0].affected_column == "unexpected_field"


def test_empty_dataframe_and_score_bounds():
    """Verify empty datasets receive score 0.0 and scores are always clamped in [0.0, 100.0]."""
    # 0 rows
    empty_df = pd.DataFrame(columns=["a", "b", "c"])
    res_empty = ProfilerService.profile_dataframe(empty_df)
    assert res_empty.quality_score.score == 0.0
    assert "0 rows" in res_empty.quality_score.explanation

    # Extremely corrupted dataset
    horrible_df = pd.DataFrame({
        "all_null_1": [None] * 50,
        "all_null_2": [None] * 50,
        "constant_1": ["x"] * 50,
        "constant_2": ["y"] * 50,
    })
    res_horrible = ProfilerService.profile_dataframe(horrible_df)
    assert 0.0 <= res_horrible.quality_score.score <= 100.0


def test_deterministic_scoring():
    """Verify that identical inputs produce exactly the same score and explanation."""
    df = pd.DataFrame({
        "a": [1, 2, None, 4, 5, 2],
        "b": ["apple", "banana", "apple", "date", "fig", "banana"],
    })
    res_1 = ProfilerService.profile_dataframe(df)
    res_2 = ProfilerService.profile_dataframe(df)

    assert res_1.quality_score.score == res_2.quality_score.score
    assert res_1.quality_score.penalties == res_2.quality_score.penalties
    assert res_1.quality_score.explanation == res_2.quality_score.explanation
