"""add emergencies (raised in the chat or with the emergency button)

Revision ID: d8f2b0e5a3c4
Revises: c7e1a9d4f2b3
Create Date: 2026-11-24 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8f2b0e5a3c4'
down_revision: Union[str, None] = 'c7e1a9d4f2b3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'emergencies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('checkin_id', sa.String(length=36), sa.ForeignKey('health_checkins.id', ondelete='CASCADE'), nullable=True),
        sa.Column('reported_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_emergencies_family_status', 'emergencies', ['family_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_emergencies_family_status', table_name='emergencies')
    op.drop_table('emergencies')
