"""post format: a generation job records its second item, "carousel" or "image_reel"

image_reel = the carousel's cheat-sheet slide as a short video with music, posted as a Reel instead of the
carousel. Chosen per run on the Generate page (default: brand/config.yaml post_format). Additive: existing
jobs read as carousel. Posts need no column: an image reel is its own kind ("image").

Revision ID: 3f9a1c7e5b2d
Revises: 8decd9abf465
Create Date: 2026-11-03 12:00:00
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '3f9a1c7e5b2d'
down_revision: Union[str, Sequence[str], None] = '8decd9abf465'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('generation_jobs',
                  sa.Column('post_format', sa.String(length=12), nullable=False, server_default='carousel'))


def downgrade() -> None:
    op.drop_column('generation_jobs', 'post_format')
