import json
import logging
from unittest.mock import MagicMock, patch
import pytest
import httpx
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.dataset import Dataset, DatasetVersion
from app.models.profiling import ProfilingRun, QualityMetric
from app.models.quality_issue import QualityIssue
from app.services.ai_analysis_service import AIAnalysisService
from app.services.llm_provider import (
    OpenAICompatibleProvider,
    LLMConfigurationError,
    LLMTimeoutError,
    LLMRateLimitError,
    LLMProviderError,
    LLMResponseFormatError,
)
from app.schemas.ai_analysis import AnalysisRequest


MOCK_VALID_LLM_RESPONSE = json.dumps({
    "overall_assessment": "Dataset shows moderate quality with elevated null rates in contact fields and numeric outliers in salary.",
    "key_findings": [
        "Column 'email' has 50% missing values breaching the 5% threshold.",
        "Detected 14 IQR outliers in column 'salary' with mean 125000 exceeding median 85000.",
        "Total duplicate rows rate is 0.0% (healthy uniqueness)."
    ],
    "likely_causes": [
        {
            "cause": "Optional registration field in upstream web signup form",
            "is_hypothesis": True,
            "supporting_evidence": "email missing rate is exactly 50% across new signups"
        },
        {
            "cause": "Currency conversion discrepancy or executive compensation skew",
            "is_hypothesis": True,
            "supporting_evidence": "salary max 950000 is 10x median with 14 IQR outliers"
        }
    ],
    "recommendations": [
        {
            "action": "Enforce email collection at onboarding or set up an identity enrichment step",
            "priority": "high",
            "evidence": "email has 50% missing values"
        },
        {
            "action": "Investigate salary values exceeding 500k for currency denomination mismatches",
            "priority": "medium",
            "evidence": "14 IQR outliers detected in salary"
        }
    ],
    "limitations": [
        "Cannot verify upstream form validation rules without application source access.",
        "Downstream consumers tolerance for null emails was not evaluated."
    ]
})


@pytest.fixture
def sample_completed_run(db_session: Session) -> ProfilingRun:
    """Create a dataset, version snapshot, and completed profiling run with metrics and issues."""
    dataset = Dataset(name="hr_employees", source_type="s3", user_id=1)
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0.0",
        storage_uri="s3://datapulse-bucket/hr_employees_v1.csv",
        row_count=1000,
        column_count=5,
    )
    db_session.add(version)
    db_session.flush()

    run = ProfilingRun(
        dataset_version_id=version.id,
        status="completed",
        total_rows_profiled=1000,
        quality_score=78.5,
        summary_stats=json.dumps({
            "column_names": ["id", "name", "email", "salary", "join_date"],
            "column_count": 5,
            "row_count": 1000,
            "component_scores": {
                "completeness": 70.0,
                "uniqueness": 100.0,
                "validity": 85.0,
                "consistency": 80.0,
            },
            "penalties": ["email missing 50% (-10 pts)", "salary 14 outliers (-11.5 pts)"],
            "explanation": "Score penalized by high nulls and extreme outliers.",
            "issues_count": 2,
        }),
    )
    db_session.add(run)
    db_session.flush()

    # Add metrics
    metrics = [
        QualityMetric(
            profiling_run_id=run.id,
            metric_name="overall_quality_score",
            column_name=None,
            metric_value=78.5,
            threshold_value=70.0,
            is_anomalous=False,
        ),
        QualityMetric(
            profiling_run_id=run.id,
            metric_name="missing_percentage",
            column_name=None,
            metric_value=10.0,
            threshold_value=5.0,
            is_anomalous=True,
        ),
        QualityMetric(
            profiling_run_id=run.id,
            metric_name="missing_percentage",
            column_name="email",
            metric_value=50.0,
            threshold_value=5.0,
            is_anomalous=True,
        ),
        QualityMetric(
            profiling_run_id=run.id,
            metric_name="outlier_count",
            column_name="salary",
            metric_value=14.0,
            is_anomalous=True,
        ),
    ]
    db_session.add_all(metrics)

    # Add issues
    issues = [
        QualityIssue(
            dataset_version_id=version.id,
            rule_name="missing_values_email",
            severity="critical",
            issue_type="missing_values",
            description="Column 'email' has 50% missing values (threshold 5%).",
            status="open",
        ),
        QualityIssue(
            dataset_version_id=version.id,
            rule_name="outliers_salary",
            severity="medium",
            issue_type="outlier",
            description="Column 'salary' contains 14 IQR outliers.",
            status="open",
        ),
    ]
    db_session.add_all(issues)
    db_session.commit()
    db_session.refresh(run)
    return run


# -----------------------------------------------------------------------------
# 1. Evidence Extraction & Prompt Grounding Tests
# -----------------------------------------------------------------------------

