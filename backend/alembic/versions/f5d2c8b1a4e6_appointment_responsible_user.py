"""appointments: the family member responsible for the visit

Revision ID: f5d2c8b1a4e6
Revises: e4c1b7a9d2f3
Create Date: 2026-11-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5d2c8b1a4e6'
down_revision: Union[str, None] = 'e4c1b7a9d2f3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('appointments') as batch:
        batch.add_column(sa.Column('responsible_user_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            'fk_appointments_responsible_user_id', 'users', ['responsible_user_id'], ['id'], ondelete='SET NULL'
        )


def downgrade() -> None:
    with op.batch_alter_table('appointments') as batch:
        batch.drop_constraint('fk_appointments_responsible_user_id', type_='foreignkey')
        batch.drop_column('responsible_user_id')
