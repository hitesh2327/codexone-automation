"""users: profile fields + avatar; otp_codes

Revision ID: a41c9d27e5b3
Revises: 6ea71f245945
Create Date: 2026-10-05 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a41c9d27e5b3'
down_revision: Union[str, Sequence[str], None] = '6ea71f245945'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Additive only, with server defaults, so code that predates these columns keeps working.
    op.add_column('users', sa.Column('job_title', sa.String(length=80), nullable=False, server_default=''))
    op.add_column('users', sa.Column('bio', sa.String(length=280), nullable=False, server_default=''))
    op.add_column('users', sa.Column('phone', sa.String(length=32), nullable=False, server_default=''))
    op.add_column('users', sa.Column('timezone', sa.String(length=64), nullable=False, server_default='Asia/Kolkata'))
    op.add_column('users', sa.Column('avatar', sa.LargeBinary(), nullable=True))
    op.add_column('users', sa.Column('avatar_mime', sa.String(length=32), nullable=True))
    op.add_column('users', sa.Column('avatar_updated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('email_verified_at', sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        'otp_codes',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('purpose', sa.String(length=24), nullable=False),
        sa.Column('email', sa.String(length=254), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_otp_codes_user_purpose', 'otp_codes', ['user_id', 'purpose'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_otp_codes_user_purpose', table_name='otp_codes')
    op.drop_table('otp_codes')
    for col in ('email_verified_at', 'password_changed_at', 'avatar_updated_at', 'avatar_mime', 'avatar',
                'timezone', 'phone', 'bio', 'job_title'):
        op.drop_column('users', col)
