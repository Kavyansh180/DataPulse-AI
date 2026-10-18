"""DataPulse AI — Guest Sandbox Isolation & Database Independence Regression Tests.

Verifies that guest sandbox profiling and remediation operate 100% in-memory
without database credentials, without importing ORM models, and without
initializing SQLAlchemy database engines or dialects.
"""

import sys
import subprocess
from unittest.mock import patch
import pandas as pd
import pytest

from dashboard.guest_sandbox import (
    load_default_guest_dataset,
    profile_guest_dataset,
    simulate_guest_remediation,
    apply_guest_remediation,
)
import app.core.database as database_module


def test_guest_sandbox_runs_without_database_engine():
    """Verify guest sandbox profiling & remediation succeed with engine creation blocked."""
    # Patch create_db_engine to guarantee it is NEVER called during guest sandbox operations
    with patch.object(
        database_module,
        "create_db_engine",
        side_effect=RuntimeError("FAIL: create_db_engine must not be called in guest mode"),
    ):
        # 1. Load dataset
        df = load_default_guest_dataset()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0

        # 2. Profile dataset in-memory
        profile_res = profile_guest_dataset(df)
        assert profile_res["dataset_name"] == "synthetic_customer_orders_sandbox"
        assert "quality_score" in profile_res
        assert profile_res["total_rows_profiled"] == len(df)
        assert profile_res["total_columns_profiled"] == len(df.columns)
        assert len(profile_res["metrics"]) > 0
        assert len(profile_res["issues"]) > 0

        # 3. Simulate remediation in-memory
        ops = [
            {"operation_type": "drop_duplicates"},
            {"operation_type": "fill_missing", "column": "email", "strategy": "constant", "fill_value": "missing@corp.com"},
            {"operation_type": "trim_whitespace", "column": "status"},
        ]
        sim_res = simulate_guest_remediation(df, ops)
        assert sim_res["preview_id"] == "guest_sandbox_preview_token"
        assert sim_res["total_rows_before"] == len(df)
        assert len(sim_res["operations"]) == 3
        assert isinstance(sim_res["new_df"], pd.DataFrame)

        # 4. Apply remediation in-memory
        apply_res = apply_guest_remediation(df, ops)
        assert "original_score" in apply_res
        assert "remediated_score" in apply_res
        assert "score_improvement" in apply_res
        assert apply_res["remediated_score"] >= apply_res["original_score"]
        assert apply_res["storage_uri"].startswith("memory://")
        assert isinstance(apply_res["remediated_df"], pd.DataFrame)


def test_guest_sandbox_isolated_in_fresh_process_with_invalid_database_url():
    """Verify that in a clean process with an invalid database URL, guest sandbox operates without error."""
    code = """
import sys
import os
import pandas as pd

# Set invalid database connection parameters that would fail if connected or dialed
os.environ["DATABASE_URL"] = "postgresql://nonexistent_user:fake_password@unreachable.invalid.local:5432/fake_db"

from dashboard.guest_sandbox import (
    load_default_guest_dataset,
    profile_guest_dataset,
    simulate_guest_remediation,
    apply_guest_remediation,
)

# Verify database engine was never loaded into sys.modules
assert "app.core.database" not in sys.modules, f"app.core.database was unexpectedly imported: {list(sys.modules.keys())}"
assert "app.models" not in sys.modules, "app.models was unexpectedly imported"

# Run guest workflow
df = load_default_guest_dataset()
p = profile_guest_dataset(df)
assert p["quality_score"] > 0

ops = [{"operation_type": "drop_duplicates"}]
s = simulate_guest_remediation(df, ops)
assert s["total_rows_after"] <= s["total_rows_before"]

a = apply_guest_remediation(df, ops)
assert a["remediated_score"] >= a["original_score"]

print("SUCCESS: Guest sandbox executed fully in-memory with unreachable DATABASE_URL")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(database_module._PROJECT_ROOT if hasattr(database_module, "_PROJECT_ROOT") else "."),
    )
    assert result.returncode == 0, f"Subprocess failed:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    assert "SUCCESS: Guest sandbox executed fully in-memory" in result.stdout


def test_guest_sandbox_all_remediation_transformations_in_memory():
    """Verify each allowed remediation operation functions accurately in-memory."""
    df = pd.DataFrame({
        "num": [10.0, None, 10.0, 500.0],
        "txt": ["  apple  ", "banana", "  apple  ", " "],
        "cat": ["A", "B", "A", None],
    })

    ops = [
        {"operation_type": "drop_duplicates"},
        {"operation_type": "fill_missing", "column": "num", "strategy": "mean"},
        {"operation_type": "trim_whitespace", "column": "txt", "empty_string_to_null": True},
        {"operation_type": "cap_outliers", "column": "num", "lower_bound": 5.0, "upper_bound": 100.0},
    ]

    sim = simulate_guest_remediation(df, ops)
    assert sim["total_rows_after"] == 3  # 1 duplicate row dropped
    assert len(sim["operations"]) == 4

    out_df = sim["new_df"]
    # Check capping
    assert out_df["num"].max() <= 100.0
    # Check trimming
    assert out_df.loc[0, "txt"] == "apple"


def test_guest_sandbox_gemini_analysis_without_key_returns_none(monkeypatch):
    """Verify analyze_guest_dataset_with_gemini returns None gracefully when no key is set."""
    from dashboard.guest_sandbox import analyze_guest_dataset_with_gemini
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", None)
    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    fake_profile = {"dataset_name": "test", "total_rows_profiled": 10, "quality_score": 90.0}
    res = analyze_guest_dataset_with_gemini(fake_profile)
    assert res is None


def test_guest_sandbox_gemini_analysis_mocked_success(monkeypatch):
    """Verify analyze_guest_dataset_with_gemini parses and returns report when key is present."""
    import json
    from unittest.mock import MagicMock, patch
    from dashboard.guest_sandbox import analyze_guest_dataset_with_gemini
    from app.core.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "AIzaSyMockKeyForGuestTest")
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyMockKeyForGuestTest")

    mock_resp = json.dumps({
        "overall_assessment": "Guest dataset has clean schema with minor nulls.",
        "key_findings": ["No duplicate rows found."],
        "likely_causes": [],
        "recommendations": [{"action": "Fill nulls", "priority": "medium", "evidence": "2 nulls"}],
        "limitations": [],
    })

    with patch("app.services.llm_provider.GeminiProvider.generate", return_value=mock_resp):
        fake_profile = {
            "dataset_name": "guest_synthetic",
            "total_rows_profiled": 31,
            "quality_score": 97.8,
            "metrics": [{"column_name": "email", "metric_name": "missing_percentage", "metric_value": 3.0}],
            "issues": [],
        }
        res = analyze_guest_dataset_with_gemini(fake_profile)
        assert res is not None
        assert "clean schema" in res["overall_assessment"]
        assert res["is_sample_demo"] is False
