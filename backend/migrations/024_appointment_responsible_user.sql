BEGIN;

-- The family member responsible for an appointment (backend/app/models/appointment.py); they and the family
-- managers are notified when it is marked completed.

ALTER TABLE appointments ADD COLUMN responsible_user_id VARCHAR(36);
ALTER TABLE appointments ADD CONSTRAINT fk_appointments_responsible_user_id
    FOREIGN KEY (responsible_user_id) REFERENCES users (id) ON DELETE SET NULL;

UPDATE alembic_version SET version_num='f5d2c8b1a4e6' WHERE alembic_version.version_num = 'e4c1b7a9d2f3';

COMMIT;
