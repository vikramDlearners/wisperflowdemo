"""add medicine purpose and appointment location

Revision ID: 1b2c3d4e5f60
Revises: 0a1b2c3d4e5f
Create Date: 2026-11-25 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b2c3d4e5f60'
down_revision: Union[str, None] = '0a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('medicines') as batch:
        batch.add_column(sa.Column('purpose', sa.String(length=120), nullable=True))
    with op.batch_alter_table('appointments') as batch:
        batch.add_column(sa.Column('location', sa.String(length=255), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('appointments') as batch:
        batch.drop_column('location')
    with op.batch_alter_table('medicines') as batch:
        batch.drop_column('purpose')
