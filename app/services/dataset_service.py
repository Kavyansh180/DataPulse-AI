from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models.dataset import Dataset, DatasetVersion
from app.schemas.dataset import DatasetCreate, DatasetUpdate, DatasetVersionCreate


class DatasetService:
    """Service handling dataset and dataset version operations."""

    @staticmethod
    def get_by_id(db: Session, dataset_id: int) -> Optional[Dataset]:
        stmt = select(Dataset).where(Dataset.id == dataset_id)
        return db.scalars(stmt).first()

    @staticmethod
    def get_by_name(db: Session, name: str) -> Optional[Dataset]:
        stmt = select(Dataset).where(Dataset.name == name)
        return db.scalars(stmt).first()

    @staticmethod
    def list_datasets(db: Session, user_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Dataset]:
        stmt = select(Dataset)
        if user_id is not None:
            stmt = stmt.where(Dataset.user_id == user_id)
        stmt = stmt.offset(skip).limit(limit).order_by(Dataset.id.desc())
        return list(db.scalars(stmt).all())

    @staticmethod
    def create(db: Session, dataset_in: DatasetCreate, user_id: Optional[int] = None) -> Dataset:
        dataset = Dataset(
            name=dataset_in.name,
            description=dataset_in.description,
            source_type=dataset_in.source_type,
            user_id=user_id,
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        return dataset

    @staticmethod
    def update(db: Session, db_dataset: Dataset, dataset_in: DatasetUpdate) -> Dataset:
        if dataset_in.description is not None:
            db_dataset.description = dataset_in.description
        if dataset_in.source_type is not None:
            db_dataset.source_type = dataset_in.source_type
        db.commit()
        db.refresh(db_dataset)
        return db_dataset

    @staticmethod
    def delete(db: Session, db_dataset: Dataset) -> None:
        db.delete(db_dataset)
        db.commit()

    @staticmethod
    def create_version(db: Session, version_in: DatasetVersionCreate) -> DatasetVersion:
        version = DatasetVersion(
            dataset_id=version_in.dataset_id,
            version_tag=version_in.version_tag,
            storage_uri=version_in.storage_uri,
            row_count=version_in.row_count,
            column_count=version_in.column_count,
            file_size_bytes=version_in.file_size_bytes,
        )
        db.add(version)
        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def list_versions_for_dataset(db: Session, dataset_id: int) -> List[DatasetVersion]:
        stmt = (
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.created_at.desc())
        )
        return list(db.scalars(stmt).all())
