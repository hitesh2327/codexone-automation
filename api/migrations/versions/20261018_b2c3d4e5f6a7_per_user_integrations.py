"""per-user integrations: role column on users, user_config_values table

Revision ID: b2c3d4e5f6a7
Revises: f96c2d3e4a51
Create Date: 2026-10-18 12:00:00
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'f96c2d3e4a51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(length=16), nullable=False, server_default='admin'))

    op.create_table(
        'user_config_values',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('ciphertext', sa.LargeBinary(), nullable=True),
        sa.Column('nonce', sa.LargeBinary(), nullable=True),
        sa.Column('value_plain', sa.Text(), nullable=True),
        sa.Column('dek_version', sa.Integer(), nullable=True),
        sa.Column('fingerprint', sa.String(length=16), nullable=True),
        sa.Column('source', sa.String(length=12), nullable=False, server_default='ui'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(length=254), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'key', name='uq_user_config_values_user_key'),
    )
    op.create_index('ix_user_config_values_user_id', 'user_config_values', ['user_id'])


def downgrade() -> None:
    op.drop_table('user_config_values')
    op.drop_column('users', 'role')
