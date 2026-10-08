"""rate_limit_events (shared limiter) + users.via_google (allowlist applies to Google-created accounts)

Revision ID: e85b1c2d9f40
Revises: d74f5a08b3e6
Create Date: 2026-10-06 18:00:00

QA-M-05: rate limits were per process (each Lambda container had its own counters). QA-M-06: a Google
account that set a password kept access after being removed from ALLOWED_GOOGLE_EMAILS.
Additive only (new table, new column with a server default), so older code keeps running on this schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e85b1c2d9f40'
down_revision: Union[str, Sequence[str], None] = 'd74f5a08b3e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'rate_limit_events',
        sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(length=200), nullable=False),
        sa.Column('at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_rate_limit_events_key_at', 'rate_limit_events', ['key', 'at'], unique=False)
    op.create_index('ix_rate_limit_events_at', 'rate_limit_events', ['at'], unique=False)
    op.add_column('users', sa.Column('via_google', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    # Existing accounts made by Google sign-in: no username, or no password (the seeded admin has both).
    op.execute("UPDATE users SET via_google = true WHERE username IS NULL OR password_hash IS NULL")


def downgrade() -> None:
    op.drop_column('users', 'via_google')
    op.drop_index('ix_rate_limit_events_at', table_name='rate_limit_events')
    op.drop_index('ix_rate_limit_events_key_at', table_name='rate_limit_events')
    op.drop_table('rate_limit_events')
