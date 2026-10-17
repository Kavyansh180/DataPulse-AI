from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from typing import Optional
from app.core.config import Settings, get_settings
from app.api.errors import register_error_handlers
from app.api.v1.router import api_router
from app.api.v1.health import router as health_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("datapulse")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for initialization and clean shutdown."""
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} [{settings.ENVIRONMENT}]")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


def create_application(custom_settings: Optional[Settings] = None) -> FastAPI:
    """FastAPI application factory with middleware, error handling, and route registration."""
    app_settings = custom_settings or get_settings()
    application = FastAPI(
        title=app_settings.APP_NAME,
        version=app_settings.APP_VERSION,
        description=(
            "AI-powered data quality monitoring and root-cause analysis platform. "
            "Foundation phase providing database management, health probes, and core catalog APIs."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Register CORS middleware for frontend / dashboard integration (if enabled)
    if app_settings.ENABLE_CORS_MIDDLEWARE:
        allow_credentials = False if app_settings.ALLOWED_ORIGINS == ["*"] else True
        application.add_middleware(
            CORSMiddleware,
            allow_origins=app_settings.ALLOWED_ORIGINS,
            allow_credentials=allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Register centralized exception handlers
    register_error_handlers(application)

    # Mount health & ready endpoints at root level for cloud / container probes (/health, /ready)
    application.include_router(health_router, tags=["Health & Readiness"])

    # Mount versioned API routes under /api/v1
    application.include_router(api_router, prefix=app_settings.API_V1_PREFIX)

    @application.get("/", include_in_schema=False)
    def root():
        return JSONResponse(
            content={
                "name": settings.APP_NAME,
                "version": settings.APP_VERSION,
                "environment": settings.ENVIRONMENT,
                "docs": "/docs",
                "health": "/health",
                "ready": "/ready",
            }
        )

    return application


app = create_application()
