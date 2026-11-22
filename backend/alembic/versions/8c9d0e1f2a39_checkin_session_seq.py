"""health_checkins.session_seq: each opening of the parent chat starts a new conversation on screen

Revision ID: 8c9d0e1f2a39
Revises: 7b8c9d0e1f28
Create Date: 2026-11-23 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c9d0e1f2a39'
down_revision: Union[str, None] = '7b8c9d0e1f28'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('health_checkins') as batch:
        batch.add_column(sa.Column('session_seq', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('health_checkins') as batch:
        batch.drop_column('session_seq')
