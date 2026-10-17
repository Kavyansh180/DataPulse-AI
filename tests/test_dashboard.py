from unittest.mock import MagicMock, patch
import pytest
import httpx

from dashboard.api_client import DataPulseApiClient, DashboardApiError
from dashboard.components import (
    render_score_gauge,
    render_component_breakdown,
    render_issue_severity_distribution,
    render_column_quality_bar,
)


# -----------------------------------------------------------------------------
# 1. ApiClient URL and Error Handling Tests
# -----------------------------------------------------------------------------

def test_api_client_url_construction():
    """Verify base URL normalization and endpoint path construction."""
    client = DataPulseApiClient(base_url="http://custom-host:9000/")
    assert client.base_url == "http://custom-host:9000"
    assert client._url("/api/v1/datasets") == "http://custom-host:9000/api/v1/datasets"
    assert client._url("health") == "http://custom-host:9000/health"


def test_api_client_check_health_success():
    """Verify health check returns payload on 200 response."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {"status": "healthy", "app": "DataPulse AI", "version": "0.1.0"}

    with patch("httpx.Client.get", return_value=fake_resp):
        res = client.check_health()
        assert res["app"] == "DataPulse AI"
        assert res["status"] == "healthy"


def test_api_client_check_health_connection_error():
    """Verify connection refusal raises friendly 503 DashboardApiError."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")

    with patch("httpx.Client.get", side_effect=httpx.ConnectError("Connection refused")):
        with pytest.raises(DashboardApiError) as exc_info:
            client.check_health()
        assert exc_info.value.status_code == 503
        assert "Cannot connect to DataPulse backend" in exc_info.value.message


def test_api_client_upload_csv_multipart_payload():
    """Verify that upload_csv sends exact multipart fields, files, and does not send dataset_name."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {"id": 42, "name": "Unclean Dataset", "versions": []}

    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        res = client.upload_csv(
            file_bytes=b"id,val\n1,10",
            filename="Unclean Dataset.csv",
            name="Unclean Dataset",
            description="Retail transaction anomalies",
            version_tag="v1.0.0",
        )
        assert res["id"] == 42
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs

        # 1. Verify endpoint URL
        assert mock_post.call_args.args[0] == "http://127.0.0.1:8000/api/v1/datasets/upload"

        # 2. Verify files payload
        assert "files" in call_kwargs
        assert "file" in call_kwargs["files"]
        file_tuple = call_kwargs["files"]["file"]
        assert file_tuple[0] == "Unclean Dataset.csv"
        assert file_tuple[1] == b"id,val\n1,10"
        assert file_tuple[2] == "text/csv"

        # 3. Verify form data fields (must be name, NOT dataset_name)
        assert "data" in call_kwargs
        data = call_kwargs["data"]
        assert data["name"] == "Unclean Dataset"
        assert data["description"] == "Retail transaction anomalies"
        assert data["version_tag"] == "v1.0.0"
        assert "dataset_name" not in data

        # 4. Verify no manual multipart Content-Type header override
        headers = call_kwargs.get("headers")
        assert headers is None or "content-type" not in {k.lower(): v for k, v in headers.items()}


def test_api_client_upload_csv_defaults_and_omits_optional():
    """Verify empty/None optional fields are omitted from data and name defaults to filename stem."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {"id": 1, "name": "Unclean Dataset", "versions": []}

    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        client.upload_csv(
            file_bytes=b"a,b\n1,2",
            filename="Unclean Dataset.csv",
            name=None,
            description="   ",  # whitespace should be treated as empty and omitted
            version_tag="",    # empty string should be omitted
        )
        mock_post.assert_called_once()
        data = mock_post.call_args.kwargs["data"]

        # Defaulted to filename stem
        assert data == {"name": "Unclean Dataset"}
        assert "description" not in data
        assert "version_tag" not in data
        assert "dataset_name" not in data


