"""scoped generation job lock: allow one active job per trigger per user

Revision ID: 4a1b2c3d4e5f
Revises: 3f9a1c7e5b2d
Create Date: 2026-11-10 00:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '4a1b2c3d4e5f'
down_revision: Union[str, Sequence[str], None] = '3f9a1c7e5b2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ACTIVE = "status IN ('queued', 'running')"


def upgrade() -> None:
    op.drop_index('uq_generation_jobs_one_active', table_name='generation_jobs',
                  postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))
    op.create_index('uq_generation_jobs_one_active', 'generation_jobs', ['trigger', 'user_id'], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))


def downgrade() -> None:
    op.drop_index('uq_generation_jobs_one_active', table_name='generation_jobs',
                  postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))
    op.create_index('uq_generation_jobs_one_active', 'generation_jobs', ['trigger'], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))
