"""activity_log: what happened, who did it, shown on the Logs page

Revision ID: b52d38e6f1c4
Revises: a41c9d27e5b3
Create Date: 2026-10-05 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b52d38e6f1c4'
down_revision: Union[str, Sequence[str], None] = 'a41c9d27e5b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive only: a new table; nothing existing is touched.
    op.create_table(
        'activity_log',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('level', sa.String(length=8), nullable=False, server_default='info'),
        sa.Column('source', sa.String(length=24), nullable=False, server_default='system'),
        sa.Column('event', sa.String(length=48), nullable=False),
        sa.Column('message', sa.Text(), nullable=False, server_default=''),
        sa.Column('post_id', sa.String(length=160), nullable=True),
        sa.Column('actor', sa.String(length=254), nullable=True),
        sa.Column('detail', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_activity_log_created_at', 'activity_log', ['created_at'], unique=False)
    op.create_index('ix_activity_log_post_id', 'activity_log', ['post_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_activity_log_post_id', table_name='activity_log')
    op.drop_index('ix_activity_log_created_at', table_name='activity_log')
    op.drop_table('activity_log')
