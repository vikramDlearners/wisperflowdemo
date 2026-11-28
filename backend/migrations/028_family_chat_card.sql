BEGIN;

-- A card shown under a family Chat answer, e.g. the month's analysis (backend/app/models/family_chat.py).

ALTER TABLE family_chat_messages ADD COLUMN card JSON;

UPDATE alembic_version SET version_num='d3a6b9e2c5f1' WHERE alembic_version.version_num = 'c9f5a2d7b4e8';

COMMIT;
