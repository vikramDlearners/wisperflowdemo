BEGIN;

-- Insurance policies the family keeps track of, with their renewal dates (backend/app/models/insurance.py).

CREATE TABLE insurance_policies (
    id VARCHAR(36) PRIMARY KEY,
    family_id VARCHAR(36) NOT NULL REFERENCES families (id) ON DELETE CASCADE,
    care_profile_id VARCHAR(36) REFERENCES care_profiles (id) ON DELETE SET NULL,
    policy_type VARCHAR(32) NOT NULL,
    insurer VARCHAR(120) NOT NULL,
    plan_name VARCHAR(160),
    policy_number VARCHAR(80),
    sum_insured NUMERIC(14, 2),
    premium NUMERIC(12, 2),
    premium_frequency VARCHAR(16) NOT NULL,
    start_date DATE,
    renewal_date DATE NOT NULL,
    last_renewed_on DATE,
    agent_name VARCHAR(120),
    agent_phone VARCHAR(32),
    helpline VARCHAR(32),
    notes TEXT,
    responsible_user_id VARCHAR(36) REFERENCES users (id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL
);
CREATE INDEX ix_insurance_policies_family_id ON insurance_policies (family_id);

UPDATE alembic_version SET version_num='b8d4e1f6a3c9' WHERE alembic_version.version_num = 'a7e3f9c2b6d1';

COMMIT;