def test_ai_analysis_evidence_preparation(db_session: Session, sample_completed_run: ProfilingRun):
    """Verify empirical evidence accurately extracts metrics, anomalies, issues, and score."""
    evidence = AIAnalysisService.prepare_evidence(sample_completed_run, db_session)

    assert evidence["run_id"] == sample_completed_run.id
    assert evidence["dataset_name"] == "hr_employees"
    assert evidence["quality_score"] == 78.5
    assert evidence["total_rows_profiled"] == 1000

    # Verify anomalies detected
    anomalies = evidence["anomalies_detected"]
    anomaly_columns = [a["column"] for a in anomalies]
    assert "email" in anomaly_columns
    assert "salary" in anomaly_columns

    # Verify issues
    issues = evidence["quality_issues"]
    assert len(issues) == 2
    assert issues[0]["severity"] == "critical"
    assert issues[0]["issue_type"] == "missing_values"

    # Verify user prompt builds without error
    req = AnalysisRequest(focus_areas=["email"], custom_context="HR Ingestion pipeline")
    prompt = AIAnalysisService.build_user_prompt(evidence, req)
    assert "Focus areas requested: email" in prompt
    assert "HR Ingestion pipeline" in prompt
    assert "hr_employees" in prompt
    assert "missing_values_email" in prompt


def test_ai_analysis_with_historical_comparison(db_session: Session, sample_completed_run: ProfilingRun):
    """Verify that prior completed runs are detected and included in evidence."""
    dataset_version = sample_completed_run.dataset_version
    dataset = dataset_version.dataset

    # Add a newer version and run
    v2 = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v2.0.0",
        storage_uri="s3://datapulse-bucket/hr_employees_v2.csv",
        row_count=1200,
        column_count=5,
    )
    db_session.add(v2)
    db_session.flush()

    run_2 = ProfilingRun(
        dataset_version_id=v2.id,
        status="completed",
        total_rows_profiled=1200,
        quality_score=85.0,
        summary_stats=json.dumps({"column_names": ["id", "name", "email", "salary", "join_date"]}),
    )
    db_session.add(run_2)
    db_session.commit()
    db_session.refresh(run_2)

    evidence = AIAnalysisService.prepare_evidence(run_2, db_session)
    comp = evidence["historical_comparison"]
    assert isinstance(comp, dict)
    assert comp["baseline_run_id"] == sample_completed_run.id
    assert comp["previous_quality_score"] == 78.5
    assert comp["current_quality_score"] == 85.0
    assert comp["score_delta"] == 6.5


# -----------------------------------------------------------------------------
# 2. Mocked LLM Success API Tests
# -----------------------------------------------------------------------------

def test_analyze_endpoint_success_mocked(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Test successful POST /api/v1/profiling/{run_id}/analyze with mocked LLM completion."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-mock-valid-key")

    mock_provider = MagicMock()
    mock_provider.generate.return_value = MOCK_VALID_LLM_RESPONSE

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(
            f"/api/v1/profiling/{sample_completed_run.id}/analyze",
            json={"focus_areas": ["email", "salary"], "custom_context": "Quarterly batch"},
        )

    assert response.status_code == 200
    data = response.json()

    assert data["run_id"] == sample_completed_run.id
    assert data["dataset_name"] == "hr_employees"
    assert data["overall_score"] == 78.5
    assert "moderate quality" in data["overall_assessment"]
    assert len(data["key_findings"]) >= 2
    assert len(data["likely_causes"]) >= 1
    assert data["likely_causes"][0]["is_hypothesis"] is True
    assert len(data["recommendations"]) >= 1
    assert data["recommendations"][0]["priority"] in ("high", "medium", "low")
    assert len(data["limitations"]) >= 1


def test_analyze_endpoint_with_markdown_fences(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify LLM output wrapped in ```json ... ``` markdown fences parses seamlessly."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-mock-valid-key")

    fenced_output = f"```json\n{MOCK_VALID_LLM_RESPONSE}\n```"
    mock_provider = MagicMock()
    mock_provider.generate.return_value = fenced_output

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")

    assert response.status_code == 200
    assert response.json()["run_id"] == sample_completed_run.id


# -----------------------------------------------------------------------------
# 3. Missing API Key & Configuration Tests
# -----------------------------------------------------------------------------

def test_analyze_endpoint_missing_api_key(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify 503 is returned when LLM_API_KEY is not configured."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", None)

    response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "LLM_NOT_CONFIGURED"
    assert "LLM_API_KEY" in error["message"]


# -----------------------------------------------------------------------------
# 4. Provider Error & Failure Handling Tests
# -----------------------------------------------------------------------------

