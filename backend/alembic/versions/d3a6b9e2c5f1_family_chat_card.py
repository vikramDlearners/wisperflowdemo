"""family chat: a card under an answer (the month's analysis)

Revision ID: d3a6b9e2c5f1
Revises: c9f5a2d7b4e8
Create Date: 2026-11-28 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3a6b9e2c5f1'
down_revision: Union[str, None] = 'c9f5a2d7b4e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('family_chat_messages') as batch:
        batch.add_column(sa.Column('card', sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('family_chat_messages') as batch:
        batch.drop_column('card')
