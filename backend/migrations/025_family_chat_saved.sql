BEGIN;

-- The family Chat page: each member's own conversations and every question and answer in them
-- (backend/app/models/family_chat.py). Before this they were kept only in the browser.

CREATE TABLE family_chat_conversations (
    id VARCHAR(36) PRIMARY KEY,
    family_id VARCHAR(36) NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title VARCHAR(120) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_family_chat_conversations_user_id ON family_chat_conversations (user_id);

CREATE TABLE family_chat_messages (
    id VARCHAR(36) PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL REFERENCES family_chat_conversations (id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    role VARCHAR(16) NOT NULL,
    text TEXT NOT NULL,
    destination VARCHAR(60),
    source VARCHAR(16),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_family_chat_messages_conversation_id ON family_chat_messages (conversation_id);

UPDATE alembic_version SET version_num='a7e3f9c2b6d1' WHERE alembic_version.version_num = 'f5d2c8b1a4e6';

COMMIT;
