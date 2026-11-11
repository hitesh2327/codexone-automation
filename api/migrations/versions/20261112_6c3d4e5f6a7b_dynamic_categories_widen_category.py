"""dynamic categories: widen category columns to 64 chars

Revision ID: 6c3d4e5f6a7b
Revises: 5b2c3d4e5f6a
Create Date: 2026-11-12 04:50:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "6c3d4e5f6a7b"
down_revision: Union[str, Sequence[str], None] = "5b2c3d4e5f6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("posted_topics") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=True,
        )

    with op.batch_alter_table("posts") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=False,
        )

    with op.batch_alter_table("generation_jobs") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "topic_category",
            existing_type=sa.String(length=32),
            type_=sa.String(length=64),
            existing_nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("generation_jobs") as batch_op:
        batch_op.alter_column(
            "topic_category",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=True,
        )

    with op.batch_alter_table("posts") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=False,
        )

    with op.batch_alter_table("posted_topics") as batch_op:
        batch_op.alter_column(
            "category",
            existing_type=sa.String(length=64),
            type_=sa.String(length=32),
            existing_nullable=True,
        )
