BEGIN;

-- Adds health_checkins.session_seq (backend/app/models/checkin.py): the first message of the conversation on
-- screen; each opening of the parent chat starts a new one.

ALTER TABLE health_checkins ADD COLUMN session_seq INTEGER;

UPDATE alembic_version SET version_num='8c9d0e1f2a39' WHERE alembic_version.version_num = '7b8c9d0e1f28';

COMMIT;
