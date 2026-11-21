"""add appointments table

Revision ID: b7c8d9e0f1a2
Revises: e5f6a7b8c9d0
Create Date: 2026-11-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c8d9e0f1a2'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'appointments',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('scheduled_date', sa.Date(), nullable=False),
        sa.Column('start_time', sa.String(length=8), nullable=False),
        sa.Column('provider', sa.String(length=255), nullable=False),
        sa.Column('reason', sa.String(length=255), nullable=False),
        sa.Column('notes', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('appointments')
