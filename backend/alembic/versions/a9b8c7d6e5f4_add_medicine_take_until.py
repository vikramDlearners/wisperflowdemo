"""add take_until to medicines

Revision ID: a9b8c7d6e5f4
Revises: d8f2b0e5a3c4
Create Date: 2026-11-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9b8c7d6e5f4'
down_revision: Union[str, None] = 'd8f2b0e5a3c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('medicines', sa.Column('take_until', sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column('medicines', 'take_until')
