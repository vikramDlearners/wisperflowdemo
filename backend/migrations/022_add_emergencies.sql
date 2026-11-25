BEGIN;

-- Adds emergencies (backend/app/models/emergency.py): raised in the parent chat or with the emergency button.
-- Safe to run where the table already exists.

CREATE TABLE IF NOT EXISTS emergencies (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    checkin_id VARCHAR(36),
    reported_by_user_id VARCHAR(36),
    text TEXT NOT NULL,
    source VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    completed_at TIMESTAMP WITH TIME ZONE,
    completed_by_user_id VARCHAR(36),
    PRIMARY KEY (id),
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE,
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE,
    FOREIGN KEY(checkin_id) REFERENCES health_checkins (id) ON DELETE CASCADE,
    FOREIGN KEY(reported_by_user_id) REFERENCES users (id),
    FOREIGN KEY(completed_by_user_id) REFERENCES users (id)
);

CREATE INDEX IF NOT EXISTS ix_emergencies_family_status ON emergencies (family_id, status);

UPDATE alembic_version SET version_num='d8f2b0e5a3c4' WHERE alembic_version.version_num = 'c7e1a9d4f2b3';

COMMIT;
