"""add health_checkins and chat_messages tables

Revision ID: d2e3f4a5b6c7
Revises: c1d2e3f4a5b6
Create Date: 2026-11-22 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd2e3f4a5b6c7'
down_revision: Union[str, None] = 'c1d2e3f4a5b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'health_checkins',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('parent_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('checkin_date', sa.Date(), nullable=False),
        sa.Column('step', sa.String(length=16), nullable=False),
        sa.Column('health_text', sa.Text(), nullable=True),
        sa.Column('urgent', sa.Boolean(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary_sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pending_medicine_id', sa.String(length=36), nullable=True),
        sa.UniqueConstraint('care_profile_id', 'checkin_date', name='uq_health_checkin_profile_date'),
    )
    op.create_table(
        'chat_messages',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('checkin_id', sa.String(length=36), sa.ForeignKey('health_checkins.id'), nullable=False),
        sa.Column('sender', sa.String(length=8), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('language', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('chat_messages')
    op.drop_table('health_checkins')
