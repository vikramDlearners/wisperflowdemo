BEGIN;

-- Adds parent_onboarding_profiles.care_profile_id (optional FK to care_profiles.id; set for a parent with no linked account)
-- and makes parent_onboarding_profiles.user_id nullable.
-- Matches alembic revision 3d4e5f6a7b82 (backend/alembic/versions).

ALTER TABLE parent_onboarding_profiles ADD COLUMN care_profile_id VARCHAR(36) REFERENCES care_profiles(id);

ALTER TABLE parent_onboarding_profiles ALTER COLUMN user_id DROP NOT NULL;

UPDATE alembic_version SET version_num='3d4e5f6a7b82' WHERE alembic_version.version_num = '2c3d4e5f6a71';

COMMIT;
