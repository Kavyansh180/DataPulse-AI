from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, BigInteger, Integer, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Dataset(Base):
    """Represents a monitored dataset entity (e.g., table, stream, or file collection)."""

    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="s3")
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    user: Mapped[Optional["User"]] = relationship("User", back_populates="datasets")
    versions: Mapped[List["DatasetVersion"]] = relationship(
        "DatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        order_by="desc(DatasetVersion.created_at)",
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name='{self.name}' source='{self.source_type}'>"


class DatasetVersion(Base):
    """Represents an immutable snapshot / version of a dataset ingestion."""

    __tablename__ = "dataset_versions"
    __table_args__ = (
        UniqueConstraint("dataset_id", "version_tag", name="uq_dataset_version_tag"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_tag: Mapped[str] = mapped_column(String(100), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1024), nullable=False)
    row_count: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    column_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship("Dataset", back_populates="versions")
    profiling_runs: Mapped[List["ProfilingRun"]] = relationship(
        "ProfilingRun",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
        order_by="desc(ProfilingRun.created_at)",
    )
    quality_issues: Mapped[List["QualityIssue"]] = relationship(
        "QualityIssue",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
        order_by="desc(QualityIssue.created_at)",
    )

    def __repr__(self) -> str:
        return f"<DatasetVersion id={self.id} dataset_id={self.dataset_id} tag='{self.version_tag}'>"
