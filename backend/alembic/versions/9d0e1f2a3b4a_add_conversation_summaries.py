"""add conversation_summaries (Gemini summary of each finished parent conversation)

Revision ID: 9d0e1f2a3b4a
Revises: 8c9d0e1f2a39
Create Date: 2026-11-23 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d0e1f2a3b4a'
down_revision: Union[str, None] = '8c9d0e1f2a39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'conversation_summaries',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('checkin_id', sa.String(length=36), sa.ForeignKey('health_checkins.id'), nullable=False),
        sa.Column('from_seq', sa.Integer(), nullable=False),
        sa.Column('to_seq', sa.Integer(), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('important', sa.JSON(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('checkin_id', 'from_seq', name='uq_conversation_summary_part'),
    )
    op.create_index('ix_conversation_summaries_checkin_id', 'conversation_summaries', ['checkin_id'])


def downgrade() -> None:
    op.drop_index('ix_conversation_summaries_checkin_id', table_name='conversation_summaries')
    op.drop_table('conversation_summaries')
