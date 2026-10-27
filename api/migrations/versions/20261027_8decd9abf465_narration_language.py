"""narration language: posts and generation jobs record "en" (English) or "hi" (Hinglish)

Hinglish narration is chosen per run on the Generate page (docs/specs/hinglish-narration-plan.md).
Additive: existing rows read as English. A random revision id (not the next in the f6a7/a7b8 sequence),
which the Stripe branch collided with once.

Revision ID: 8decd9abf465
Revises: a7b8c9d0e1f2
Create Date: 2026-10-27 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '8decd9abf465'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('language', sa.String(length=2), nullable=False, server_default='en'))
    op.add_column('generation_jobs', sa.Column('language', sa.String(length=2), nullable=False, server_default='en'))


def downgrade() -> None:
    op.drop_column('generation_jobs', 'language')
    op.drop_column('posts', 'language')
