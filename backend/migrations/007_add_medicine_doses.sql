BEGIN;

-- Adds the medicine_doses table (backend/app/models/dose.py).

CREATE TABLE medicine_doses (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    medicine_id VARCHAR(36) NOT NULL,
    dose_date DATE NOT NULL,
    slot VARCHAR(8) NOT NULL,
    status VARCHAR(16) NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    recorded_by_user_id VARCHAR(36),
    source VARCHAR(16) NOT NULL,
    remind_at TIMESTAMP WITH TIME ZONE,
    family_alerted_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT uq_medicine_dose_slot UNIQUE (medicine_id, dose_date, slot),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id),
    FOREIGN KEY(medicine_id) REFERENCES medicines (id),
    FOREIGN KEY(recorded_by_user_id) REFERENCES users (id)
);

UPDATE alembic_version SET version_num='c1d2e3f4a5b6' WHERE alembic_version.version_num = 'a9c4e2b7d1f0';

COMMIT;
