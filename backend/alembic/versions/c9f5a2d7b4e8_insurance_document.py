"""insurance policies: the policy document (PDF or photo)

Revision ID: c9f5a2d7b4e8
Revises: b8d4e1f6a3c9
Create Date: 2026-11-28 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9f5a2d7b4e8'
down_revision: Union[str, None] = 'b8d4e1f6a3c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('insurance_policies') as batch:
        batch.add_column(sa.Column('document_data', sa.LargeBinary(), nullable=True))
        batch.add_column(sa.Column('document_content_type', sa.String(length=100), nullable=True))
        batch.add_column(sa.Column('document_name', sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('insurance_policies') as batch:
        batch.drop_column('document_name')
        batch.drop_column('document_content_type')
        batch.drop_column('document_data')
