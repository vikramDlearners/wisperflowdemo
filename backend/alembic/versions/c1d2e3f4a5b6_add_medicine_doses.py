"""add medicine_doses table

Revision ID: c1d2e3f4a5b6
Revises: a9c4e2b7d1f0
Create Date: 2026-11-22 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, None] = 'a9c4e2b7d1f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'medicine_doses',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('medicine_id', sa.String(length=36), sa.ForeignKey('medicines.id'), nullable=False),
        sa.Column('dose_date', sa.Date(), nullable=False),
        sa.Column('slot', sa.String(length=8), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('remind_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('family_alerted_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('medicine_id', 'dose_date', 'slot', name='uq_medicine_dose_slot'),
    )


def downgrade() -> None:
    op.drop_table('medicine_doses')
