BEGIN;

-- Running upgrade d4e5f6a7b8c9 -> e5f6a7b8c9d0

CREATE TABLE prescription_scans (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    uploaded_by_user_id VARCHAR(36) NOT NULL,
    document_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    proposed JSON,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id),
    FOREIGN KEY(uploaded_by_user_id) REFERENCES users (id)
);

CREATE TABLE medicine_reminders (
    id VARCHAR(36) NOT NULL,
    medicine_id VARCHAR(36) NOT NULL,
    time_of_day VARCHAR(5) NOT NULL,
    active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(medicine_id) REFERENCES medicines (id)
);

UPDATE alembic_version SET version_num='e5f6a7b8c9d0' WHERE alembic_version.version_num = 'd4e5f6a7b8c9';

COMMIT;
