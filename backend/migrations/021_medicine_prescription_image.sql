BEGIN;

-- Adds a photo of the prescription to medicines (backend/app/models/medicine.py), separate from the medicine photo.

ALTER TABLE medicines ADD COLUMN prescription_image_data BYTEA;
ALTER TABLE medicines ADD COLUMN prescription_image_content_type VARCHAR(100);

UPDATE alembic_version SET version_num='c7e1a9d4f2b3' WHERE alembic_version.version_num = 'af1e2d3c4b5a';

COMMIT;
