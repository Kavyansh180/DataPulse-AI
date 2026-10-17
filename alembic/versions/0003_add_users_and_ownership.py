"""0003_add_users_and_ownership

Create users table and add user_id ownership column to datasets.

Revision ID: 0003_add_users_and_ownership
Revises: 0002_add_quality_score
Create Date: 2026-10-17 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_add_users_and_ownership"
down_revision: Union[str, None] = "0002_add_quality_score"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)

    # 2. Add user_id column and foreign key to datasets
    op.add_column("datasets", sa.Column("user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_datasets_user_id_users",
        "datasets",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(op.f("ix_datasets_user_id"), "datasets", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_constraint("fk_datasets_user_id_users", "datasets", type_="foreignkey")
    op.drop_index(op.f("ix_datasets_user_id"), table_name="datasets")
    op.drop_column("datasets", "user_id")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
