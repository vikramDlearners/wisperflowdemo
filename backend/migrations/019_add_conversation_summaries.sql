BEGIN;

-- Adds the conversation_summaries table (backend/app/models/conversation_summary.py): a Gemini summary of each
-- finished part of a parent's chat; important points also become tasks for caretakers and managers.

CREATE TABLE conversation_summaries (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    checkin_id VARCHAR(36) NOT NULL,
    from_seq INTEGER NOT NULL,
    to_seq INTEGER NOT NULL,
    summary TEXT NOT NULL,
    important JSON,
    source VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_conversation_summary_part UNIQUE (checkin_id, from_seq),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id),
    FOREIGN KEY(checkin_id) REFERENCES health_checkins (id)
);

CREATE INDEX ix_conversation_summaries_checkin_id ON conversation_summaries (checkin_id);

UPDATE alembic_version SET version_num='9d0e1f2a3b4a' WHERE alembic_version.version_num = '8c9d0e1f2a39';

COMMIT;
