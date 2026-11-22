BEGIN;

-- Adds the meal_logs table (backend/app/models/meal.py): what the parent said they ate, from the chatbot.

CREATE TABLE meal_logs (
    id VARCHAR(36) NOT NULL,
    family_id VARCHAR(36) NOT NULL,
    care_profile_id VARCHAR(36) NOT NULL,
    checkin_id VARCHAR(36),
    log_date DATE NOT NULL,
    meals VARCHAR(32) NOT NULL,
    text TEXT NOT NULL,
    recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
    recorded_by_user_id VARCHAR(36),
    PRIMARY KEY (id),
    FOREIGN KEY(family_id) REFERENCES families (id),
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id),
    FOREIGN KEY(checkin_id) REFERENCES health_checkins (id),
    FOREIGN KEY(recorded_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_meal_logs_profile_date ON meal_logs (care_profile_id, log_date);

UPDATE alembic_version SET version_num='7b8c9d0e1f28' WHERE alembic_version.version_num = '6a7b8c9d0e16';

COMMIT;
