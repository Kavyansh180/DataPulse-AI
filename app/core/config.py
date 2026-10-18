from functools import lru_cache
from typing import Optional, List, Any
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings managed via environment variables.

    Reads from system environment and optional .env file.
    Designed for production safety: credentials must be passed via environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # General App Settings
    APP_NAME: str = Field(default="DataPulse AI", description="Application display name")
    APP_VERSION: str = Field(default="0.1.0", description="Application semantic version")
    ENVIRONMENT: str = Field(default="development", description="Runtime environment (development, staging, production)")
    DEBUG: bool = Field(default=True, description="Enable debug mode")
    API_V1_PREFIX: str = Field(default="/api/v1", description="URL prefix for v1 endpoints")
    HOST: str = Field(default="0.0.0.0", description="Server host binding")
    PORT: int = Field(default=8000, description="Server port binding")

    # CORS Configuration
    ALLOWED_ORIGINS: Any = Field(
        default_factory=lambda: ["*"],
        description="Allowed CORS origins list or comma-separated string",
    )
    ENABLE_CORS_MIDDLEWARE: bool = Field(
        default=True,
        description="Enable FastAPI CORSMiddleware. Set to False when CORS is terminated at API Gateway to prevent duplicate headers.",
    )

    # AWS Systems Manager (SSM) Parameter Store & Secrets Manager Integration
    SSM_PARAMETER_PATH: Optional[str] = Field(
        default=None,
        description="Optional SSM Parameter Store path prefix (e.g., /datapulse/production) for fetching secure credentials at runtime.",
    )
    SECRETS_MANAGER_SECRET_ID: Optional[str] = Field(
        default=None,
        description="Optional AWS Secrets Manager secret ID or ARN (e.g., datapulse/production/secrets) for fetching secure credentials at runtime.",
    )

    # Ingestion & Profiling Limits
    MAX_UPLOAD_SIZE_BYTES: int = Field(default=50 * 1024 * 1024, description="Maximum CSV upload size (50MB)")
    MAX_ROW_COUNT_LIMIT: int = Field(default=1_000_000, description="Maximum rows allowed for profiling")

    # Amazon S3 Storage Configuration
    AWS_REGION: str = Field(default="ap-south-1", description="AWS Region for Amazon S3 and SSM")
    S3_BUCKET_NAME: Optional[str] = Field(default=None, description="Amazon S3 bucket for dataset storage")
    S3_ENDPOINT_URL: Optional[str] = Field(default=None, description="Custom S3 endpoint URL (MinIO/LocalStack/testing)")

    # AI Root-Cause Analysis (LLM Integration)
    LLM_PROVIDER: str = Field(default="openai", description="LLM provider name (e.g., gemini, openai, groq, generic)")
    LLM_API_KEY: Optional[str] = Field(default=None, description="API key for generic/OpenAI LLM provider")
    GEMINI_API_KEY: Optional[str] = Field(default=None, description="Dedicated Google Gemini API key")
    LLM_MODEL: str = Field(default="gemini-3.8-flash", description="LLM model name to invoke (e.g., gemini-3.8-flash, gpt-4o-mini)")
    LLM_API_BASE: Optional[str] = Field(default=None, description="Custom base URL for LLM API (e.g., OpenAI/Groq/OpenRouter)")
    LLM_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1.0, le=120.0, description="Request timeout for LLM calls in seconds")

    # JWT & Authentication Configuration
    JWT_SECRET_KEY: str = Field(
        default="datapulse-dev-secret-key-minimum-32-chars-long-for-testing-only-123456789",
        description="Cryptographic secret key for signing JWT access tokens (minimum 32 characters)",
    )
    JWT_ALGORITHM: str = Field(
        default="HS256",
        description="Cryptographic signing algorithm for JWT access tokens",
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        ge=5,
        le=1440,
        description="JWT access token lifetime in minutes",
    )

    # Database Configuration (PostgreSQL on Neon / or SQLite fallback for tests)
    DATABASE_URL: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/datapulse",
        description="Database connection URL",
    )

    # Connection Pool Settings
    DB_POOL_SIZE: int = Field(default=5, ge=1, le=50, description="SQLAlchemy connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, ge=0, le=100, description="Maximum overflow connections")
    DB_POOL_TIMEOUT: int = Field(default=30, ge=1, description="Seconds to wait before timing out on pool")
    DB_POOL_RECYCLE: int = Field(default=1800, ge=60, description="Recycle connections every N seconds")

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, v: Any) -> List[str]:
        """Parse comma-separated string into a list of allowed origins."""
        if isinstance(v, str):
            clean = v.strip()
            if not clean:
                return ["*"]
            return [origin.strip() for origin in clean.split(",") if origin.strip()]
        elif isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return ["*"]

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, v: Optional[str]) -> str:
        """Normalize database URLs.

        Neon and Heroku often provide 'postgres://' URIs. SQLAlchemy 2.0 requires
        'postgresql://'. This validator safely normalizes the scheme.
        """
        if not v or not isinstance(v, str):
            return "postgresql://postgres:postgres@localhost:5432/datapulse"

        url = v.strip()
        # Normalize legacy postgres:// scheme to postgresql://
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        return url

    @property
    def is_sqlite(self) -> bool:
        """Check if current database is SQLite (e.g., in unit tests)."""
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def effective_gemini_api_key(self) -> Optional[str]:
        """Resolve Gemini API key: checks GEMINI_API_KEY first, falls back to LLM_API_KEY."""
        return self.GEMINI_API_KEY or self.LLM_API_KEY

    def load_ssm_parameters(self) -> None:
        """Fetch secure credentials from AWS SSM Parameter Store if SSM_PARAMETER_PATH is set."""
        if not self.SSM_PARAMETER_PATH or not self.SSM_PARAMETER_PATH.strip():
            return

        try:
            import boto3
            import os
            region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or self.AWS_REGION
            ssm_client = boto3.client("ssm", region_name=region)
            response = ssm_client.get_parameters_by_path(
                Path=self.SSM_PARAMETER_PATH.strip(),
                Recursive=True,
                WithDecryption=True,
            )
            for param in response.get("Parameters", []):
                param_name = param["Name"].rstrip("/").split("/")[-1].upper()
                param_value = param.get("Value", "")
                if param_name == "DATABASE_URL" and param_value:
                    self.DATABASE_URL = self.normalize_database_url(param_value)
                elif param_name == "LLM_API_KEY" and param_value:
                    self.LLM_API_KEY = param_value
                elif param_name == "GEMINI_API_KEY" and param_value:
                    self.GEMINI_API_KEY = param_value
                elif param_name == "JWT_SECRET_KEY" and param_value:
                    self.JWT_SECRET_KEY = param_value
        except Exception as exc:
            import logging
            logging.getLogger("datapulse.config").warning(
                "Could not load SSM parameters from %s in region %s: %s",
                self.SSM_PARAMETER_PATH,
                locals().get("region", self.AWS_REGION),
                type(exc).__name__,
            )

    def load_secrets_manager_secrets(self) -> None:
        """Fetch secure credentials from AWS Secrets Manager if SECRETS_MANAGER_SECRET_ID is set."""
        if not self.SECRETS_MANAGER_SECRET_ID or not self.SECRETS_MANAGER_SECRET_ID.strip():
            return

        try:
            import boto3
            import os
            import json
            region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or self.AWS_REGION
            sm_client = boto3.client("secretsmanager", region_name=region)
            response = sm_client.get_secret_value(SecretId=self.SECRETS_MANAGER_SECRET_ID.strip())
            secret_string = response.get("SecretString")
            if secret_string:
                try:
                    secret_dict = json.loads(secret_string)
                    if isinstance(secret_dict, dict):
                        if "DATABASE_URL" in secret_dict and secret_dict["DATABASE_URL"]:
                            self.DATABASE_URL = self.normalize_database_url(str(secret_dict["DATABASE_URL"]))
                        if "LLM_API_KEY" in secret_dict and secret_dict["LLM_API_KEY"]:
                            self.LLM_API_KEY = str(secret_dict["LLM_API_KEY"])
                        if "GEMINI_API_KEY" in secret_dict and secret_dict["GEMINI_API_KEY"]:
                            self.GEMINI_API_KEY = str(secret_dict["GEMINI_API_KEY"])
                        if "JWT_SECRET_KEY" in secret_dict and secret_dict["JWT_SECRET_KEY"]:
                            self.JWT_SECRET_KEY = str(secret_dict["JWT_SECRET_KEY"])
                except json.JSONDecodeError:
                    pass
        except Exception as exc:
            import logging
            logging.getLogger("datapulse.config").warning(
                "Could not load Secrets Manager secret %s: %s",
                self.SECRETS_MANAGER_SECRET_ID,
                type(exc).__name__,
            )

    def validate_production_security(self) -> None:
        """Enforce strict production safeguards against default secrets and insecure configs."""
        if self.ENVIRONMENT.lower() == "production":
            if (
                not self.JWT_SECRET_KEY
                or self.JWT_SECRET_KEY.startswith("datapulse-dev-secret")
                or len(self.JWT_SECRET_KEY) < 32
            ):
                raise ValueError(
                    "CRITICAL SECURITY CONFIGURATION ERROR: A dedicated, cryptographically strong "
                    "JWT_SECRET_KEY (min 32 characters) must be configured via environment variable, "
                    "SSM Parameter Store, or AWS Secrets Manager in production."
                )


@lru_cache
def get_settings() -> Settings:
    """Return cached Settings instance to prevent redundant environment parsing."""
    settings = Settings()
    settings.load_ssm_parameters()
    settings.load_secrets_manager_secrets()
    settings.validate_production_security()
    return settings

