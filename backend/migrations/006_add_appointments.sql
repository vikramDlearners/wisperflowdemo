BEGIN;

-- Adds the appointments table (backend/app/models/appointment.py).

CREATE TABLE appointments (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    scheduled_date DATE NOT NULL,
    start_time VARCHAR(8) NOT NULL,
    provider VARCHAR(255) NOT NULL,
    reason VARCHAR(255) NOT NULL,
    notes TEXT NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id)
);

COMMIT;
