from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Text, BigInteger, Integer, Float, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ProfilingRun(Base):
    """Represents an execution of data profiling and statistical quality computation."""

    __tablename__ = "profiling_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_version_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending",
        index=True,
    )  # pending, running, completed, failed
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_rows_profiled: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    summary_stats: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    dataset_version: Mapped["DatasetVersion"] = relationship(
        "DatasetVersion",
        back_populates="profiling_runs",
    )
    metrics: Mapped[List["QualityMetric"]] = relationship(
        "QualityMetric",
        back_populates="profiling_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProfilingRun id={self.id} version_id={self.dataset_version_id} status='{self.status}'>"


class QualityMetric(Base):
    """Stores granular metrics computed during a profiling run (e.g., null ratio, distinct count)."""

    __tablename__ = "quality_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profiling_run_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("profiling_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    column_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    metric_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    threshold_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_anomalous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    profiling_run: Mapped["ProfilingRun"] = relationship(
        "ProfilingRun",
        back_populates="metrics",
    )

    def __repr__(self) -> str:
        return (
            f"<QualityMetric id={self.id} metric='{self.metric_name}' "
            f"column='{self.column_name}' anomalous={self.is_anomalous}>"
        )
