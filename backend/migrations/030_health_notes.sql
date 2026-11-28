BEGIN;

-- A parent's allergies, conditions and readings, from chat, uploads and the family
-- (backend/app/models/health_note.py). Run after 029_parent_notes.sql.

CREATE TABLE health_notes (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(16) NOT NULL, 
    label VARCHAR(120) NOT NULL, 
    value VARCHAR(60), 
    value_num FLOAT, 
    value_num2 FLOAT, 
    source VARCHAR(16) NOT NULL, 
    source_text TEXT, 
    active BOOLEAN NOT NULL, 
    recorded_by_user_id VARCHAR(36), 
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id), 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id), 
    FOREIGN KEY(recorded_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_health_notes_profile_kind ON health_notes (care_profile_id, kind, recorded_at);

UPDATE alembic_version SET version_num='b8d4f0a2c6e3' WHERE alembic_version.version_num = 'a7c3e9f1b5d2';

COMMIT;
