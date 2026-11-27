BEGIN;

-- After a visit: the appointment's fee and the doctor's notes (backend/app/models/appointment.py),
-- and which appointment each medicine was given at (backend/app/models/medicine.py).

ALTER TABLE appointments ADD COLUMN fee NUMERIC(10, 2);
ALTER TABLE appointments ADD COLUMN doctor_notes TEXT;

ALTER TABLE medicines ADD COLUMN appointment_id VARCHAR(36);
ALTER TABLE medicines ADD CONSTRAINT fk_medicines_appointment_id
    FOREIGN KEY (appointment_id) REFERENCES appointments (id) ON DELETE SET NULL;
CREATE INDEX ix_medicines_appointment_id ON medicines (appointment_id);

UPDATE alembic_version SET version_num='e4c1b7a9d2f3' WHERE alembic_version.version_num = 'b1c2d3e4f5a6';

COMMIT;
