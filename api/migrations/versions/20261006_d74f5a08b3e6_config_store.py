"""config store: encrypted config_values, the wrapped data key, verification results, meta/canary

Revision ID: d74f5a08b3e6
Revises: c63e49f7a2d5
Create Date: 2026-10-06 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd74f5a08b3e6'
down_revision: Union[str, Sequence[str], None] = 'c63e49f7a2d5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive only: four new tables; nothing existing is touched. Until values are saved on the Config
    # page every setting keeps coming from the environment exactly as before.
    json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql')
    big_id = sa.BigInteger().with_variant(sa.Integer(), 'sqlite')
    op.create_table(
        'config_keys',
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('wrapped_dek', sa.LargeBinary(), nullable=False),
        sa.Column('nonce', sa.LargeBinary(), nullable=False),
        sa.Column('kek_id', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('rewrapped_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('version'),
    )
    op.create_table(
        'config_values',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('is_secret', sa.Boolean(), nullable=False),
        sa.Column('ciphertext', sa.LargeBinary(), nullable=True),
        sa.Column('nonce', sa.LargeBinary(), nullable=True),
        sa.Column('value_plain', sa.Text(), nullable=True),
        sa.Column('dek_version', sa.Integer(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('fingerprint', sa.String(length=16), nullable=True),
        sa.Column('source', sa.String(length=12), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_by', sa.String(length=254), nullable=True),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_table(
        'config_checks',
        sa.Column('id', big_id, autoincrement=True, nullable=False),
        sa.Column('integration', sa.String(length=24), nullable=False),
        sa.Column('status', sa.String(length=10), nullable=False),
        sa.Column('depth', sa.String(length=8), nullable=False),
        sa.Column('error_class', sa.String(length=16), nullable=True),
        sa.Column('code', sa.String(length=48), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('result', json_type, nullable=False),
        sa.Column('values_fp', sa.String(length=16), nullable=True),
        sa.Column('config_version', sa.Integer(), nullable=False),
        sa.Column('ran_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ran_in', sa.String(length=8), nullable=False),
        sa.Column('duration_ms', sa.Integer(), nullable=False),
        sa.Column('actor', sa.String(length=254), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_config_checks_integration_ran_at', 'config_checks', ['integration', 'ran_at'], unique=False)
    op.create_table(
        'config_meta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('canary', sa.LargeBinary(), nullable=True),
        sa.Column('canary_nonce', sa.LargeBinary(), nullable=True),
        sa.Column('config_version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    # Dropping config_values loses every value saved on the Config page (the environment still works).
    op.drop_table('config_meta')
    op.drop_index('ix_config_checks_integration_ran_at', table_name='config_checks')
    op.drop_table('config_checks')
    op.drop_table('config_values')
    op.drop_table('config_keys')
