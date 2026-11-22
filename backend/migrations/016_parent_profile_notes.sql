BEGIN;

-- Adds one free-text "notes" column on parent_onboarding_profiles, saved in the medical section next to "deficiencies".
-- Matches alembic revision 6a7b8c9d0e16 (backend/alembic/versions).

ALTER TABLE parent_onboarding_profiles ADD COLUMN notes TEXT;

UPDATE alembic_version SET version_num='6a7b8c9d0e16' WHERE alembic_version.version_num = '5f6a7b8c9d05';

COMMIT;
