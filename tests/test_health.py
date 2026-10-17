from unittest.mock import patch
from fastapi.testclient import TestClient


def test_health_endpoint_root(client: TestClient):
    """Verify /health returns 200 OK and application metadata."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "DataPulse AI"
    assert "version" in data
    assert "environment" in data
    assert "timestamp" in data


def test_health_endpoint_v1(client: TestClient):
    """Verify /api/v1/health responds identical to root /health."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["app"] == "DataPulse AI"


def test_ready_endpoint_healthy(client: TestClient):
    """Verify /ready returns 200 OK when database connectivity succeeds."""
    response = client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    assert data["error"] is None
    assert "timestamp" in data


def test_ready_endpoint_v1(client: TestClient):
    """Verify /api/v1/ready responds healthy."""
    response = client.get("/api/v1/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_ready_endpoint_database_failure(client: TestClient):
    """Verify /ready returns 503 Service Unavailable when the database is unreachable."""
    with patch(
        "app.api.v1.health.check_database_connectivity",
        return_value=(False, "Connection to Neon server timed out"),
    ):
        response = client.get("/ready")
        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
        assert "error" in data
        assert data["error"] == "Database connectivity check failed"


def test_root_endpoint(client: TestClient):
    """Verify root / returns API descriptor."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "DataPulse AI"
    assert data["health"] == "/health"
    assert data["ready"] == "/ready"
    assert data["docs"] == "/docs"