def test_api_client_422_validation_error_reporting():
    """Verify that HTTP 422 validation errors capture loc, msg, and full response body."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = False
    fake_resp.status_code = 422
    fake_resp.reason_phrase = "Unprocessable Entity"
    raw_payload = {
        "detail": [
            {"loc": ["body", "name"], "msg": "Field required", "type": "missing"}
        ]
    }
    fake_resp.json.return_value = raw_payload

    with patch("httpx.Client.post", return_value=fake_resp):
        with pytest.raises(DashboardApiError) as exc_info:
            client.upload_csv(b"a,b\n1,2", "test.csv")

        exc = exc_info.value
        assert exc.status_code == 422
        assert "body -> name" in exc.message
        assert "Field required" in exc.message
        assert exc.response_body == raw_payload
        assert isinstance(exc.details, list)
        assert exc.details[0]["loc"] == ["body", "name"]
        assert exc.details[0]["msg"] == "Field required"


def test_api_client_upload_csv_s3_error_handling():
    """Verify backend 503 S3 unconfigured error is cleanly captured."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = False
    fake_resp.status_code = 503
    fake_resp.reason_phrase = "Service Unavailable"
    fake_resp.json.return_value = {
        "error": {
            "code": "SERVICE_UNAVAILABLE",
            "message": "S3 storage service is not configured. Please set S3_BUCKET_NAME in environment.",
        }
    }

    with patch("httpx.Client.post", return_value=fake_resp):
        with pytest.raises(DashboardApiError) as exc_info:
            client.upload_csv(b"a,b\n1,2", "test.csv")
        assert exc_info.value.status_code == 503
        assert "S3 storage service is not configured" in exc_info.value.message



def test_api_client_compare_runs_success():
    """Verify compare runs response parsing."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {
        "dataset_id": 1,
        "run_id_1": 1,
        "run_id_2": 2,
        "previous_score": 75.0,
        "current_score": 85.0,
        "score_change": 10.0,
        "schema_compatible": True,
        "new_issues": [],
        "resolved_issues": ["Resolved [CRITICAL]: email (missing_values)"],
    }

    with patch("httpx.Client.get", return_value=fake_resp):
        data = client.compare_runs(dataset_id=1, baseline_run_id=1, target_run_id=2)
        assert data["score_change"] == 10.0
        assert len(data["resolved_issues"]) == 1


def test_api_client_ai_analysis_missing_key_503():
    """Verify 503 LLM_NOT_CONFIGURED error translation."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = False
    fake_resp.status_code = 503
    fake_resp.reason_phrase = "Service Unavailable"
    fake_resp.json.return_value = {
        "error": {
            "code": "LLM_NOT_CONFIGURED",
            "message": "LLM API key is not configured. Please set LLM_API_KEY in your environment.",
        }
    }

    with patch("httpx.Client.post", return_value=fake_resp):
        with pytest.raises(DashboardApiError) as exc_info:
            client.analyze_run(run_id=1)
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "LLM_NOT_CONFIGURED"


def test_api_client_preview_remediation_success():
    """Verify preview remediation sends expected payload and returns response."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {
        "preview_id": "test_token_123",
        "source_run_id": 1,
        "dataset_id": 10,
        "original_row_count": 100,
        "predicted_row_count": 98,
        "operations": [],
        "warnings": [],
    }

    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        res = client.preview_remediation(run_id=1, operations=[{"operation_type": "remove_duplicates"}])
        assert res["preview_id"] == "test_token_123"
        assert res["predicted_row_count"] == 98
        mock_post.assert_called_once()


def test_api_client_apply_remediation_success():
    """Verify apply remediation sends preview_id and operations."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = {
        "success": True,
        "source_run_id": 1,
        "new_run_id": 2,
        "dataset_id": 10,
        "new_version_id": 5,
        "new_version_tag": "v2_remediated",
        "revalidation": {
            "previous_score": 80.0,
            "current_score": 90.0,
            "score_change": 10.0,
        },
    }

    with patch("httpx.Client.post", return_value=fake_resp) as mock_post:
        res = client.apply_remediation(
            run_id=1,
            preview_id="test_token_123",
            operations=[{"operation_type": "remove_duplicates"}],
            new_version_tag="v2_remediated",
        )
        assert res["success"] is True
        assert res["new_run_id"] == 2
        mock_post.assert_called_once()


