CREATE TABLE IF NOT EXISTS operator_accounts (
    email TEXT PRIMARY KEY,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('operator', 'reviewer', 'admin')),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    last_login_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_operator_accounts_role
    ON operator_accounts (role, active);
