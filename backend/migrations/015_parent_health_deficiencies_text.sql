BEGIN;

-- Replaces the four deficiency inputs with one free-text "deficiencies" column on parent_onboarding_profiles.
-- The earlier calcium/sugar columns from 014 are left in place.
-- Matches alembic revision 5f6a7b8c9d05 (backend/alembic/versions).

ALTER TABLE parent_onboarding_profiles ADD COLUMN deficiencies TEXT;

UPDATE alembic_version SET version_num='5f6a7b8c9d05' WHERE alembic_version.version_num = '4e5f6a7b8c94';

COMMIT;
