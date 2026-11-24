"""medicines: photo of the prescription

Revision ID: c7e1a9d4f2b3
Revises: af1e2d3c4b5a
Create Date: 2026-11-24 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7e1a9d4f2b3'
down_revision: Union[str, None] = 'af1e2d3c4b5a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('medicines') as batch:
        batch.add_column(sa.Column('prescription_image_data', sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column('prescription_image_content_type', sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('medicines') as batch:
        batch.drop_column('prescription_image_content_type')
        batch.drop_column('prescription_image_data')
