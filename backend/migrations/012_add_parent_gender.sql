BEGIN;

-- Adds parent_onboarding_profiles.gender (optional; 'male' / 'female', NULL = unset).
-- Matches alembic revision 2c3d4e5f6a71 (backend/alembic/versions).

ALTER TABLE parent_onboarding_profiles ADD COLUMN gender VARCHAR(16);

UPDATE alembic_version SET version_num='2c3d4e5f6a71' WHERE alembic_version.version_num = '1b2c3d4e5f60';

COMMIT;
