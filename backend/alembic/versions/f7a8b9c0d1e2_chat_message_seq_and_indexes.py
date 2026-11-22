"""chat_messages.seq (conversation order on every database) and lookup indexes

Revision ID: f7a8b9c0d1e2
Revises: d2e3f4a5b6c7
Create Date: 2026-11-22 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, None] = 'd2e3f4a5b6c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('chat_messages') as batch:
        batch.add_column(sa.Column('seq', sa.Integer(), nullable=False, server_default='0'))
    # Number existing messages 1..n per check-in, oldest first. On SQLite the insertion order (rowid) breaks
    # timestamp ties, as the app did before this column existed.
    tie_break = 'rowid' if op.get_context().dialect.name == 'sqlite' else 'id'
    op.execute(
        "UPDATE chat_messages SET seq = ("
        " SELECT COUNT(*) FROM chat_messages AS earlier"
        " WHERE earlier.checkin_id = chat_messages.checkin_id"
        " AND (earlier.created_at < chat_messages.created_at"
        f" OR (earlier.created_at = chat_messages.created_at AND earlier.{tie_break} <= chat_messages.{tie_break}))"
        ")"
    )
    op.create_index('ix_chat_messages_checkin_id', 'chat_messages', ['checkin_id'])
    op.create_index('ix_medicine_doses_profile_date', 'medicine_doses', ['care_profile_id', 'dose_date'])


def downgrade() -> None:
    op.drop_index('ix_medicine_doses_profile_date', table_name='medicine_doses')
    op.drop_index('ix_chat_messages_checkin_id', table_name='chat_messages')
    with op.batch_alter_table('chat_messages') as batch:
        batch.drop_column('seq')
