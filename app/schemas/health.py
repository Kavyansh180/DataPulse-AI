from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Payload for the basic liveness / health probe."""

    status: str = Field(default="healthy", description="Application service status")
    app: str = Field(..., description="Application name")
    version: str = Field(..., description="Application version")
    environment: str = Field(..., description="Current environment mode")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of the check")


class ReadyResponse(BaseModel):
    """Payload for the database readiness probe."""

    status: str = Field(default="ready", description="Overall readiness status")
    database: str = Field(default="connected", description="Database connection state")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="UTC timestamp of the check")
    error: Optional[str] = Field(default=None, description="Error detail if unavailable")
