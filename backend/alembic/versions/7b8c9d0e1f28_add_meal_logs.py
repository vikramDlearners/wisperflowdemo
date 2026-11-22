"""add meal_logs (what the parent ate, from the chatbot)

Revision ID: 7b8c9d0e1f28
Revises: 6a7b8c9d0e16
Create Date: 2026-11-22 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7b8c9d0e1f28'
down_revision: Union[str, None] = '6a7b8c9d0e16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'meal_logs',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('checkin_id', sa.String(length=36), sa.ForeignKey('health_checkins.id'), nullable=True),
        sa.Column('log_date', sa.Date(), nullable=False),
        sa.Column('meals', sa.String(length=32), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
    )
    op.create_index('ix_meal_logs_profile_date', 'meal_logs', ['care_profile_id', 'log_date'])


def downgrade() -> None:
    op.drop_index('ix_meal_logs_profile_date', table_name='meal_logs')
    op.drop_table('meal_logs')
