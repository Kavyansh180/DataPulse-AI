import json
from typing import Tuple
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dataset import Dataset, DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.models.audit_log import AuditLog
from app.schemas.remediation import (
    RemediationOperation,
    RemediationPreviewRequest,
    RemediationApplyRequest,
)
from app.services.remediation_service import RemediationService
from app.api.errors import APIError


@pytest.fixture
def sample_remediation_dataset(db_session: Session) -> Tuple[Dataset, DatasetVersion, ProfilingRun, bytes]:
    """Create a dataset with messy data, completed profiling run, and raw CSV bytes."""
    raw_csv = (
        "id,name,email,salary,status\n"
        "1,  Alice  ,,100000,active\n"
        "2,Bob,bob@corp.com,90000,active\n"
        "2,Bob,bob@corp.com,90000,active\n"  # Duplicate row
        "3,Charlie,charlie@corp.com,1500000,pending\n"  # Outlier salary
        "4,Diana,diana@corp.com,,inactive\n"
        "5,Evan,evan@corp.com,85000,   \n"  # Whitespace-only status
    ).encode("utf-8")

    dataset = Dataset(name="hr_remediation_demo", source_type="s3", user_id=1)
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0.0",
        storage_uri="s3://datapulse-bucket/hr_raw.csv",
        row_count=6,
        column_count=5,
    )
    db_session.add(version)
    db_session.flush()

    run = ProfilingRun(
        dataset_version_id=version.id,
        status="completed",
        total_rows_profiled=6,
        quality_score=68.0,
        summary_stats=json.dumps({
            "column_names": ["id", "name", "email", "salary", "status"],
            "column_count": 5,
            "row_count": 6,
            "component_scores": {"completeness": 60.0, "uniqueness": 80.0, "validity": 70.0, "consistency": 60.0},
        }),
    )
    db_session.add(run)
    db_session.flush()

    # Add issues
    issue1 = QualityIssue(
        dataset_version_id=version.id,
        rule_name="duplicate_rows",
        severity="medium",
        issue_type="duplicate_rows",
        description="Dataset contains duplicate rows.",
        status="open",
    )
    issue2 = QualityIssue(
        dataset_version_id=version.id,
        rule_name="missing_values_email",
        severity="high",
        issue_type="missing_values",
        description="Column 'email' has missing values.",
        status="open",
    )
    db_session.add_all([issue1, issue2])
    db_session.commit()
    db_session.refresh(run)

    return dataset, version, run, raw_csv


# -----------------------------------------------------------------------------
# 1. Operation Simulation Unit Tests
# -----------------------------------------------------------------------------

def test_missing_values_imputation_numeric_and_categorical():
    """Verify mean, median, constant, and mode strategies for missing values."""
    df = pd.DataFrame({
        "num": [10.0, 20.0, np.nan, 30.0],
        "cat": ["A", "B", np.nan, "A"],
    })

    # 1. Constant numeric
    ops_const = [RemediationOperation(operation_type="fill_missing", column="num", strategy="constant", fill_value=0.0)]
    res_df, previews, diffs, _ = RemediationService.simulate_operations(df, ops_const)
    assert res_df.loc[2, "num"] == 0.0
    assert previews[0].affected_rows == 1
    assert len(diffs) == 1

    # 2. Mean numeric
    ops_mean = [RemediationOperation(operation_type="fill_missing", column="num", strategy="mean")]
    res_df, _, _, _ = RemediationService.simulate_operations(df, ops_mean)
    assert res_df.loc[2, "num"] == 20.0  # mean of (10 + 20 + 30)/3 = 20.0

    # 3. Mode categorical
    ops_mode = [RemediationOperation(operation_type="fill_missing", column="cat", strategy="mode")]
    res_df, _, _, _ = RemediationService.simulate_operations(df, ops_mode)
    assert res_df.loc[2, "cat"] == "A"


