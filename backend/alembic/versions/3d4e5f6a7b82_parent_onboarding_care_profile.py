"""parent onboarding care profile link

Revision ID: 3d4e5f6a7b82
Revises: 2c3d4e5f6a71
Create Date: 2026-11-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3d4e5f6a7b82'
down_revision: Union[str, None] = '2c3d4e5f6a71'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.add_column(sa.Column('care_profile_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            'fk_parent_onboarding_profiles_care_profile_id',
            'care_profiles',
            ['care_profile_id'],
            ['id'],
        )
        batch.alter_column('user_id', existing_type=sa.String(length=36), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.alter_column('user_id', existing_type=sa.String(length=36), nullable=False)
        batch.drop_constraint('fk_parent_onboarding_profiles_care_profile_id', type_='foreignkey')
        batch.drop_column('care_profile_id')
