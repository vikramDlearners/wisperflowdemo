BEGIN;

-- Notes a parent saves, with an optional reminder for themselves or another family member
-- (backend/app/models/parent_note.py). Run after 028_family_chat_card.sql.

CREATE TABLE parent_notes (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    created_by_user_id VARCHAR(36) NOT NULL,
    text TEXT NOT NULL,
    remind_at TIMESTAMP WITH TIME ZONE,
    remind_user_id VARCHAR(36),
    send_reminder BOOLEAN NOT NULL,
    task_id VARCHAR(36),
    reminded_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id),
    FOREIGN KEY(created_by_user_id) REFERENCES users (id),
    FOREIGN KEY(remind_user_id) REFERENCES users (id),
    FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX ix_parent_notes_care_profile_id ON parent_notes (care_profile_id);
CREATE INDEX ix_parent_notes_due ON parent_notes (reminded_at, remind_at);

UPDATE alembic_version SET version_num='a7c3e9f1b5d2' WHERE alembic_version.version_num = 'd3a6b9e2c5f1';

COMMIT;
