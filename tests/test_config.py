from app.core.config import Settings


def test_default_settings():
    """Verify default configuration attributes."""
    settings = Settings(DATABASE_URL="sqlite:///:memory:")
    assert settings.APP_NAME == "DataPulse AI"
    assert settings.API_V1_PREFIX == "/api/v1"
    assert settings.PORT == 8000
    assert settings.is_sqlite is True


def test_postgres_url_normalization():
    """Verify legacy postgres:// URI scheme is normalized to postgresql:// for SQLAlchemy 2.x."""
    raw_neon_url = "postgres://neondb_owner:npg_secret123@ep-sample-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require"
    settings = Settings(DATABASE_URL=raw_neon_url)

    assert settings.DATABASE_URL.startswith("postgresql://")
    assert "neondb_owner:npg_secret123" in settings.DATABASE_URL
    assert "ep-sample-pooler.us-east-2.aws.neon.tech" in settings.DATABASE_URL
    assert "sslmode=require" in settings.DATABASE_URL
    assert settings.is_sqlite is False


def test_postgresql_url_unchanged():
    """Verify postgresql:// URLs are preserved without mutation."""
    standard_url = "postgresql://user:pass@localhost:5432/datapulse"
    settings = Settings(DATABASE_URL=standard_url)
    assert settings.DATABASE_URL == standard_url
    assert settings.is_sqlite is False


def test_custom_pool_settings():
    """Verify connection pool customization."""
    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        DB_POOL_SIZE=15,
        DB_MAX_OVERFLOW=20,
        DB_POOL_TIMEOUT=45,
        DB_POOL_RECYCLE=3600,
    )
    assert settings.DB_POOL_SIZE == 15
    assert settings.DB_MAX_OVERFLOW == 20
    assert settings.DB_POOL_TIMEOUT == 45
    assert settings.DB_POOL_RECYCLE == 3600


def test_ssm_parameter_store_loading(monkeypatch):
    """Verify runtime credential loading from AWS SSM Parameter Store."""
    import boto3
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.get_parameters_by_path.return_value = {
        "Parameters": [
            {
                "Name": "/datapulse/production/DATABASE_URL",
                "Value": "postgres://user:pass@ep-pooler.ap-south-1.aws.neon.tech/neondb?sslmode=require",
            },
            {
                "Name": "/datapulse/production/LLM_API_KEY",
                "Value": "sk-mocked-ssm-key-12345",
            },
        ]
    }

    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: mock_client)

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SSM_PARAMETER_PATH="/datapulse/production",
    )
    settings.load_ssm_parameters()

    assert settings.DATABASE_URL.startswith("postgresql://")
    assert "ep-pooler.ap-south-1.aws.neon.tech" in settings.DATABASE_URL
    assert settings.LLM_API_KEY == "sk-mocked-ssm-key-12345"
    mock_client.get_parameters_by_path.assert_called_once_with(
        Path="/datapulse/production",
        Recursive=True,
        WithDecryption=True,
    )


def test_secrets_manager_loading(monkeypatch):
    """Verify runtime credential loading from AWS Secrets Manager."""
    import boto3
    import json
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.get_secret_value.return_value = {
        "SecretString": json.dumps({
            "DATABASE_URL": "postgresql://sm_user:sm_pass@ep-sm-pooler.ap-south-1.aws.neon.tech/neondb?sslmode=require",
            "LLM_API_KEY": "sk-mocked-sm-key-67890",
        })
    }

    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: mock_client)

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SECRETS_MANAGER_SECRET_ID="datapulse/production/secrets",
    )
    settings.load_secrets_manager_secrets()

    assert "ep-sm-pooler.ap-south-1.aws.neon.tech" in settings.DATABASE_URL
    assert settings.LLM_API_KEY == "sk-mocked-sm-key-67890"
    mock_client.get_secret_value.assert_called_once_with(
        SecretId="datapulse/production/secrets"
    )


def test_cloud_secret_loading_graceful_fallback(monkeypatch):
    """Verify application gracefully falls back without crashing when AWS calls fail."""
    import boto3
    from unittest.mock import MagicMock

    mock_client = MagicMock()
    mock_client.get_parameters_by_path.side_effect = Exception("AWS AccessDeniedException")
    mock_client.get_secret_value.side_effect = Exception("AWS ResourceNotFoundException")

    monkeypatch.setattr(boto3, "client", lambda service, **kwargs: mock_client)

    settings = Settings(
        DATABASE_URL="sqlite:///:memory:",
        SSM_PARAMETER_PATH="/datapulse/production",
        SECRETS_MANAGER_SECRET_ID="datapulse/production/secrets",
    )
    # Should not raise any exceptions
    settings.load_ssm_parameters()
    settings.load_secrets_manager_secrets()

    assert settings.DATABASE_URL == "sqlite:///:memory:"

