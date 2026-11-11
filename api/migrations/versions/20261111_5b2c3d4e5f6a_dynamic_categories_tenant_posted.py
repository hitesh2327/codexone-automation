"""dynamic categories: tenant-scope posted_topics and widen category columns to 64 chars

Revision ID: 5b2c3d4e5f6a
Revises: 4a1b2c3d4e5f
Create Date: 2026-11-11 23:00:00
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5b2c3d4e5f6a'
down_revision: Union[str, Sequence[str], None] = '4a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('posted_topics') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_posted_topics_user_id_users', 'users', ['user_id'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_posted_topics_user_id', ['user_id'], unique=False)
        batch_op.alter_column('category', existing_type=sa.String(length=32), type_=sa.String(length=64), existing_nullable=True)

    op.execute(
        "UPDATE posted_topics SET user_id = ("
        "SELECT posts.user_id FROM posts WHERE posts.id = posted_topics.item_id"
        ") WHERE item_id IS NOT NULL"
    )

    with op.batch_alter_table('posts') as batch_op:
        batch_op.alter_column('category', existing_type=sa.String(length=32), type_=sa.String(length=64), existing_nullable=False)

    with op.batch_alter_table('generation_jobs') as batch_op:
        batch_op.alter_column('category', existing_type=sa.String(length=32), type_=sa.String(length=64), existing_nullable=True)
        batch_op.alter_column('topic_category', existing_type=sa.String(length=32), type_=sa.String(length=64), existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('generation_jobs') as batch_op:
        batch_op.alter_column('topic_category', existing_type=sa.String(length=64), type_=sa.String(length=32), existing_nullable=True)
        batch_op.alter_column('category', existing_type=sa.String(length=64), type_=sa.String(length=32), existing_nullable=True)

    with op.batch_alter_table('posts') as batch_op:
        batch_op.alter_column('category', existing_type=sa.String(length=64), type_=sa.String(length=32), existing_nullable=False)

    with op.batch_alter_table('posted_topics') as batch_op:
        batch_op.alter_column('category', existing_type=sa.String(length=64), type_=sa.String(length=32), existing_nullable=True)
        batch_op.drop_index('ix_posted_topics_user_id')
        batch_op.drop_constraint('fk_posted_topics_user_id_users', type_='foreignkey')
        batch_op.drop_column('user_id')
