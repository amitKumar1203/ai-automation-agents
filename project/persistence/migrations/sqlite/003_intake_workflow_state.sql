ALTER TABLE intake_submissions ADD COLUMN classification_category TEXT;
ALTER TABLE intake_submissions ADD COLUMN classification_confidence REAL;
ALTER TABLE intake_submissions ADD COLUMN classification_reasoning TEXT;
ALTER TABLE intake_submissions ADD COLUMN classification_model TEXT;
ALTER TABLE intake_submissions ADD COLUMN approval_status TEXT NOT NULL DEFAULT 'not_required';
ALTER TABLE intake_submissions ADD COLUMN approval_actor TEXT;
ALTER TABLE intake_submissions ADD COLUMN approval_at TEXT;
ALTER TABLE intake_submissions ADD COLUMN execution_status TEXT NOT NULL DEFAULT 'not_started';
ALTER TABLE intake_submissions ADD COLUMN monday_result_json TEXT;
ALTER TABLE intake_submissions ADD COLUMN notification_result_json TEXT;
ALTER TABLE intake_submissions ADD COLUMN version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE intake_submissions ADD COLUMN completed_at TEXT;

CREATE INDEX IF NOT EXISTS idx_intake_submissions_status_updated
    ON intake_submissions (status, updated_at DESC, id);
CREATE INDEX IF NOT EXISTS idx_classification_attempts_submission_started
    ON classification_attempts (submission_id, started_at DESC, id);
