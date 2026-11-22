BEGIN;

-- Adds the health_checkins and chat_messages tables (backend/app/models/checkin.py).

CREATE TABLE health_checkins (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    parent_user_id VARCHAR(36) NOT NULL,
    checkin_date DATE NOT NULL,
    step VARCHAR(16) NOT NULL,
    health_text TEXT,
    urgent BOOLEAN NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    summary_sent_at TIMESTAMP WITH TIME ZONE,
    pending_medicine_id VARCHAR(36),
    PRIMARY KEY (id),
    CONSTRAINT uq_health_checkin_profile_date UNIQUE (care_profile_id, checkin_date),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id),
    FOREIGN KEY(parent_user_id) REFERENCES users (id)
);

CREATE TABLE chat_messages (
    id VARCHAR(36) NOT NULL,
    checkin_id VARCHAR(36) NOT NULL,
    sender VARCHAR(8) NOT NULL,
    text TEXT NOT NULL,
    language VARCHAR(8) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(checkin_id) REFERENCES health_checkins (id)
);

UPDATE alembic_version SET version_num='d2e3f4a5b6c7' WHERE alembic_version.version_num = 'c1d2e3f4a5b6';

COMMIT;
