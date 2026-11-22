"""parent health deficiencies as one free-text field

Revision ID: 5f6a7b8c9d05
Revises: 4e5f6a7b8c94
Create Date: 2026-11-29 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5f6a7b8c9d05'
down_revision: Union[str, None] = '4e5f6a7b8c94'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.add_column(sa.Column('deficiencies', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.drop_column('deficiencies')