def test_analyze_endpoint_timeout(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify 504 is returned on LLM request timeout."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = LLMTimeoutError("Request timed out after 30s")

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "LLM_TIMEOUT"


def test_analyze_endpoint_rate_limited(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify 429 is returned on LLM rate limiting."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = LLMRateLimitError("Rate limit reached")

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "LLM_RATE_LIMIT"


def test_analyze_endpoint_provider_failure(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify 502 is returned on general provider error."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    mock_provider = MagicMock()
    mock_provider.generate.side_effect = LLMProviderError("Connection refused by upstream")

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_PROVIDER_ERROR"


def test_analyze_endpoint_malformed_llm_response(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify 502 is returned when LLM response is not valid JSON."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    mock_provider = MagicMock()
    mock_provider.generate.return_value = "Sorry, I am an AI and cannot analyze this right now."

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "LLM_MALFORMED_RESPONSE"


def test_analyze_endpoint_invalid_schema_llm_response(client: TestClient, sample_completed_run: ProfilingRun, monkeypatch):
    """Verify 502 is returned when LLM response is missing required fields."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-test")

    mock_provider = MagicMock()
    mock_provider.generate.return_value = json.dumps({"unknown_field": 123})

    with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
        response = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")

    assert response.status_code == 502
    # Field overall_assessment is required
    assert response.json()["error"]["code"] in ("LLM_INVALID_SCHEMA", "LLM_MALFORMED_RESPONSE", "BAD_GATEWAY")


# -----------------------------------------------------------------------------
# 5. Route Validation & State Precondition Tests
# -----------------------------------------------------------------------------

def test_analyze_endpoint_nonexistent_run_404(client: TestClient):
    """Verify 404 is returned when profiling run does not exist."""
    response = client.post("/api/v1/profiling/99999/analyze")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


def test_analyze_endpoint_run_not_completed_400(client: TestClient, db_session: Session):
    """Verify 400 is returned when profiling run status is running or failed."""
    dataset = Dataset(name="pending_data", source_type="s3", user_id=1)
    db_session.add(dataset)
    db_session.flush()

    version = DatasetVersion(
        dataset_id=dataset.id,
        version_tag="v1.0",
        storage_uri="s3://datapulse-bucket/pending.csv",
    )
    db_session.add(version)
    db_session.flush()

    run = ProfilingRun(
        dataset_version_id=version.id,
        status="running",
    )
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)

    response = client.post(f"/api/v1/profiling/{run.id}/analyze")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RUN_NOT_COMPLETED"
    assert "Only completed runs can be analyzed" in response.json()["error"]["message"]


# -----------------------------------------------------------------------------
# 6. Secret Masking & Non-Leakage Tests
# -----------------------------------------------------------------------------

def test_ai_analysis_secrets_never_leaked(
    client: TestClient,
    sample_completed_run: ProfilingRun,
    monkeypatch,
    caplog,
):
    """Verify that sensitive API keys are NEVER printed in responses or logs."""
    SECRET_KEY = "sk-super-secret-key-that-must-never-leak-998877"
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", SECRET_KEY)

    # 1. Success case
    mock_provider = MagicMock()
    mock_provider.generate.return_value = MOCK_VALID_LLM_RESPONSE

    with caplog.at_level(logging.DEBUG):
        with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
            res_success = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")
            assert res_success.status_code == 200
            assert SECRET_KEY not in res_success.text
            assert SECRET_KEY not in caplog.text

    # 2. Error cases (timeout / provider error)
    mock_provider.generate.side_effect = LLMProviderError("Upstream connection rejected")
    with caplog.at_level(logging.DEBUG):
        with patch("app.services.ai_analysis_service.get_llm_provider", return_value=mock_provider):
            res_error = client.post(f"/api/v1/profiling/{sample_completed_run.id}/analyze")
            assert res_error.status_code == 502
            assert SECRET_KEY not in res_error.text
            assert SECRET_KEY not in caplog.text


# -----------------------------------------------------------------------------
# 7. OpenAICompatibleProvider Unit Tests
# -----------------------------------------------------------------------------

def test_openai_provider_missing_key_raises_config_error(monkeypatch):
    """Verify provider raises LLMConfigurationError if key is missing or blank."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "")
    provider = OpenAICompatibleProvider(settings=settings)

    with pytest.raises(LLMConfigurationError) as exc_info:
        provider.generate("Test prompt")
    assert "LLM_API_KEY" in str(exc_info.value)


def test_openai_provider_http_mocked_success(monkeypatch):
    """Verify provider correctly builds payload and returns message content."""
    settings = get_settings()
    monkeypatch.setattr(settings, "LLM_API_KEY", "sk-mock-key")
    provider = OpenAICompatibleProvider(settings=settings)

    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "choices": [{"message": {"content": '{"assessment": "ok"}'}}]
    }

    with patch("httpx.Client.post", return_value=fake_response) as mock_post:
        result = provider.generate("Analyze this", system_prompt="System prompt")
        assert result == '{"assessment": "ok"}'
        assert mock_post.called
        call_kwargs = mock_post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer sk-mock-key"
        assert call_kwargs["json"]["model"] == settings.LLM_MODEL
