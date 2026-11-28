-- The parent and family features from TODO.md: the daily "I'm fine" button, the care circle,
-- the medical file and doctor links, siblings' expenses and visits, video calls, paperwork and the carer's day
-- (backend/app/models/care_circle.py). Run after 030_health_notes.sql.

BEGIN;

-- Running upgrade b8d4f0a2c6e3 -> c9e5a1b3d7f4

CREATE TABLE daily_fine (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    day DATE NOT NULL, 
    fine_at TIMESTAMP WITH TIME ZONE, 
    asked_at TIMESTAMP WITH TIME ZONE, 
    family_told_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_daily_fine_profile_day UNIQUE (care_profile_id, day), 
    FOREIGN KEY(family_id) REFERENCES families (id), 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id)
);

CREATE TABLE care_alerts_sent (
    id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(40) NOT NULL, 
    period VARCHAR(20) NOT NULL, 
    sent_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    CONSTRAINT uq_care_alert_once UNIQUE (care_profile_id, kind, period), 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id)
);

CREATE TABLE refill_requests (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    medicine_id VARCHAR(36) NOT NULL, 
    tablets_left INTEGER, 
    asked_user_id VARCHAR(36), 
    task_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id), 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id), 
    FOREIGN KEY(medicine_id) REFERENCES medicines (id), 
    FOREIGN KEY(asked_user_id) REFERENCES users (id), 
    FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX ix_refill_requests_medicine_id ON refill_requests (medicine_id);

CREATE TABLE help_requests (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    note TEXT, 
    status VARCHAR(12) NOT NULL, 
    asked_by_user_id VARCHAR(36), 
    decided_by_user_id VARCHAR(36), 
    task_id VARCHAR(36), 
    amount NUMERIC(12, 2), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    decided_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(asked_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(decided_by_user_id) REFERENCES users (id), 
    FOREIGN KEY(task_id) REFERENCES tasks (id)
);

CREATE INDEX ix_help_requests_care_profile_id ON help_requests (care_profile_id);

CREATE TABLE family_posts (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    author_user_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(8) NOT NULL, 
    text TEXT, 
    data BYTEA, 
    content_type VARCHAR(100), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    seen_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(author_user_id) REFERENCES users (id)
);

CREATE INDEX ix_family_posts_care_profile_id ON family_posts (care_profile_id);

CREATE TABLE care_contacts (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    name VARCHAR(120) NOT NULL, 
    role VARCHAR(20) NOT NULL, 
    phone VARCHAR(30), 
    address VARCHAR(240), 
    birthday_month INTEGER, 
    birthday_day INTEGER, 
    sort_order INTEGER NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE
);

CREATE INDEX ix_care_contacts_care_profile_id ON care_contacts (care_profile_id);

CREATE TABLE care_cards (
    id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    blood_group VARCHAR(8), 
    emergency_name VARCHAR(120), 
    emergency_phone VARCHAR(30), 
    notes TEXT, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (care_profile_id), 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE
);

CREATE TABLE parent_privacy (
    id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    share_words BOOLEAN NOT NULL, 
    share_chats BOOLEAN NOT NULL, 
    video_auto_answer BOOLEAN NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    UNIQUE (care_profile_id), 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE
);

CREATE TABLE medical_documents (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(20) NOT NULL, 
    title VARCHAR(160) NOT NULL, 
    doc_date DATE, 
    text TEXT, 
    data BYTEA, 
    content_type VARCHAR(100), 
    file_name VARCHAR(200), 
    uploaded_by_user_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(uploaded_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_medical_documents_care_profile_id ON medical_documents (care_profile_id);

CREATE TABLE medical_share_links (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    created_by_user_id VARCHAR(36) NOT NULL, 
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    revoked_at TIMESTAMP WITH TIME ZONE, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_medical_share_links_care_profile_id ON medical_share_links (care_profile_id);

CREATE TABLE care_expenses (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    paid_by_user_id VARCHAR(36) NOT NULL, 
    amount NUMERIC(12, 2) NOT NULL, 
    what VARCHAR(160) NOT NULL, 
    spent_on DATE NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(paid_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_care_expenses_care_profile_id ON care_expenses (care_profile_id);

CREATE TABLE care_visits (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    visit_date DATE NOT NULL, 
    appointment_id VARCHAR(36), 
    note VARCHAR(240), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id), 
    FOREIGN KEY(appointment_id) REFERENCES appointments (id)
);

CREATE INDEX ix_care_visits_care_profile_id ON care_visits (care_profile_id);

CREATE TABLE video_calls (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    caller_user_id VARCHAR(36) NOT NULL, 
    status VARCHAR(12) NOT NULL, 
    offer TEXT, 
    answer TEXT, 
    caller_ice JSON NOT NULL, 
    callee_ice JSON NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    answered_at TIMESTAMP WITH TIME ZONE, 
    ended_at TIMESTAMP WITH TIME ZONE, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(caller_user_id) REFERENCES users (id)
);

CREATE INDEX ix_video_calls_care_profile_id ON video_calls (care_profile_id);

CREATE TABLE paperwork_items (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(24) NOT NULL, 
    title VARCHAR(160) NOT NULL, 
    due_date DATE NOT NULL, 
    note TEXT, 
    done_on DATE, 
    created_by_user_id VARCHAR(36), 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(created_by_user_id) REFERENCES users (id)
);

CREATE INDEX ix_paperwork_items_care_profile_id ON paperwork_items (care_profile_id);

CREATE TABLE carer_reports (
    id VARCHAR(36) NOT NULL, 
    family_id VARCHAR(36) NOT NULL, 
    care_profile_id VARCHAR(36) NOT NULL, 
    user_id VARCHAR(36) NOT NULL, 
    kind VARCHAR(12) NOT NULL, 
    text TEXT NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
    PRIMARY KEY (id), 
    FOREIGN KEY(family_id) REFERENCES families (id) ON DELETE CASCADE, 
    FOREIGN KEY(care_profile_id) REFERENCES care_profiles (id) ON DELETE CASCADE, 
    FOREIGN KEY(user_id) REFERENCES users (id)
);

CREATE INDEX ix_carer_reports_care_profile_id ON carer_reports (care_profile_id);

UPDATE alembic_version SET version_num='c9e5a1b3d7f4' WHERE alembic_version.version_num = 'b8d4f0a2c6e3';

COMMIT;

