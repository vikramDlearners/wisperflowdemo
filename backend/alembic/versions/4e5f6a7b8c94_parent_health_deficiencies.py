"""parent health deficiencies (calcium, sugar problems)

Revision ID: 4e5f6a7b8c94
Revises: 3d4e5f6a7b82
Create Date: 2026-11-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e5f6a7b8c94'
down_revision: Union[str, None] = '3d4e5f6a7b82'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.add_column(sa.Column('calcium_deficiency', sa.Boolean(), nullable=True))
        batch.add_column(sa.Column('calcium_deficiency_notes', sa.Text(), nullable=True))
        batch.add_column(sa.Column('sugar_problems', sa.Boolean(), nullable=True))
        batch.add_column(sa.Column('sugar_problems_notes', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.drop_column('sugar_problems_notes')
        batch.drop_column('sugar_problems')
        batch.drop_column('calcium_deficiency_notes')
        batch.drop_column('calcium_deficiency')
