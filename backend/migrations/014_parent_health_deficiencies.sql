BEGIN;

-- Adds calcium deficiency and sugar problem yes/no flags with optional notes to parent_onboarding_profiles.
-- Matches alembic revision 4e5f6a7b8c94 (backend/alembic/versions).

ALTER TABLE parent_onboarding_profiles ADD COLUMN calcium_deficiency BOOLEAN;
ALTER TABLE parent_onboarding_profiles ADD COLUMN calcium_deficiency_notes TEXT;
ALTER TABLE parent_onboarding_profiles ADD COLUMN sugar_problems BOOLEAN;
ALTER TABLE parent_onboarding_profiles ADD COLUMN sugar_problems_notes TEXT;

UPDATE alembic_version SET version_num='4e5f6a7b8c94' WHERE alembic_version.version_num = '3d4e5f6a7b82';

COMMIT;
