"""family chat: save each member's conversations and messages

Revision ID: a7e3f9c2b6d1
Revises: f5d2c8b1a4e6
Create Date: 2026-11-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7e3f9c2b6d1'
down_revision: Union[str, None] = 'f5d2c8b1a4e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'family_chat_conversations',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column('family_id', sa.String(length=36), sa.ForeignKey('families.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', sa.String(length=36), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_family_chat_conversations_user_id', 'family_chat_conversations', ['user_id'])
    op.create_table(
        'family_chat_messages',
        sa.Column('id', sa.String(length=36), primary_key=True),
        sa.Column(
            'conversation_id', sa.String(length=36),
            sa.ForeignKey('family_chat_conversations.id', ondelete='CASCADE'), nullable=False,
        ),
        sa.Column('seq', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(length=16), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('destination', sa.String(length=60), nullable=True),
        sa.Column('source', sa.String(length=16), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_family_chat_messages_conversation_id', 'family_chat_messages', ['conversation_id'])


def downgrade() -> None:
    op.drop_index('ix_family_chat_messages_conversation_id', table_name='family_chat_messages')
    op.drop_table('family_chat_messages')
    op.drop_index('ix_family_chat_conversations_user_id', table_name='family_chat_conversations')
    op.drop_table('family_chat_conversations')
