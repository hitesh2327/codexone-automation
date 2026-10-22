"""owner role: the original account runs the brand's own posts and isn't limited by a plan

Every account so far has role "admin" (the default). Plan limits (src/plan_limits.py) exempt only role "owner",
which goes to the first account: the one the pipeline's scheduled posts belong to (posts.user_id defaults to 1).

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-22 18:00:00
"""
from typing import Sequence, Union
from alembic import op

revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'owner' WHERE id = (SELECT min(id) FROM users)")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'owner'")
