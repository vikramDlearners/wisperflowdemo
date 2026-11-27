"""appointments: fee and doctor's notes; medicines: the appointment they were given at

Revision ID: e4c1b7a9d2f3
Revises: b1c2d3e4f5a6
Create Date: 2026-11-27 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4c1b7a9d2f3'
down_revision: Union[str, None] = 'b1c2d3e4f5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('appointments') as batch:
        batch.add_column(sa.Column('fee', sa.Numeric(10, 2), nullable=True))
        batch.add_column(sa.Column('doctor_notes', sa.Text(), nullable=True))
    with op.batch_alter_table('medicines') as batch:
        batch.add_column(sa.Column('appointment_id', sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            'fk_medicines_appointment_id', 'appointments', ['appointment_id'], ['id'], ondelete='SET NULL'
        )
        batch.create_index('ix_medicines_appointment_id', ['appointment_id'])


def downgrade() -> None:
    with op.batch_alter_table('medicines') as batch:
        batch.drop_index('ix_medicines_appointment_id')
        batch.drop_constraint('fk_medicines_appointment_id', type_='foreignkey')
        batch.drop_column('appointment_id')
    with op.batch_alter_table('appointments') as batch:
        batch.drop_column('doctor_notes')
        batch.drop_column('fee')