def test_missing_values_incompatible_strategy_raises_error():
    """Verify requesting mean/median on a text column raises validation error."""
    df = pd.DataFrame({"name": ["Alice", "Bob", None]})
    ops = [RemediationOperation(operation_type="fill_missing", column="name", strategy="mean")]

    with pytest.raises(APIError) as exc_info:
        RemediationService.simulate_operations(df, ops)
    assert exc_info.value.status_code == 400
    assert "Cannot compute mean on non-numeric column" in exc_info.value.message


def test_duplicate_removal_preserves_first_occurrence():
    """Verify duplicate row detection and removal preserving first row."""
    df = pd.DataFrame({
        "id": [1, 2, 2, 3],
        "name": ["A", "B", "B", "C"],
    })
    ops = [RemediationOperation(operation_type="drop_duplicates")]
    res_df, previews, diffs, _ = RemediationService.simulate_operations(df, ops)

    assert len(res_df) == 3
    assert previews[0].affected_rows == 1
    assert list(res_df["id"]) == [1, 2, 3]


def test_whitespace_trimming_and_empty_to_null():
    """Verify whitespace trimming and empty string normalization to NULL."""
    df = pd.DataFrame({
        "name": ["  Alice  ", "Bob\t", "   "],
    })
    ops = [
        RemediationOperation(
            operation_type="trim_whitespace",
            column="name",
            empty_string_to_null=True,
        )
    ]
    res_df, previews, diffs, _ = RemediationService.simulate_operations(df, ops)

    assert res_df.loc[0, "name"] == "Alice"
    assert res_df.loc[1, "name"] == "Bob"
    assert pd.isna(res_df.loc[2, "name"])


def test_type_conversion_reject_policy():
    """Verify unconvertible values cause rejection when failure_policy='reject'."""
    df = pd.DataFrame({"age": ["25", "30", "invalid_age", "40"]})
    ops = [
        RemediationOperation(
            operation_type="convert_type",
            column="age",
            target_type="integer",
            failure_policy="reject",
        )
    ]

    with pytest.raises(APIError) as exc_info:
        RemediationService.simulate_operations(df, ops)
    assert exc_info.value.status_code == 400
    assert "values cannot be converted" in exc_info.value.message


def test_type_conversion_coerce_policy():
    """Verify unconvertible values are coerced to null with a warning when failure_policy='coerce'."""
    df = pd.DataFrame({"age": ["25", "30", "invalid_age", "40"]})
    ops = [
        RemediationOperation(
            operation_type="convert_type",
            column="age",
            target_type="integer",
            failure_policy="coerce",
        )
    ]
    res_df, previews, diffs, _ = RemediationService.simulate_operations(df, ops)

    assert pd.isna(res_df.loc[2, "age"])
    assert res_df.loc[0, "age"] == 25
    assert len(previews[0].warnings) >= 1


def test_outlier_capping():
    """Verify numeric outlier capping at lower and upper bounds."""
    df = pd.DataFrame({"val": [5.0, 50.0, 100.0, 500.0]})
    ops = [
        RemediationOperation(
            operation_type="cap_outliers",
            column="val",
            lower_bound=10.0,
            upper_bound=200.0,
        )
    ]
    res_df, previews, diffs, _ = RemediationService.simulate_operations(df, ops)

    assert res_df.loc[0, "val"] == 10.0  # 5.0 capped to 10.0
    assert res_df.loc[3, "val"] == 200.0  # 500.0 capped to 200.0
    assert previews[0].affected_rows == 2


# -----------------------------------------------------------------------------
# 2. Preview & Token Integrity Tests
# -----------------------------------------------------------------------------

