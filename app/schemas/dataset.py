from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class DatasetBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Unique human-readable dataset name")
    description: Optional[str] = Field(default=None, description="Detailed description of dataset contents")
    source_type: str = Field(default="s3", max_length=50, description="Origin source system (s3, postgres, csv, etc.)")


class DatasetCreate(DatasetBase):
    pass


class DatasetUpdate(BaseModel):
    description: Optional[str] = None
    source_type: Optional[str] = None


class DatasetVersionBase(BaseModel):
    version_tag: str = Field(..., min_length=1, max_length=100, description="Version identifier (e.g., v1.0.0, 20261016_01)")
    storage_uri: str = Field(..., min_length=1, max_length=1024, description="S3 or local URI to the source artifact")
    row_count: Optional[int] = Field(default=None, ge=0, description="Total number of records in this version")
    column_count: Optional[int] = Field(default=None, ge=0, description="Total number of fields/features")
    file_size_bytes: Optional[int] = Field(default=None, ge=0, description="File size in bytes")


class DatasetVersionCreate(DatasetVersionBase):
    dataset_id: int = Field(..., description="Parent dataset identifier")


class DatasetVersionRead(DatasetVersionBase):
    id: int
    dataset_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetRead(DatasetBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DatasetDetailRead(DatasetRead):
    versions: List[DatasetVersionRead] = []

    model_config = ConfigDict(from_attributes=True)