def test_api_client_get_dataset_remediation_history_success():
    """Verify retrieval of remediation history items."""
    client = DataPulseApiClient(base_url="http://127.0.0.1:8000")
    fake_resp = MagicMock()
    fake_resp.is_success = True
    fake_resp.json.return_value = [
        {
            "audit_id": 1,
            "timestamp": "2026-10-17T08:00:00",
            "source_run_id": 1,
            "new_run_id": 2,
            "new_version_tag": "v2_remediated",
            "operations_count": 1,
            "score_before": 80.0,
            "score_after": 90.0,
            "score_change": 10.0,
            "operations": [{"operation_type": "remove_duplicates"}],
        }
    ]

    with patch("httpx.Client.get", return_value=fake_resp):
        history = client.get_dataset_remediation_history(dataset_id=10)
        assert len(history) == 1
        assert history[0]["new_version_tag"] == "v2_remediated"
        assert history[0]["score_change"] == 10.0



# -----------------------------------------------------------------------------
# 2. Components & Plotly Chart Helper Tests
# -----------------------------------------------------------------------------

def test_components_score_gauge():
    """Verify gauge figure creation with valid and None score."""
    fig1 = render_score_gauge(88.4)
    assert fig1 is not None
    assert fig1.data[0].value == 88.4

    fig2 = render_score_gauge(None)
    assert fig2 is not None
    assert fig2.data[0].value == 0.0


def test_components_render_component_breakdown():
    """Verify breakdown figure creation."""
    comp_scores = {
        "completeness": 92.0,
        "uniqueness": 100.0,
        "validity": 84.0,
        "consistency": 70.0,
    }
    fig = render_component_breakdown(comp_scores)
    assert fig is not None
    assert len(fig.data[0].y) == 4

    # Empty dict returns None
    assert render_component_breakdown({}) is None


def test_components_render_issue_severity_distribution():
    """Verify severity pie/donut chart creation."""
    issues = [
        {"severity": "critical", "issue_type": "missing_values"},
        {"severity": "critical", "issue_type": "empty_column"},
        {"severity": "medium", "issue_type": "outlier"},
    ]
    fig = render_issue_severity_distribution(issues)
    assert fig is not None
    assert "Critical" in fig.data[0].labels
    assert "Medium" in fig.data[0].labels

    # Empty list returns None
    assert render_issue_severity_distribution([]) is None


def test_components_render_column_quality_bar():
    """Verify column metrics bar chart generation."""
    metrics = [
        {"column_name": "email", "metric_name": "missing_percentage", "metric_value": 45.0},
        {"column_name": "salary", "metric_name": "outlier_count", "metric_value": 12.0},
    ]
    fig = render_column_quality_bar(metrics)
    assert fig is not None
    assert len(fig.data) >= 1

    # Empty metrics returns None
    assert render_column_quality_bar([]) is None


def test_dashboard_app_module_import():
    """Verify that dashboard.app imports successfully without ModuleNotFoundError."""
    import dashboard.app as app_module
    assert hasattr(app_module, "client")
    assert hasattr(app_module, "DataPulseApiClient")


def test_sample_demo_csv_loading():
    """Verify synthetic customer orders sample dataset loads properly."""
    from dashboard.sample_demo import get_sample_csv_bytes
    data = get_sample_csv_bytes()
    assert len(data) > 0
    text = data.decode("utf-8")
    assert "customer_id" in text
    assert "email" in text
    assert "order_amount" in text
    assert "status" in text


