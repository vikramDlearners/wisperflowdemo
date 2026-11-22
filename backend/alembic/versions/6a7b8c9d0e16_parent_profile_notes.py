"""parent profile notes as one free-text field

Revision ID: 6a7b8c9d0e16
Revises: 5f6a7b8c9d05
Create Date: 2026-11-29 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a7b8c9d0e16'
down_revision: Union[str, None] = '5f6a7b8c9d05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.add_column(sa.Column('notes', sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('parent_onboarding_profiles') as batch:
        batch.drop_column('notes')
