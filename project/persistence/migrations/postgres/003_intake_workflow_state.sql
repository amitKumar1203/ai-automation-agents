ALTER TABLE intake_submissions
    ADD COLUMN IF NOT EXISTS classification_category TEXT,
    ADD COLUMN IF NOT EXISTS classification_confidence DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS classification_reasoning TEXT,
    ADD COLUMN IF NOT EXISTS classification_model TEXT,
    ADD COLUMN IF NOT EXISTS approval_status TEXT NOT NULL DEFAULT 'not_required',
    ADD COLUMN IF NOT EXISTS approval_actor TEXT,
    ADD COLUMN IF NOT EXISTS approval_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS execution_status TEXT NOT NULL DEFAULT 'not_started',
    ADD COLUMN IF NOT EXISTS monday_result_json JSONB,
    ADD COLUMN IF NOT EXISTS notification_result_json JSONB,
    ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_intake_submissions_status_updated
    ON intake_submissions (status, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_classification_attempts_submission_started
    ON classification_attempts (submission_id, started_at DESC, id);
