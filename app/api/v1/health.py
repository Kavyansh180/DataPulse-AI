from datetime import datetime
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.database import check_database_connectivity
from app.schemas.health import HealthResponse, ReadyResponse

router = APIRouter()
settings = get_settings()


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness check",
    description="Check whether the application process is running and responding.",
)
def get_health() -> HealthResponse:
    """Basic health check indicating process vitality."""
    return HealthResponse(
        status="healthy",
        app=settings.APP_NAME,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        timestamp=datetime.utcnow(),
    )


@router.get(
    "/ready",
    response_model=ReadyResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Database connectivity failed",
            "model": ReadyResponse,
        }
    },
    summary="Readiness probe",
    description="Verify active connectivity to the underlying PostgreSQL/database engine.",
)
def get_ready():
    """Readiness probe that tests live database connectivity.

    Returns HTTP 200 when database responds to ping query,
    or HTTP 503 if database connection is failing or unreachable.
    """
    is_connected, error_msg = check_database_connectivity()

    if not is_connected:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "timestamp": datetime.utcnow().isoformat(),
                "error": "Database connectivity check failed",
            },
        )

    return ReadyResponse(
        status="ready",
        database="connected",
        timestamp=datetime.utcnow(),
        error=None,
    )
