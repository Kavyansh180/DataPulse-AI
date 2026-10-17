from fastapi import APIRouter

from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.datasets import router as datasets_router
from app.api.v1.profiling import router as profiling_router

api_router = APIRouter()

# Health and readiness endpoints under /api/v1
api_router.include_router(health_router, tags=["Health & Readiness"])

# Authentication endpoints under /api/v1/auth
api_router.include_router(auth_router, prefix="/auth", tags=["Authentication"])

# Datasets endpoints under /api/v1/datasets
api_router.include_router(datasets_router, prefix="/datasets", tags=["Datasets"])

# Profiling and Quality Engine endpoints under /api/v1/profiling
api_router.include_router(profiling_router, prefix="/profiling", tags=["Profiling & Quality"])
