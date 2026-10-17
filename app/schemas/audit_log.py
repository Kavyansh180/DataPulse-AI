from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class AuditLogCreate(BaseModel):
    action: str = Field(..., max_length=100, description="Action performed, e.g., dataset_created")
    entity_type: str = Field(..., max_length=100, description="Target entity type, e.g., dataset")
    entity_id: Optional[str] = Field(default=None, max_length=100, description="String representation of entity ID")
    actor: str = Field(default="system", max_length=100, description="User or service identity triggering action")
    details: Optional[str] = Field(default=None, description="Contextual metadata or JSON payload")


class AuditLogRead(AuditLogCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
