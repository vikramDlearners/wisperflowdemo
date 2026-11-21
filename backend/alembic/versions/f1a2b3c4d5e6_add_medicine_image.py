"""add image columns to medicines

Revision ID: f1a2b3c4d5e6
Revises: b7c8d9e0f1a2
Create Date: 2026-11-27 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'b7c8d9e0f1a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('medicines', sa.Column('image_data', sa.LargeBinary(), nullable=True))
    op.add_column('medicines', sa.Column('image_content_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    op.drop_column('medicines', 'image_content_type')
    op.drop_column('medicines', 'image_data')
