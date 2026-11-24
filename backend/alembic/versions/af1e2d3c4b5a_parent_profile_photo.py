"""parent_onboarding_profiles: uploaded profile photo

Revision ID: af1e2d3c4b5a
Revises: 9d0e1f2a3b4a
Create Date: 2026-11-24 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af1e2d3c4b5a'
down_revision: Union[str, None] = '9d0e1f2a3b4a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.add_column(sa.Column('profile_photo_data', sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column('profile_photo_content_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.drop_column('profile_photo_content_type')
        batch.drop_column('profile_photo_data')
