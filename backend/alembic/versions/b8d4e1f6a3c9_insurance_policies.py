"""insurance policies and their renewal dates

Revision ID: b8d4e1f6a3c9
Revises: a7e3f9c2b6d1
Create Date: 2026-11-28 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8d4e1f6a3c9'
down_revision: Union[str, None] = 'a7e3f9c2b6d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'insurance_policies',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('policy_type', sa.String(length=32), nullable=False),
        sa.Column('insurer', sa.String(length=120), nullable=False),
        sa.Column('plan_name', sa.String(length=160), nullable=True),
        sa.Column('policy_number', sa.String(length=80), nullable=True),
        sa.Column('sum_insured', sa.Numeric(14, 2), nullable=True),
        sa.Column('premium', sa.Numeric(12, 2), nullable=True),
        sa.Column('premium_frequency', sa.String(length=16), nullable=False),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('renewal_date', sa.Date(), nullable=False),
        sa.Column('last_renewed_on', sa.Date(), nullable=True),
        sa.Column('agent_name', sa.String(length=120), nullable=True),
        sa.Column('agent_phone', sa.String(length=32), nullable=True),
        sa.Column('helpline', sa.String(length=32), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('responsible_user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='SET NULL'),
                  nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_insurance_policies_family_id', 'insurance_policies', ['family_id'])


def downgrade() -> None:
    op.drop_index('ix_insurance_policies_family_id', table_name='insurance_policies')
    op.drop_table('insurance_policies')
