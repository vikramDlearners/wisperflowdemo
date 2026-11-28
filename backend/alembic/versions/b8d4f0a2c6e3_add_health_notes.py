"""health notes: a parent's allergies, conditions and readings, from chat, uploads and the family

Revision ID: b8d4f0a2c6e3
Revises: a7c3e9f1b5d2
Create Date: 2026-11-28 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4f0a2c6e3'
down_revision: Union[str, None] = 'a7c3e9f1b5d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'health_notes',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('kind', sa.String(length=16), nullable=False),
        sa.Column('label', sa.String(length=120), nullable=False),
        sa.Column('value', sa.String(length=60), nullable=True),
        sa.Column('value_num', sa.Float(), nullable=True),
        sa.Column('value_num2', sa.Float(), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=False),
        sa.Column('source_text', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.Column('recorded_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_health_notes_profile_kind', 'health_notes', ['care_profile_id', 'kind', 'recorded_at'])


def downgrade() -> None:
    op.drop_index('ix_health_notes_profile_kind', table_name='health_notes')
    op.drop_table('health_notes')
