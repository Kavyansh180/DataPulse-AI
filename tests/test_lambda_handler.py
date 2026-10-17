import pytest
from app.lambda_handler import handler
from app.core.config import Settings
from fastapi.testclient import TestClient
from app.main import create_application


def test_lambda_handler_initialization():
    """Verify that Mangum handler is initialized and callable."""
    assert handler is not None
    assert callable(handler)


def test_lambda_handler_health_invocation():
    """Verify Mangum processes an API Gateway HTTP API v2 event for /health."""
    apigw_v2_event = {
        "version": "2.0",
        "routeKey": "GET /health",
        "rawPath": "/health",
        "rawQueryString": "",
        "headers": {
            "accept": "application/json",
            "host": "api.datapulse.local",
        },
        "requestContext": {
            "http": {
                "method": "GET",
                "path": "/health",
                "protocol": "HTTP/1.1",
                "sourceIp": "127.0.0.1",
                "userAgent": "pytest-client",
            },
        },
        "isBase64Encoded": False,
    }

    response = handler(apigw_v2_event, {})
    assert response["statusCode"] == 200
    assert "application/json" in response["headers"]["content-type"]
    assert '"status":"healthy"' in response["body"] or '"healthy"' in response["body"]


def test_cors_headers_with_wildcard(client: TestClient):
    """Verify CORS response headers when ALLOWED_ORIGINS contains wildcard."""
    res = client.get("/health", headers={"Origin": "http://localhost:3000"})
    assert res.status_code == 200
    assert res.headers.get("access-control-allow-origin") == "*"


def test_cors_headers_with_explicit_origin():
    """Verify CORS response headers when explicit origins are configured."""
    custom_settings = Settings(
        ALLOWED_ORIGINS=["https://dashboard.example.com", "http://localhost:8501"]
    )
    # create app with custom settings
    app_with_cors = create_application(custom_settings=custom_settings)
    with TestClient(app_with_cors) as explicit_client:
        # Preflight OPTIONS request
        res = explicit_client.options(
            "/api/v1/datasets",
            headers={
                "Origin": "https://dashboard.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert res.status_code == 200
        assert res.headers.get("access-control-allow-origin") == "https://dashboard.example.com"
        assert res.headers.get("access-control-allow-credentials") == "true"


def test_allowed_origins_string_parsing():
    """Verify ALLOWED_ORIGINS correctly parses comma-separated string input."""
    s = Settings(ALLOWED_ORIGINS="https://app.streamlit.app, http://localhost:8501")
    assert s.ALLOWED_ORIGINS == ["https://app.streamlit.app", "http://localhost:8501"]

    s_empty = Settings(ALLOWED_ORIGINS="")
    assert s_empty.ALLOWED_ORIGINS == ["*"]


def test_cors_disabled_when_flag_false():
    """Verify CORS middleware is skipped when ENABLE_CORS_MIDDLEWARE is False."""
    custom_settings = Settings(
        ALLOWED_ORIGINS=["https://dashboard.example.com"],
        ENABLE_CORS_MIDDLEWARE=False,
    )
    app_no_cors = create_application(custom_settings=custom_settings)
    with TestClient(app_no_cors) as client_no_cors:
        res = client_no_cors.get("/health", headers={"Origin": "https://dashboard.example.com"})
        assert res.status_code == 200
        # When CORS middleware is disabled, FastAPI does NOT append Access-Control-Allow-Origin,
        # allowing API Gateway HTTP API v2 to be the single source of truth without duplicates!
        assert "access-control-allow-origin" not in res.headers

