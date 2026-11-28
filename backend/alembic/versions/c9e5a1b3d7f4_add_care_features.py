"""care features: the daily "I'm fine" button and the other parent and family features from TODO.md

Revision ID: c9e5a1b3d7f4
Revises: b8d4f0a2c6e3
Create Date: 2026-11-28 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9e5a1b3d7f4'
down_revision: Union[str, None] = 'b8d4f0a2c6e3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'daily_fine',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('day', sa.Date(), nullable=False),
        sa.Column('fine_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('asked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('family_told_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('care_profile_id', 'day', name='uq_daily_fine_profile_day'),
    )
    op.create_table(
        'care_alerts_sent',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('kind', sa.String(length=40), nullable=False),
        sa.Column('period', sa.String(length=20), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('care_profile_id', 'kind', 'period', name='uq_care_alert_once'),
    )
    op.create_table(
        'refill_requests',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id'), nullable=False),
        sa.Column('medicine_id', sa.String(length=36), sa.ForeignKey('medicines.id'), nullable=False),
        sa.Column('tablets_left', sa.Integer(), nullable=True),
        sa.Column('asked_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('task_id', sa.String(length=36), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_refill_requests_medicine_id', 'refill_requests', ['medicine_id'])
    op.create_table(
        'help_requests',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('asked_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('decided_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('task_id', sa.String(length=36), sa.ForeignKey('tasks.id'), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_help_requests_care_profile_id', 'help_requests', ['care_profile_id'])
    op.create_table(
        'family_posts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('author_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=8), nullable=False),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('data', sa.LargeBinary(), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('seen_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_family_posts_care_profile_id', 'family_posts', ['care_profile_id'])
    op.create_table(
        'care_contacts',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('phone', sa.String(length=30), nullable=True),
        sa.Column('address', sa.String(length=240), nullable=True),
        sa.Column('birthday_month', sa.Integer(), nullable=True),
        sa.Column('birthday_day', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_care_contacts_care_profile_id', 'care_contacts', ['care_profile_id'])
    op.create_table(
        'care_cards',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('blood_group', sa.String(length=8), nullable=True),
        sa.Column('emergency_name', sa.String(length=120), nullable=True),
        sa.Column('emergency_phone', sa.String(length=30), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'parent_privacy',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False, unique=True),
        sa.Column('share_words', sa.Boolean(), nullable=False),
        sa.Column('share_chats', sa.Boolean(), nullable=False),
        sa.Column('video_auto_answer', sa.Boolean(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        'medical_documents',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('doc_date', sa.Date(), nullable=True),
        sa.Column('text', sa.Text(), nullable=True),
        sa.Column('data', sa.LargeBinary(), nullable=True),
        sa.Column('content_type', sa.String(length=100), nullable=True),
        sa.Column('file_name', sa.String(length=200), nullable=True),
        sa.Column('uploaded_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_medical_documents_care_profile_id', 'medical_documents', ['care_profile_id'])
    op.create_table(
        'medical_share_links',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_medical_share_links_care_profile_id', 'medical_share_links', ['care_profile_id'])
    op.create_table(
        'care_expenses',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('paid_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('what', sa.String(length=160), nullable=False),
        sa.Column('spent_on', sa.Date(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_care_expenses_care_profile_id', 'care_expenses', ['care_profile_id'])
    op.create_table(
        'care_visits',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('visit_date', sa.Date(), nullable=False),
        sa.Column('appointment_id', sa.String(length=36), sa.ForeignKey('appointments.id'), nullable=True),
        sa.Column('note', sa.String(length=240), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_care_visits_care_profile_id', 'care_visits', ['care_profile_id'])
    op.create_table(
        'video_calls',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('caller_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('offer', sa.Text(), nullable=True),
        sa.Column('answer', sa.Text(), nullable=True),
        sa.Column('caller_ice', sa.JSON(), nullable=False),
        sa.Column('callee_ice', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('answered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_video_calls_care_profile_id', 'video_calls', ['care_profile_id'])
    op.create_table(
        'paperwork_items',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.String(length=24), nullable=False),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('done_on', sa.Date(), nullable=True),
        sa.Column('created_by_user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_paperwork_items_care_profile_id', 'paperwork_items', ['care_profile_id'])
    op.create_table(
        'carer_reports',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('care_profile_id', sa.String(length=36), sa.ForeignKey('care_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('kind', sa.String(length=12), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_carer_reports_care_profile_id', 'carer_reports', ['care_profile_id'])


def downgrade() -> None:
    op.drop_index('ix_carer_reports_care_profile_id', table_name='carer_reports')
    op.drop_table('carer_reports')
    op.drop_index('ix_paperwork_items_care_profile_id', table_name='paperwork_items')
    op.drop_table('paperwork_items')
    op.drop_index('ix_video_calls_care_profile_id', table_name='video_calls')
    op.drop_table('video_calls')
    op.drop_index('ix_care_visits_care_profile_id', table_name='care_visits')
    op.drop_table('care_visits')
    op.drop_index('ix_care_expenses_care_profile_id', table_name='care_expenses')
    op.drop_table('care_expenses')
    op.drop_index('ix_medical_share_links_care_profile_id', table_name='medical_share_links')
    op.drop_table('medical_share_links')
    op.drop_index('ix_medical_documents_care_profile_id', table_name='medical_documents')
    op.drop_table('medical_documents')
    op.drop_table('parent_privacy')
    op.drop_table('care_cards')
    op.drop_index('ix_care_contacts_care_profile_id', table_name='care_contacts')
    op.drop_table('care_contacts')
    op.drop_index('ix_family_posts_care_profile_id', table_name='family_posts')
    op.drop_table('family_posts')
    op.drop_index('ix_help_requests_care_profile_id', table_name='help_requests')
    op.drop_table('help_requests')
    op.drop_index('ix_refill_requests_medicine_id', table_name='refill_requests')
    op.drop_table('refill_requests')
    op.drop_table('care_alerts_sent')
    op.drop_table('daily_fine')
