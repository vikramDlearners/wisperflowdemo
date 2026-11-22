BEGIN;

-- Adds family_members.relationship (mother, father, grandmother, grandfather, other; lowercase, optional)
-- and care_profiles.linked_member_id (the family member a Mother/Father care profile belongs to).
-- Matches alembic revision 0a1b2c3d4e5f (backend/alembic/versions).

ALTER TABLE family_members ADD COLUMN relationship VARCHAR(20);

ALTER TABLE care_profiles ADD COLUMN linked_member_id VARCHAR(36) REFERENCES family_members (id);

UPDATE alembic_version SET version_num='0a1b2c3d4e5f' WHERE alembic_version.version_num = 'e8f9a0b1c2d3';

COMMIT;
