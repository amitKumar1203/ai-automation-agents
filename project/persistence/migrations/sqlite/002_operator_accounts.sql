CREATE TABLE IF NOT EXISTS operator_accounts (
    email TEXT PRIMARY KEY,
    display_name TEXT,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('operator', 'reviewer', 'admin')),
    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_login_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_operator_accounts_role
    ON operator_accounts (role, active);
