BEGIN;

-- Adds medicines.purpose (short purpose label, optional)
-- and appointments.location (where the appointment takes place, optional).
-- Matches alembic revision 1b2c3d4e5f60 (backend/alembic/versions).

ALTER TABLE medicines ADD COLUMN purpose VARCHAR(120);

ALTER TABLE appointments ADD COLUMN location VARCHAR(255);

UPDATE alembic_version SET version_num='1b2c3d4e5f60' WHERE alembic_version.version_num = '0a1b2c3d4e5f';

COMMIT;
