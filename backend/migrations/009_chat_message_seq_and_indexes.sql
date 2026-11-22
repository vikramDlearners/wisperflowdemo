BEGIN;

-- Adds chat_messages.seq (conversation order 1..n per check-in, so the order is the same on every database),
-- numbers the existing messages, and adds lookup indexes (backend/app/models/checkin.py, dose.py).

ALTER TABLE chat_messages ADD COLUMN seq INTEGER DEFAULT '0' NOT NULL;

UPDATE chat_messages SET seq = ( SELECT COUNT(*) FROM chat_messages AS earlier WHERE earlier.checkin_id = chat_messages.checkin_id AND (earlier.created_at < chat_messages.created_at OR (earlier.created_at = chat_messages.created_at AND earlier.id <= chat_messages.id)));

CREATE INDEX ix_chat_messages_checkin_id ON chat_messages (checkin_id);

CREATE INDEX ix_medicine_doses_profile_date ON medicine_doses (care_profile_id, dose_date);

UPDATE alembic_version SET version_num='f7a8b9c0d1e2' WHERE alembic_version.version_num = 'd2e3f4a5b6c7';

COMMIT;
