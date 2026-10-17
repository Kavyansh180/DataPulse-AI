"""0002_add_quality_score_and_summary

Add quality_score and summary_stats columns to profiling_runs.

Revision ID: 0002_add_quality_score
Revises: 0001_initial_schema
Create Date: 2026-10-16 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_add_quality_score"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiling_runs", sa.Column("quality_score", sa.Float(), nullable=True))
    op.add_column("profiling_runs", sa.Column("summary_stats", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("profiling_runs", "summary_stats")
    op.drop_column("profiling_runs", "quality_score")
