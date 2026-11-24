BEGIN;

-- Adds an uploaded profile photo to parent_onboarding_profiles (backend/app/models/parent_onboarding_profile.py).

ALTER TABLE parent_onboarding_profiles ADD COLUMN profile_photo_data BYTEA;
ALTER TABLE parent_onboarding_profiles ADD COLUMN profile_photo_content_type VARCHAR(100);

UPDATE alembic_version SET version_num='af1e2d3c4b5a' WHERE alembic_version.version_num = '9d0e1f2a3b4a';

COMMIT;
