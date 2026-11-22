"""add family member relationship and care profile linked_member_id

Revision ID: 0a1b2c3d4e5f
Revises: e8f9a0b1c2d3
Create Date: 2026-11-24 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a1b2c3d4e5f'
down_revision: Union[str, None] = 'e8f9a0b1c2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('family_members') as batch:
        batch.add_column(sa.Column('relationship', sa.String(length=20), nullable=True))
    with op.batch_alter_table('care_profiles') as batch:
        batch.add_column(sa.Column('linked_member_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            'fk_care_profiles_linked_member_id_family_members',
            'family_members',
            ['linked_member_id'],
            ['id'],
        )


def downgrade() -> None:
    with op.batch_alter_table('care_profiles') as batch:
        batch.drop_constraint('fk_care_profiles_linked_member_id_family_members', type_='foreignkey')
        batch.drop_column('linked_member_id')
    with op.batch_alter_table('family_members') as batch:
        batch.drop_column('relationship')