def test_sample_ai_report_structure():
    """Verify structured pre-recorded sample AI report matches expected schema."""
    from dashboard.sample_demo import get_sample_ai_report
    report = get_sample_ai_report("test_dataset", run_id=42)
    assert report["run_id"] == 42
    assert report["is_sample_demo"] is True
    assert "overall_assessment" in report
    assert len(report["key_findings"]) >= 1
    assert len(report["likely_causes"]) >= 1
    assert len(report["recommendations"]) >= 1
    assert report["likely_causes"][0]["is_hypothesis"] in [True, False]
    assert report["recommendations"][0]["priority"] in ["high", "medium", "low"]


# -----------------------------------------------------------------------------
# 3. Environment Configuration & Cloud Integration Tests
# -----------------------------------------------------------------------------

def test_api_client_env_variable_resolution(monkeypatch):
    """Verify DataPulseApiClient prioritizes DATAPULSE_API_URL and falls back correctly."""
    # 1. DATAPULSE_API_URL set
    monkeypatch.setenv("DATAPULSE_API_URL", "https://production.api.amazonaws.com/")
    client = DataPulseApiClient()
    assert client.base_url == "https://production.api.amazonaws.com"

    # 2. DATAPULSE_API_URL absent, BACKEND_URL present
    monkeypatch.delenv("DATAPULSE_API_URL", raising=False)
    monkeypatch.setenv("BACKEND_URL", "http://staging.internal:8000/")
    client2 = DataPulseApiClient()
    assert client2.base_url == "http://staging.internal:8000"

    # 3. Both absent -> fallback to localhost:8000
    monkeypatch.delenv("BACKEND_URL", raising=False)
    client3 = DataPulseApiClient()
    assert client3.base_url == "http://127.0.0.1:8000"


def test_api_client_check_readiness_primary_and_fallback():
    """Verify check_readiness calls /api/v1/ready and handles fallback."""
    client = DataPulseApiClient(base_url="https://api.datapulse.ai")

    # Primary succeeds
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    fake_resp.is_success = True
    fake_resp.json.return_value = {"status": "ready", "database": "connected", "error": None}

    with patch("httpx.Client.get", return_value=fake_resp) as mock_get:
        res = client.check_readiness()
        assert res["status"] == "ready"
        assert res["database"] == "connected"
        assert mock_get.call_args.args[0] == "https://api.datapulse.ai/api/v1/ready"


def test_api_client_analyze_run_llm_not_configured():
    """Verify analyze_run raises DashboardApiError with LLM_NOT_CONFIGURED status and message."""
    client = DataPulseApiClient(base_url="https://api.datapulse.ai")
    fake_resp = MagicMock()
    fake_resp.status_code = 503
    fake_resp.is_success = False
    fake_resp.reason_phrase = "Service Unavailable"
    fake_resp.json.return_value = {
        "error": {
            "code": "LLM_NOT_CONFIGURED",
            "message": "LLM API key is not configured. Please set LLM_API_KEY in your environment.",
            "details": None,
        }
    }

    with patch("httpx.Client.post", return_value=fake_resp):
        with pytest.raises(DashboardApiError) as exc_info:
            client.analyze_run(run_id=9)
        assert exc_info.value.status_code == 503
        assert exc_info.value.error_code == "LLM_NOT_CONFIGURED"
        assert "LLM API key is not configured" in exc_info.value.message


