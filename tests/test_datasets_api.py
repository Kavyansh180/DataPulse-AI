from fastapi.testclient import TestClient


def test_create_and_get_dataset(client: TestClient):
    """Test creating a dataset via API and retrieving it."""
    payload = {
        "name": "ecommerce_orders",
        "description": "Daily store transactions",
        "source_type": "s3",
    }
    response = client.post("/api/v1/datasets", json=payload)
    assert response.status_code == 201
    created = response.json()
    assert created["id"] is not None
    assert created["name"] == "ecommerce_orders"
    assert created["source_type"] == "s3"

    dataset_id = created["id"]

    # Retrieve dataset details
    get_res = client.get(f"/api/v1/datasets/{dataset_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["name"] == "ecommerce_orders"
    assert detail["versions"] == []


def test_create_duplicate_dataset_conflict(client: TestClient):
    """Test attempting to create a duplicate dataset returns 409 Conflict with structured error."""
    payload = {
        "name": "duplicate_check_dataset",
        "source_type": "csv",
    }
    res1 = client.post("/api/v1/datasets", json=payload)
    assert res1.status_code == 201

    res2 = client.post("/api/v1/datasets", json=payload)
    assert res2.status_code == 409
    error_body = res2.json()
    assert "error" in error_body
    assert error_body["error"]["code"] == "CONFLICT"
    assert "already exists" in error_body["error"]["message"]


def test_get_nonexistent_dataset_404(client: TestClient):
    """Test getting a nonexistent dataset returns 404 with structured error."""
    response = client.get("/api/v1/datasets/999999")
    assert response.status_code == 404
    error_body = response.json()
    assert "error" in error_body
    assert error_body["error"]["code"] == "NOT_FOUND"


def test_create_dataset_version(client: TestClient):
    """Test creating a version for a registered dataset."""
    # First create dataset
    d_res = client.post("/api/v1/datasets", json={"name": "analytics_events", "source_type": "s3"})
    assert d_res.status_code == 201
    dataset_id = d_res.json()["id"]

    # Now create version
    v_payload = {
        "dataset_id": dataset_id,
        "version_tag": "v1.0.0",
        "storage_uri": "s3://lake/events/v1.parquet",
        "row_count": 12500,
        "column_count": 15,
        "file_size_bytes": 524288,
    }
    v_res = client.post(f"/api/v1/datasets/{dataset_id}/versions", json=v_payload)
    assert v_res.status_code == 201
    version_data = v_res.json()
    assert version_data["version_tag"] == "v1.0.0"
    assert version_data["dataset_id"] == dataset_id

    # Verify detail shows version
    detail_res = client.get(f"/api/v1/datasets/{dataset_id}")
    assert detail_res.status_code == 200
    assert len(detail_res.json()["versions"]) == 1


def test_create_version_mismatched_id_400(client: TestClient):
    """Test that URL dataset_id mismatch with body dataset_id returns 400 Bad Request."""
    v_payload = {
        "dataset_id": 99,
        "version_tag": "v1.0.0",
        "storage_uri": "s3://lake/test.parquet",
    }
    response = client.post("/api/v1/datasets/1/versions", json=v_payload)
    assert response.status_code == 400
    error_body = response.json()
    assert error_body["error"]["code"] == "BAD_REQUEST"


def test_validation_error_structure(client: TestClient):
    """Test that invalid payload formats return 422 with structured validation error schema."""
    response = client.post("/api/v1/datasets", json={})
    assert response.status_code == 422
    body = response.json()
    assert "error" in body
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["details"], list)
    assert any("name" in err.get("field", "") for err in body["error"]["details"])