def test_preview_token_generation_and_tamper_detection():
    """Verify preview token signature and rejection of mismatched runs or operations."""
    ops1 = [RemediationOperation(operation_type="drop_duplicates")]
    token1 = RemediationService.generate_preview_token(run_id=1, operations=ops1)

    # Valid check passes
    RemediationService.verify_preview_token(token1, run_id=1, operations=ops1)

    # Mismatched run ID fails
    with pytest.raises(APIError) as exc_info:
        RemediationService.verify_preview_token(token1, run_id=2, operations=ops1)
    assert exc_info.value.code == "PREVIEW_MISMATCH"

    # Mismatched operations fail
    ops2 = [RemediationOperation(operation_type="fill_missing", column="salary", strategy="mean")]
    with pytest.raises(APIError) as exc_info2:
        RemediationService.verify_preview_token(token1, run_id=1, operations=ops2)
    assert exc_info2.value.code == "PREVIEW_MISMATCH"


def test_preview_leaves_source_data_unchanged(sample_remediation_dataset, db_session: Session):
    """Verify preview generates diffs without touching source CSV or database records."""
    _, _, run, raw_csv = sample_remediation_dataset

    with patch("app.services.s3_service.S3Service.download_file_bytes", return_value=raw_csv):
        ops = [
            RemediationOperation(operation_type="drop_duplicates"),
            RemediationOperation(operation_type="fill_missing", column="email", strategy="constant", fill_value="unknown@corp.com"),
        ]
        preview_res = RemediationService.preview_remediation(db_session, run.id, ops)

    assert preview_res.total_rows_before == 6
    assert preview_res.total_rows_after == 5  # 1 duplicate dropped
    assert len(preview_res.operations) == 2
    assert len(preview_res.sample_diffs) >= 2

    # Assert source database run is untouched
    db_session.refresh(run)
    assert run.total_rows_profiled == 6
    assert run.quality_score == 68.0


# -----------------------------------------------------------------------------
# 3. Application, S3 Artifact Storage, and Revalidation Tests
# -----------------------------------------------------------------------------

def test_remediation_apply_and_revalidation_workflow(
    sample_remediation_dataset,
    db_session: Session,
    monkeypatch,
):
    """Verify full apply flow: corrected CSV uploaded, new DatasetVersion created, revalidation run executed."""
    dataset, orig_version, run, raw_csv = sample_remediation_dataset

    settings = get_settings()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "mock-remediation-bucket")

    mock_uploaded_data = {}

    def mock_upload(file_bytes, object_key, content_type="text/csv"):
        mock_uploaded_data["key"] = object_key
        mock_uploaded_data["bytes"] = file_bytes
        return f"s3://mock-remediation-bucket/{object_key}"

    with patch("app.services.s3_service.S3Service.download_file_bytes", return_value=raw_csv):
        with patch("app.services.s3_service.S3Service.upload_file_bytes", side_effect=mock_upload):
            ops = [
                RemediationOperation(operation_type="drop_duplicates"),
                RemediationOperation(operation_type="fill_missing", column="email", strategy="constant", fill_value="default@corp.com"),
                RemediationOperation(operation_type="cap_outliers", column="salary", lower_bound=0.0, upper_bound=200000.0),
            ]
            preview_token = RemediationService.generate_preview_token(run.id, ops)

            apply_res = RemediationService.apply_remediation(
                db=db_session,
                run_id=run.id,
                preview_id=preview_token,
                operations=ops,
                new_version_tag="v1.1.0_clean",
            )

    # 1. Assertions on response
    assert apply_res.source_run_id == run.id
    assert apply_res.new_run_id != run.id
    assert apply_res.new_version_tag == "v1.1.0_clean"
    assert apply_res.rows_before == 6
    assert apply_res.rows_after == 5
    assert apply_res.score_improvement > 0.0  # Quality score improved after fixing nulls, duplicates, and outliers!

    # 2. Source version must remain intact
    db_session.refresh(orig_version)
    assert orig_version.version_tag == "v1.0.0"
    assert orig_version.row_count == 6

    # 3. New version exists in database
    new_version = db_session.get(DatasetVersion, apply_res.new_dataset_version_id)
    assert new_version is not None
    assert new_version.row_count == 5
    assert new_version.dataset_id == dataset.id

    # 4. Audit log entry recorded
    audit_logs = db_session.query(AuditLog).filter_by(action="remediation_applied").all()
    assert len(audit_logs) >= 1
    assert "source_run_id" in audit_logs[0].details


