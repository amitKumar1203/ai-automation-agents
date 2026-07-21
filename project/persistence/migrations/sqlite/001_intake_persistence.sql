CREATE TABLE IF NOT EXISTS intake_submissions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    external_submission_id TEXT NOT NULL,
    submitted_by TEXT NOT NULL,
    body TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'received',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (source, external_submission_id)
);

CREATE TABLE IF NOT EXISTS intake_events (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES intake_submissions(id),
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_intake_events_submission
    ON intake_events (submission_id, created_at);

CREATE TRIGGER IF NOT EXISTS intake_events_no_update
BEFORE UPDATE ON intake_events
BEGIN
    SELECT RAISE(ABORT, 'intake_events are append-only');
END;
CREATE TRIGGER IF NOT EXISTS intake_events_no_delete
BEFORE DELETE ON intake_events
BEGIN
    SELECT RAISE(ABORT, 'intake_events are append-only');
END;

CREATE TABLE IF NOT EXISTS background_jobs (
    id TEXT PRIMARY KEY,
    queue TEXT NOT NULL,
    job_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'succeeded', 'dead')),
    available_at TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts > 0),
    lease_owner TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    dead_lettered_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    idempotency_key TEXT,
    UNIQUE (queue, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_background_jobs_claim
    ON background_jobs (queue, status, available_at, lease_expires_at);

CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    delivery_id TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'completed', 'failed')),
    response_json TEXT,
    error TEXT,
    received_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (provider, delivery_id)
);

CREATE TABLE IF NOT EXISTS classification_attempts (
    id TEXT PRIMARY KEY,
    submission_id TEXT NOT NULL REFERENCES intake_submissions(id),
    attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
    model TEXT,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'succeeded', 'failed')),
    category TEXT,
    confidence REAL,
    reasoning TEXT,
    error TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (submission_id, attempt_number)
);

CREATE TABLE IF NOT EXISTS effect_executions (
    id TEXT PRIMARY KEY,
    effect_type TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'started'
        CHECK (status IN ('started', 'completed', 'failed')),
    request_json TEXT NOT NULL,
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    completed_at TEXT,
    UNIQUE (effect_type, idempotency_key)
);