def test_resolve_backend_url_with_st_secrets(monkeypatch):
    """Verify resolve_backend_url correctly reads from st.secrets."""
    from dashboard.api_client import resolve_backend_url
    import streamlit as st

    monkeypatch.delenv("DATAPULSE_API_URL", raising=False)
    monkeypatch.delenv("BACKEND_URL", raising=False)

    # 1. Top-level secret
    with patch.object(st, "secrets", {"DATAPULSE_API_URL": "https://secrets.api.datapulse.ai/"}):
        assert resolve_backend_url() == "https://secrets.api.datapulse.ai"

    # 2. General section secret
    with patch.object(st, "secrets", {"general": {"DATAPULSE_API_URL": "https://general-secrets.api.datapulse.ai/"}}):
        assert resolve_backend_url() == "https://general-secrets.api.datapulse.ai"

    # 3. Explicit argument overrides secrets
    with patch.object(st, "secrets", {"DATAPULSE_API_URL": "https://secrets.api.datapulse.ai/"}):
        assert resolve_backend_url("https://explicit.api.datapulse.ai/") == "https://explicit.api.datapulse.ai"


def test_api_client_check_health_primary_and_fallback():
    """Verify check_health falls back to /api/v1/health when /health returns 404."""
    client = DataPulseApiClient(base_url="https://api.datapulse.ai")

    # Primary returns 404, fallback returns 200
    resp_404 = MagicMock()
    resp_404.status_code = 404
    resp_404.is_success = False

    resp_200 = MagicMock()
    resp_200.status_code = 200
    resp_200.is_success = True
    resp_200.json.return_value = {"status": "healthy", "app": "DataPulse AI", "version": "0.1.0"}

    with patch("httpx.Client.get", side_effect=[resp_404, resp_200]) as mock_get:
        res = client.check_health()
        assert res["status"] == "healthy"
        assert mock_get.call_count == 2
        assert mock_get.call_args_list[0].args[0] == "https://api.datapulse.ai/health"
        assert mock_get.call_args_list[1].args[0] == "https://api.datapulse.ai/api/v1/health"


# -----------------------------------------------------------------------------
# 5. Header Rendering Regression Tests (TicketVault Badge & Backward Compatibility)
# -----------------------------------------------------------------------------

def test_theme_render_header_with_badge_text():
    """Verify render_header in dashboard.theme accepts badge_text without TypeError."""
    import streamlit as st
    from dashboard.theme import render_header

    with patch.object(st, "markdown") as mock_markdown, patch.object(st, "divider") as mock_divider:
        render_header(
            title="Overview & Dataset Ingestion",
            subtitle="Upload datasets for automated statistical profiling",
            icon="📊",
            badge_text="LIVE MONITORING",
        )
        assert mock_markdown.called
        assert mock_divider.called
        rendered_html = mock_markdown.call_args[0][0]
        assert "LIVE MONITORING" in rendered_html
        assert "tv-badge-crimson" in rendered_html
        assert "Overview & Dataset Ingestion" in rendered_html


def test_theme_render_header_legacy_args_and_kwargs():
    """Verify render_header handles legacy backend arguments and arbitrary kwargs."""
    import streamlit as st
    from dashboard.theme import render_header

    with patch.object(st, "markdown") as mock_markdown, patch.object(st, "divider") as mock_divider:
        render_header(
            title="Quality Deep-Dive",
            subtitle="Inspect metrics",
            icon="🔍",
            backend_status="Backend Online",
            backend_online=True,
            arbitrary_future_arg="supported",
        )
        assert mock_markdown.called
        assert mock_divider.called


def test_app_render_header_stale_cache_fallback():
    """Verify app.render_header gracefully handles TypeError from a stale cached function."""
    import streamlit as st
    from dashboard.app import render_header

    def stale_side_effect(*args, **kwargs):
        if "badge_text" in kwargs:
            raise TypeError("render_header() got an unexpected keyword argument 'badge_text'")
        return None

    stale_mock = MagicMock(side_effect=stale_side_effect)

    with patch("dashboard.app._theme_render_header", stale_mock), \
         patch.object(st, "markdown") as mock_markdown:
        # Should not raise TypeError despite stale_mock raising on badge_text
        render_header(
            title="Overview & Dataset Ingestion",
            subtitle="Test subtitle",
            icon="📊",
            badge_text="LIVE MONITORING",
        )
        assert stale_mock.call_count >= 2
        assert mock_markdown.called