def test_remediation_s3_unconfigured_raises_503(
    sample_remediation_dataset,
    db_session: Session,
    monkeypatch,
):
    """Verify that applying remediation without S3 configured returns clear 503 error."""
    _, _, run, raw_csv = sample_remediation_dataset
    settings = get_settings()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", None)

    ops = [RemediationOperation(operation_type="drop_duplicates")]
    token = RemediationService.generate_preview_token(run.id, ops)

    with patch("app.services.s3_service.S3Service.download_file_bytes", return_value=raw_csv):
        with pytest.raises(APIError) as exc_info:
            RemediationService.apply_remediation(db_session, run.id, token, ops)

    assert exc_info.value.status_code == 503
    assert "S3_BUCKET_NAME" in exc_info.value.message


# -----------------------------------------------------------------------------
# 4. REST API Endpoint Integration Tests
# -----------------------------------------------------------------------------

def test_api_remediation_preview_and_apply(
    client: TestClient,
    sample_remediation_dataset,
    monkeypatch,
):
    """Test POST /remediation/preview, POST /remediation/apply, and GET /remediation-history."""
    dataset, _, run, raw_csv = sample_remediation_dataset
    settings = get_settings()
    monkeypatch.setattr(settings, "S3_BUCKET_NAME", "mock-test-bucket")

    with patch("app.services.s3_service.S3Service.download_file_bytes", return_value=raw_csv):
        with patch("app.services.s3_service.S3Service.upload_file_bytes", return_value="s3://mock-test-bucket/safe.csv"):

            # 1. Preview request
            preview_payload = {
                "operations": [
                    {"operation_type": "drop_duplicates"},
                    {"operation_type": "fill_missing", "column": "email", "strategy": "constant", "fill_value": "fixed@corp.com"},
                ]
            }
            res_preview = client.post(f"/api/v1/profiling/{run.id}/remediation/preview", json=preview_payload)
            assert res_preview.status_code == 200
            preview_data = res_preview.json()
            assert "preview_id" in preview_data
            assert preview_data["total_rows_after"] == 5

            # 2. Apply request
            apply_payload = {
                "preview_id": preview_data["preview_id"],
                "operations": preview_payload["operations"],
                "new_version_tag": "v1.0.0_remediated",
            }
            res_apply = client.post(f"/api/v1/profiling/{run.id}/remediation/apply", json=apply_payload)
            assert res_apply.status_code == 201
            apply_data = res_apply.json()
            assert apply_data["remediated_score"] > apply_data["original_score"]
            assert apply_data["new_version_tag"] == "v1.0.0_remediated"

            # 3. History request
            res_hist = client.get(f"/api/v1/datasets/{dataset.id}/remediation-history")
            assert res_hist.status_code == 200
            hist_list = res_hist.json()
            assert len(hist_list) >= 1
            assert hist_list[0]["version_tag"] == "v1.0.0_remediated"


def test_api_remediation_invalid_run_404(client: TestClient):
    """Verify 404 for non-existent run on preview."""
    res = client.post(
        "/api/v1/profiling/999999/remediation/preview",
        json={"operations": [{"operation_type": "drop_duplicates"}]},
    )
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "NOT_FOUND"


def test_api_remediation_incomplete_run_400(client: TestClient, db_session: Session):
    """Verify 400 for profiling run that is not completed."""
    dataset = Dataset(name="pending_dataset", source_type="s3", user_id=1)
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(dataset_id=dataset.id, version_tag="v1.0", storage_uri="s3://b/pending.csv")
    db_session.add(version)
    db_session.flush()

    run = ProfilingRun(dataset_version_id=version.id, status="running")
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    res = client.post(
        f"/api/v1/profiling/{run.id}/remediation/preview",
        json={"operations": [{"operation_type": "drop_duplicates"}]},
    )
    assert res.status_code == 400
    assert res.json()["error"]["code"] == "RUN_NOT_COMPLETED"
