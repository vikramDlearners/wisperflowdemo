"""parent notes: notes a parent saves, with an optional reminder for themselves or someone else

Revision ID: a7c3e9f1b5d2
Revises: d3a6b9e2c5f1
Create Date: 2026-11-28 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f1b5d2'
down_revision: Union[str, None] = 'd3a6b9e2c5f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'parent_notes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('remind_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('remind_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('send_reminder', sa.Boolean(), nullable=False),
        sa.Column('task_id', sa.String(length=36), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('reminded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_parent_notes_care_profile_id', 'parent_notes', ['care_profile_id'])
    op.create_index('ix_parent_notes_due', 'parent_notes', ['reminded_at', 'remind_at'])


def downgrade() -> None:
    op.drop_index('ix_parent_notes_due', table_name='parent_notes')
    op.drop_index('ix_parent_notes_care_profile_id', table_name='parent_notes')
    op.drop_table('parent_notes')
