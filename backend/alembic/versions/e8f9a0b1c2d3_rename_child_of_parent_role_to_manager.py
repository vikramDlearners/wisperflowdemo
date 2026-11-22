"""rename child_of_parent role to manager

Revision ID: e8f9a0b1c2d3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e8f9a0b1c2d3'
down_revision: Union[str, None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("UPDATE users SET role = 'manager' WHERE role = 'child_of_parent'")


def downgrade() -> None:
    op.execute("UPDATE users SET role = 'child_of_parent' WHERE role = 'manager'")
