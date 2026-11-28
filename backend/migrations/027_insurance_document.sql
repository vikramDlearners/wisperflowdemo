BEGIN;

-- The policy document (PDF or a photo) attached to an insurance policy (backend/app/models/insurance.py).

ALTER TABLE insurance_policies ADD COLUMN document_data BYTEA;
ALTER TABLE insurance_policies ADD COLUMN document_content_type VARCHAR(100);
ALTER TABLE insurance_policies ADD COLUMN document_name VARCHAR(200);

UPDATE alembic_version SET version_num='c9f5a2d7b4e8' WHERE alembic_version.version_num = 'b8d4e1f6a3c9';

COMMIT;
