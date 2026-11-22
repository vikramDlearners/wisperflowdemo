"""add prescription image and medicine pricing

Revision ID: a9c4e2b7d1f0
Revises: f1a2b3c4d5e6
Create Date: 2026-11-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a9c4e2b7d1f0'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('prescription_scans', sa.Column('image_data', sa.LargeBinary(), nullable=True))
    op.add_column('prescription_scans', sa.Column('image_content_type', sa.String(length=100), nullable=True))
    with op.batch_alter_table('medicines') as batch_op:
        batch_op.add_column(sa.Column('prescription_scan_id', sa.String(length=36), nullable=True))
        batch_op.create_foreign_key('fk_medicines_prescription_scan_id', 'prescription_scans', ['prescription_scan_id'], ['id'])
        batch_op.add_column(sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=True))
        batch_op.add_column(sa.Column('total_medicine_count', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('total_price', sa.Numeric(precision=10, scale=2), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('medicines') as batch_op:
        batch_op.drop_column('total_price')
        batch_op.drop_column('total_medicine_count')
        batch_op.drop_column('unit_price')
        batch_op.drop_constraint('fk_medicines_prescription_scan_id', type_='foreignkey')
        batch_op.drop_column('prescription_scan_id')
    op.drop_column('prescription_scans', 'image_content_type')
    op.drop_column('prescription_scans', 'image_data')
