import io
import pytest
from fastapi.testclient import TestClient


def test_upload_csv_dataset_api(client: TestClient):
    """Verify multipart/form-data CSV upload creates dataset, version, and runs profiling."""
    csv_content = (
        b"id,customer_name,email,spend,signup_date\n"
        b"1,Alice,alice@example.com,120.50,2026-01-10\n"
        b"2,Bob,bob@example.com,250.00,2026-02-15\n"
        b"3,Charlie,charlie@example.com,85.25,2026-03-01\n"
    )

    response = client.post(
        "/api/v1/datasets/upload",
        data={"name": "retail_customers", "description": "Retail customer transaction records"},
        files={"file": ("customers.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "retail_customers"
    assert len(data["versions"]) == 1
    assert data["versions"][0]["row_count"] == 3
    assert data["versions"][0]["column_count"] == 5

    dataset_id = data["id"]

    # Verify profiling run was created
    runs_res = client.get(f"/api/v1/datasets/{dataset_id}/runs")
    assert runs_res.status_code == 200
    runs = runs_res.json()
    assert len(runs) == 1
    assert runs[0]["status"] == "completed"
    assert runs[0]["quality_score"] == 100.0

    run_id = runs[0]["id"]

    # Verify run summary endpoint
    summary_res = client.get(f"/api/v1/profiling/{run_id}/summary")
    assert summary_res.status_code == 200
    summary = summary_res.json()
    assert summary["run_id"] == run_id
    assert summary["quality_score"] == 100.0
    assert "completeness" in summary["component_scores"]

    # Verify metrics endpoint
    metrics_res = client.get(f"/api/v1/profiling/{run_id}/metrics")
    assert metrics_res.status_code == 200
    assert len(metrics_res.json()) > 0

    # Verify metrics filtered by column
    col_metrics_res = client.get(f"/api/v1/profiling/{run_id}/metrics?column_name=spend")
    assert col_metrics_res.status_code == 200
    assert all(m["column_name"] == "spend" for m in col_metrics_res.json())

    # Verify issues endpoint
    issues_res = client.get(f"/api/v1/profiling/{run_id}/issues")
    assert issues_res.status_code == 200


def test_upload_invalid_file_extension(client: TestClient):
    """Verify uploading a non-CSV file returns 400 Bad Request."""
    response = client.post(
        "/api/v1/datasets/upload",
        data={"name": "malicious_upload"},
        files={"file": ("malicious.sh", io.BytesIO(b"echo hello"), "application/x-sh")},
    )
    assert response.status_code == 400
    error_body = response.json()
    assert error_body["error"]["code"] == "UNSUPPORTED_FILE_TYPE"


def test_upload_empty_csv(client: TestClient):
    """Verify uploading an empty CSV returns 400 EMPTY_FILE."""
    response = client.post(
        "/api/v1/datasets/upload",
        data={"name": "empty_upload"},
        files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
    )
    assert response.status_code == 400
    error_body = response.json()
    assert error_body["error"]["code"] == "EMPTY_FILE"


def test_upload_duplicate_column_headers(client: TestClient):
    """Verify uploading CSV with duplicate column names returns 400 DUPLICATE_COLUMNS."""
    bad_csv = b"id,val,id\n1,10,1\n2,20,2"
    response = client.post(
        "/api/v1/datasets/upload",
        data={"name": "duplicate_header_dataset"},
        files={"file": ("dup.csv", io.BytesIO(bad_csv), "text/csv")},
    )
    assert response.status_code == 400
    error_body = response.json()
    assert error_body["error"]["code"] == "DUPLICATE_COLUMNS"


def test_compare_runs_api(client: TestClient):
    """Verify comparing two runs via both profiling compare and dataset compare-runs endpoints."""
    # Upload run 1
    csv1 = b"id,val\n1,10\n2,None\n"
    res1 = client.post(
        "/api/v1/datasets/upload",
        data={"name": "comparison_test_dataset", "version_tag": "v1.0.0"},
        files={"file": ("v1.csv", io.BytesIO(csv1), "text/csv")},
    )
    assert res1.status_code == 201
    dataset_id = res1.json()["id"]

    # Upload run 2
    csv2 = b"id,val\n1,10\n2,20\n"
    res2 = client.post(
        "/api/v1/datasets/upload",
        data={"name": "comparison_test_dataset", "version_tag": "v2.0.0"},
        files={"file": ("v2.csv", io.BytesIO(csv2), "text/csv")},
    )
    assert res2.status_code == 201

    runs_res = client.get(f"/api/v1/datasets/{dataset_id}/runs")
    runs = runs_res.json()
    assert len(runs) == 2

    run_1_id = runs[1]["id"]
    run_2_id = runs[0]["id"]

    # 1. Compare via /api/v1/profiling/compare
    cmp_res1 = client.get(f"/api/v1/profiling/compare?run_id_1={run_1_id}&run_id_2={run_2_id}")
    assert cmp_res1.status_code == 200
    comp1 = cmp_res1.json()
    assert comp1["dataset_id"] == dataset_id
    assert comp1["run_id_1"] == run_1_id
    assert comp1["run_id_2"] == run_2_id
    assert comp1["schema_compatible"] is True

    # 2. Compare via /api/v1/datasets/{id}/compare-runs
    cmp_res2 = client.get(f"/api/v1/datasets/{dataset_id}/compare-runs?run_id_1={run_1_id}&run_id_2={run_2_id}")
    assert cmp_res2.status_code == 200
    comp2 = cmp_res2.json()
    assert comp2["dataset_id"] == dataset_id
