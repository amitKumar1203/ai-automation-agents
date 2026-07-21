"""Repositories for durable Intake state, jobs, and idempotent effects."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from persistence.database import Database


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp(value: datetime | None = None) -> str:
    value = value or _now()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _decode(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _dict(row: Any | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def _transaction(conn: Any, backend: str) -> None:
    conn.execute("BEGIN IMMEDIATE" if backend == "sqlite" else "BEGIN")


class IntakeRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def create_submission(
        self,
        *,
        source: str,
        external_submission_id: str,
        submitted_by: str,
        body: str,
        payload: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """Insert once by source/external id, returning (submission, created)."""
        if not source.strip() or not external_submission_id.strip():
            raise ValueError("source and external_submission_id are required")
        submission_id = str(uuid.uuid4())
        now = _timestamp()
        with self.db.connect() as conn:
            _transaction(conn, self.db.backend)
            try:
                cursor = conn.execute(
                    self.db.sql(
                        """
                        INSERT INTO intake_submissions (
                            id, source, external_submission_id, submitted_by,
                            body, payload_json, status, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, 'received', ?, ?)
                        ON CONFLICT (source, external_submission_id) DO NOTHING
                        """
                    ),
                    (
                        submission_id,
                        source.strip(),
                        external_submission_id.strip(),
                        submitted_by,
                        body,
                        self.db.json_value(payload or {}),
                        now,
                        now,
                    ),
                )
                created = cursor.rowcount == 1
                row = conn.execute(
                    self.db.sql(
                        "SELECT * FROM intake_submissions "
                        "WHERE source = ? AND external_submission_id = ?"
                    ),
                    (source.strip(), external_submission_id.strip()),
                ).fetchone()
                if created:
                    conn.execute(
                        self.db.sql(
                            """
                            INSERT INTO intake_events
                                (id, submission_id, event_type, data_json, created_at)
                            VALUES (?, ?, 'received', ?, ?)
                            """
                        ),
                        (
                            str(uuid.uuid4()),
                            submission_id,
                            self.db.json_value({"source": source.strip()}),
                            now,
                        ),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self._submission(row), created

    def get_submission(self, submission_id: str) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            row = conn.execute(
                self.db.sql("SELECT * FROM intake_submissions WHERE id = ?"),
                (submission_id,),
            ).fetchone()
        return self._submission(row) if row is not None else None

    def list_submissions(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        limit = min(max(int(limit), 1), 100)
        offset = max(int(offset), 0)
        where, params = (" WHERE status = ?", [status]) if status else ("", [])
        with self.db.connect() as conn:
            total = int(
                conn.execute(
                    self.db.sql(f"SELECT COUNT(*) AS count FROM intake_submissions{where}"),
                    tuple(params),
                ).fetchone()["count"]
            )
            rows = conn.execute(
                self.db.sql(
                    "SELECT * FROM intake_submissions"
                    f"{where} ORDER BY updated_at DESC, id DESC LIMIT ? OFFSET ?"
                ),
                (*params, limit, offset),
            ).fetchall()
        return [self._submission(row) for row in rows], total

    def transition(
        self,
        submission_id: str,
        *,
        status: str,
        event_type: str,
        data: dict[str, Any] | None = None,
        expected_version: int | None = None,
        expected_statuses: tuple[str, ...] | None = None,
        fields: dict[str, Any] | None = None,
        completed: bool = False,
    ) -> dict[str, Any] | None:
        """Atomically update current state and append its immutable event."""
        allowed = {
            "classification_category",
            "classification_confidence",
            "classification_reasoning",
            "classification_model",
            "approval_status",
            "approval_actor",
            "approval_at",
            "execution_status",
            "monday_result_json",
            "notification_result_json",
        }
        values = dict(fields or {})
        invalid = set(values) - allowed
        if invalid:
            raise ValueError(f"unsupported Intake state fields: {sorted(invalid)}")
        for key in ("monday_result_json", "notification_result_json"):
            if key in values and values[key] is not None:
                values[key] = self.db.json_value(values[key])
        now = _timestamp()
        assignments = ["status = ?", "updated_at = ?", "version = version + 1"]
        params: list[Any] = [status, now]
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            params.append(value)
        if completed:
            assignments.append("completed_at = ?")
            params.append(now)
        where = "id = ?"
        params.append(submission_id)
        if expected_version is not None:
            where += " AND version = ?"
            params.append(expected_version)
        if expected_statuses:
            where += " AND status IN (" + ",".join("?" for _ in expected_statuses) + ")"
            params.extend(expected_statuses)
        with self.db.connect() as conn:
            _transaction(conn, self.db.backend)
            try:
                row = conn.execute(
                    self.db.sql(
                        f"UPDATE intake_submissions SET {', '.join(assignments)} "
                        f"WHERE {where} RETURNING *"
                    ),
                    tuple(params),
                ).fetchone()
                if row is None:
                    conn.rollback()
                    return None
                event_data = {"status": status, "version": int(row["version"]), **(data or {})}
                conn.execute(
                    self.db.sql(
                        """
                        INSERT INTO intake_events
                            (id, submission_id, event_type, data_json, created_at)
                        VALUES (?, ?, ?, ?, ?)
                        """
                    ),
                    (
                        str(uuid.uuid4()),
                        submission_id,
                        event_type,
                        self.db.json_value(event_data),
                        now,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return self._submission(row)

    def append_event(
        self,
        submission_id: str,
        event_type: str,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        event_id, created_at = str(uuid.uuid4()), _timestamp()
        with self.db.connect() as conn:
            conn.execute(
                self.db.sql(
                    """
                    INSERT INTO intake_events
                        (id, submission_id, event_type, data_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """
                ),
                (
                    event_id,
                    submission_id,
                    event_type,
                    self.db.json_value(data or {}),
                    created_at,
                ),
            )
            conn.commit()
        return {
            "id": event_id,
            "submission_id": submission_id,
            "event_type": event_type,
            "data": data or {},
            "created_at": created_at,
        }

    def list_events(
        self, submission_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 100)
        offset = max(int(offset), 0)
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql(
                    "SELECT * FROM intake_events WHERE submission_id = ? "
                    "ORDER BY created_at, id LIMIT ? OFFSET ?"
                ),
                (submission_id, limit, offset),
            ).fetchall()
        return [
            {
                **dict(row),
                "data": _decode(row["data_json"]),
            }
            for row in rows
        ]

    @staticmethod
    def _submission(row: Any) -> dict[str, Any]:
        result = dict(row)
        result["payload"] = _decode(result.pop("payload_json"))
        for key in ("monday_result_json", "notification_result_json"):
            if key in result:
                raw = result.pop(key)
                result[key.removesuffix("_json")] = _decode(raw) if raw is not None else None
        return result


@dataclass(frozen=True)
class Job:
    id: str
    queue: str
    job_type: str
    payload: dict[str, Any]
    status: str
    available_at: Any
    attempts: int
    max_attempts: int
    lease_owner: str | None
    lease_expires_at: Any | None
    last_error: str | None
    dead_lettered_at: Any | None
    idempotency_key: str | None

    @classmethod
    def from_row(cls, row: Any) -> "Job":
        values = dict(row)
        values["payload"] = _decode(values.pop("payload_json"))
        allowed = cls.__dataclass_fields__.keys()
        return cls(**{key: values[key] for key in allowed})


class JobRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def enqueue(
        self,
        *,
        queue: str,
        job_type: str,
        payload: dict[str, Any],
        available_at: datetime | None = None,
        max_attempts: int = 5,
        idempotency_key: str | None = None,
    ) -> tuple[Job, bool]:
        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        job_id, now = str(uuid.uuid4()), _timestamp()
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    INSERT INTO background_jobs (
                        id, queue, job_type, payload_json, status, available_at,
                        attempts, max_attempts, created_at, updated_at,
                        idempotency_key
                    ) VALUES (?, ?, ?, ?, 'pending', ?, 0, ?, ?, ?, ?)
                    ON CONFLICT (queue, idempotency_key) DO NOTHING
                    """
                ),
                (
                    job_id,
                    queue,
                    job_type,
                    self.db.json_value(payload),
                    _timestamp(available_at),
                    max_attempts,
                    now,
                    now,
                    idempotency_key,
                ),
            )
            created = cursor.rowcount == 1
            if created:
                row = conn.execute(
                    self.db.sql("SELECT * FROM background_jobs WHERE id = ?"),
                    (job_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    self.db.sql(
                        "SELECT * FROM background_jobs "
                        "WHERE queue = ? AND idempotency_key = ?"
                    ),
                    (queue, idempotency_key),
                ).fetchone()
            conn.commit()
        return Job.from_row(row), created

    def claim(
        self,
        *,
        queue: str,
        worker_id: str,
        lease_seconds: int = 60,
        now: datetime | None = None,
    ) -> Job | None:
        if lease_seconds < 1:
            raise ValueError("lease_seconds must be positive")
        claimed_at = now or _now()
        now_text = _timestamp(claimed_at)
        expires = _timestamp(claimed_at + timedelta(seconds=lease_seconds))
        with self.db.connect() as conn:
            _transaction(conn, self.db.backend)
            try:
                lock = " FOR UPDATE SKIP LOCKED" if self.db.backend == "postgres" else ""
                candidate = conn.execute(
                    self.db.sql(
                        """
                        SELECT id FROM background_jobs
                        WHERE queue = ?
                          AND available_at <= ?
                          AND (
                            status = 'pending'
                            OR (status = 'running' AND lease_expires_at <= ?)
                          )
                        ORDER BY available_at, created_at, id
                        LIMIT 1
                        """
                        + lock
                    ),
                    (queue, now_text, now_text),
                ).fetchone()
                if candidate is None:
                    conn.commit()
                    return None
                row = conn.execute(
                    self.db.sql(
                        """
                        UPDATE background_jobs
                        SET status = 'running', attempts = attempts + 1,
                            lease_owner = ?, lease_expires_at = ?, updated_at = ?
                        WHERE id = ?
                        RETURNING *
                        """
                    ),
                    (worker_id, expires, now_text, candidate["id"]),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return Job.from_row(row)

    def complete(self, job_id: str, *, worker_id: str) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    UPDATE background_jobs
                    SET status = 'succeeded', lease_owner = NULL,
                        lease_expires_at = NULL, updated_at = ?
                    WHERE id = ? AND status = 'running' AND lease_owner = ?
                    """
                ),
                (_timestamp(), job_id, worker_id),
            )
            conn.commit()
        return cursor.rowcount == 1

    def fail(
        self,
        job_id: str,
        *,
        worker_id: str,
        error: str,
        retry_delay_seconds: float = 0,
        now: datetime | None = None,
    ) -> Job | None:
        failed_at = now or _now()
        with self.db.connect() as conn:
            _transaction(conn, self.db.backend)
            try:
                lock = " FOR UPDATE" if self.db.backend == "postgres" else ""
                row = conn.execute(
                    self.db.sql(
                        "SELECT * FROM background_jobs "
                        "WHERE id = ? AND status = 'running' AND lease_owner = ?"
                        + lock
                    ),
                    (job_id, worker_id),
                ).fetchone()
                if row is None:
                    conn.commit()
                    return None
                dead = int(row["attempts"]) >= int(row["max_attempts"])
                status = "dead" if dead else "pending"
                available = _timestamp(
                    failed_at + timedelta(seconds=max(0, retry_delay_seconds))
                )
                updated = conn.execute(
                    self.db.sql(
                        """
                        UPDATE background_jobs
                        SET status = ?, available_at = ?, lease_owner = NULL,
                            lease_expires_at = NULL, last_error = ?,
                            dead_lettered_at = ?, updated_at = ?
                        WHERE id = ?
                        RETURNING *
                        """
                    ),
                    (
                        status,
                        available,
                        error,
                        _timestamp(failed_at) if dead else None,
                        _timestamp(failed_at),
                        job_id,
                    ),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return Job.from_row(updated)

    def dead_letter(
        self, job_id: str, *, worker_id: str, error: str
    ) -> Job | None:
        """Permanently fail a claimed job without consuming remaining retries."""
        now = _timestamp()
        with self.db.connect() as conn:
            row = conn.execute(
                self.db.sql(
                    """
                    UPDATE background_jobs
                    SET status = 'dead', lease_owner = NULL,
                        lease_expires_at = NULL, last_error = ?,
                        dead_lettered_at = ?, updated_at = ?
                    WHERE id = ? AND status = 'running' AND lease_owner = ?
                    RETURNING *
                    """
                ),
                (error, now, now, job_id, worker_id),
            ).fetchone()
            conn.commit()
        return Job.from_row(row) if row is not None else None

    def retry_dead(self, job_id: str) -> Job | None:
        """Requeue a dead-lettered job after an authorized operator retry."""
        now = _timestamp()
        with self.db.connect() as conn:
            row = conn.execute(
                self.db.sql(
                    """
                    UPDATE background_jobs
                    SET status = 'pending', attempts = 0, available_at = ?,
                        lease_owner = NULL, lease_expires_at = NULL,
                        last_error = NULL, dead_lettered_at = NULL, updated_at = ?
                    WHERE id = ? AND status = 'dead'
                    RETURNING *
                    """
                ),
                (now, now, job_id),
            ).fetchone()
            conn.commit()
        return Job.from_row(row) if row is not None else None

    def list_for_submission(
        self, submission_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[Job]:
        limit = min(max(int(limit), 1), 100)
        offset = max(int(offset), 0)
        predicate = (
            "payload_json ->> 'submission_id' = ?"
            if self.db.backend == "postgres"
            else "json_extract(payload_json, '$.submission_id') = ?"
        )
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql(
                    "SELECT * FROM background_jobs "
                    f"WHERE {predicate} ORDER BY created_at DESC, id DESC "
                    "LIMIT ? OFFSET ?"
                ),
                (submission_id, limit, offset),
            ).fetchall()
        return [Job.from_row(row) for row in rows]

    def get(self, job_id: str) -> Job | None:
        with self.db.connect() as conn:
            row = conn.execute(
                self.db.sql("SELECT * FROM background_jobs WHERE id = ?"),
                (job_id,),
            ).fetchone()
        return Job.from_row(row) if row is not None else None

    def list_jobs(
        self,
        *,
        queues: list[str] | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[Job]:
        """List recent jobs filtered by queue and/or status."""
        limit = min(max(int(limit), 1), 200)
        clauses: list[str] = []
        params: list[Any] = []
        if queues:
            placeholders = ", ".join("?" for _ in queues)
            clauses.append(f"queue IN ({placeholders})")
            params.extend(queues)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql(
                    f"SELECT * FROM background_jobs {where} "
                    "ORDER BY created_at DESC, id DESC LIMIT ?"
                ),
                (*params, limit),
            ).fetchall()
        return [Job.from_row(row) for row in rows]

    def count_by_status(
        self, *, queues: list[str] | None = None
    ) -> dict[str, Any]:
        """Return pending/running/succeeded/dead counts (optionally per queue)."""
        clauses: list[str] = []
        params: list[Any] = []
        if queues:
            placeholders = ", ".join("?" for _ in queues)
            clauses.append(f"queue IN ({placeholders})")
            params.extend(queues)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql(
                    f"""
                    SELECT queue, status, COUNT(*) AS cnt
                    FROM background_jobs
                    {where}
                    GROUP BY queue, status
                    """
                ),
                tuple(params),
            ).fetchall()
        by_queue: dict[str, dict[str, int]] = {}
        totals: dict[str, int] = {
            "pending": 0,
            "running": 0,
            "succeeded": 0,
            "dead": 0,
        }
        for row in rows:
            queue = str(row["queue"])
            status = str(row["status"])
            count = int(row["cnt"])
            by_queue.setdefault(queue, {})[status] = count
            if status in totals:
                totals[status] += count
        return {"totals": totals, "by_queue": by_queue}


class WebhookDeliveryRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def begin(
        self,
        *,
        provider: str,
        delivery_id: str,
        payload: bytes | str,
    ) -> tuple[dict[str, Any], bool]:
        raw = payload.encode() if isinstance(payload, str) else payload
        digest, delivery_pk, now = hashlib.sha256(raw).hexdigest(), str(uuid.uuid4()), _timestamp()
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    INSERT INTO webhook_deliveries (
                        id, provider, delivery_id, payload_hash, status, received_at
                    ) VALUES (?, ?, ?, ?, 'processing', ?)
                    ON CONFLICT (provider, delivery_id) DO NOTHING
                    """
                ),
                (delivery_pk, provider, delivery_id, digest, now),
            )
            created = cursor.rowcount == 1
            row = conn.execute(
                self.db.sql(
                    "SELECT * FROM webhook_deliveries "
                    "WHERE provider = ? AND delivery_id = ?"
                ),
                (provider, delivery_id),
            ).fetchone()
            conn.commit()
        result = dict(row)
        if result["payload_hash"] != digest:
            raise ValueError("delivery id was reused with a different payload")
        if result.get("response_json") is not None:
            result["response"] = _decode(result["response_json"])
        return result, created

    def finish(
        self,
        delivery_pk: str,
        *,
        response: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        status = "failed" if error else "completed"
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    UPDATE webhook_deliveries
                    SET status = ?, response_json = ?, error = ?, completed_at = ?
                    WHERE id = ? AND status = 'processing'
                    """
                ),
                (
                    status,
                    self.db.json_value(response) if response is not None else None,
                    error,
                    _timestamp(),
                    delivery_pk,
                ),
            )
            conn.commit()
        return cursor.rowcount == 1


class OperatorRepository:
    ROLES = frozenset({"operator", "reviewer", "admin"})

    def __init__(self, database: Database) -> None:
        self.db = database

    @staticmethod
    def _email(value: str) -> str:
        email = value.strip().lower()
        if not email or "@" not in email:
            raise ValueError("a valid operator email is required")
        return email

    def ensure(
        self,
        email: str,
        *,
        display_name: str | None = None,
        default_role: str = "operator",
    ) -> dict[str, Any]:
        """Create a first-login operator without overwriting an assigned role."""
        normalized = self._email(email)
        if default_role not in self.ROLES:
            raise ValueError(f"invalid operator role: {default_role}")
        now = _timestamp()
        with self.db.connect() as conn:
            conn.execute(
                self.db.sql(
                    """
                    INSERT INTO operator_accounts (
                        email, display_name, role, active,
                        created_at, updated_at, last_login_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (email) DO UPDATE SET
                        display_name = COALESCE(excluded.display_name, operator_accounts.display_name),
                        updated_at = excluded.updated_at,
                        last_login_at = excluded.last_login_at
                    """
                ),
                (
                    normalized,
                    display_name.strip() if display_name and display_name.strip() else None,
                    default_role,
                    True,
                    now,
                    now,
                    now,
                ),
            )
            row = conn.execute(
                self.db.sql("SELECT * FROM operator_accounts WHERE email = ?"),
                (normalized,),
            ).fetchone()
            conn.commit()
        return dict(row)

    def get(self, email: str) -> dict[str, Any] | None:
        normalized = self._email(email)
        with self.db.connect() as conn:
            row = conn.execute(
                self.db.sql("SELECT * FROM operator_accounts WHERE email = ?"),
                (normalized,),
            ).fetchone()
        return _dict(row)

    def list_all(self) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql(
                    """
                    SELECT email, display_name, role, active,
                           created_at, updated_at, last_login_at
                    FROM operator_accounts
                    ORDER BY email ASC
                    """
                ),
            ).fetchall()
        return [_dict(row) for row in rows]

    def set_role(self, email: str, role: str) -> bool:
        if role not in self.ROLES:
            raise ValueError(f"invalid operator role: {role}")
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    "UPDATE operator_accounts SET role = ?, updated_at = ? WHERE email = ?"
                ),
                (role, _timestamp(), self._email(email)),
            )
            conn.commit()
        return cursor.rowcount == 1

    def set_active(self, email: str, active: bool) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    "UPDATE operator_accounts SET active = ?, updated_at = ? WHERE email = ?"
                ),
                (bool(active), _timestamp(), self._email(email)),
            )
            conn.commit()
        return cursor.rowcount == 1


class ClassificationAttemptRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def start(self, submission_id: str, *, model: str | None = None) -> dict[str, Any]:
        attempt_id, now = str(uuid.uuid4()), _timestamp()
        with self.db.connect() as conn:
            _transaction(conn, self.db.backend)
            try:
                lock = " FOR UPDATE" if self.db.backend == "postgres" else ""
                conn.execute(
                    self.db.sql("SELECT id FROM intake_submissions WHERE id = ?" + lock),
                    (submission_id,),
                ).fetchone()
                row = conn.execute(
                    self.db.sql(
                        """
                        INSERT INTO classification_attempts (
                            id, submission_id, attempt_number, model, status, started_at
                        )
                        SELECT ?, ?, COALESCE(MAX(attempt_number), 0) + 1,
                               ?, 'started', ?
                        FROM classification_attempts WHERE submission_id = ?
                        RETURNING *
                        """
                    ),
                    (attempt_id, submission_id, model, now, submission_id),
                ).fetchone()
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        return dict(row)

    def finish(
        self,
        attempt_id: str,
        *,
        category: str | None = None,
        confidence: float | None = None,
        reasoning: str | None = None,
        error: str | None = None,
    ) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    UPDATE classification_attempts
                    SET status = ?, category = ?, confidence = ?, reasoning = ?,
                        error = ?, completed_at = ?
                    WHERE id = ? AND status = 'started'
                    """
                ),
                (
                    "failed" if error else "succeeded",
                    category,
                    confidence,
                    reasoning,
                    error,
                    _timestamp(),
                    attempt_id,
                ),
            )
            conn.commit()
        return cursor.rowcount == 1

    def list(
        self, submission_id: str, *, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        limit = min(max(int(limit), 1), 100)
        offset = max(int(offset), 0)
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql(
                    "SELECT * FROM classification_attempts "
                    "WHERE submission_id = ? "
                    "ORDER BY attempt_number DESC LIMIT ? OFFSET ?"
                ),
                (submission_id, limit, offset),
            ).fetchall()
        return [dict(row) for row in rows]


class EffectRepository:
    def __init__(self, database: Database) -> None:
        self.db = database

    def begin(
        self,
        *,
        effect_type: str,
        idempotency_key: str,
        request: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        effect_id, now = str(uuid.uuid4()), _timestamp()
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    INSERT INTO effect_executions (
                        id, effect_type, idempotency_key, status,
                        request_json, created_at
                    ) VALUES (?, ?, ?, 'started', ?, ?)
                    ON CONFLICT (effect_type, idempotency_key) DO NOTHING
                    """
                ),
                (
                    effect_id,
                    effect_type,
                    idempotency_key,
                    self.db.json_value(request or {}),
                    now,
                ),
            )
            created = cursor.rowcount == 1
            if not created:
                # A failed external effect is safe to retry under the same
                # idempotency key; completed or in-flight effects remain replayed.
                retried = conn.execute(
                    self.db.sql(
                        """
                        UPDATE effect_executions
                        SET status = 'started', request_json = ?,
                            result_json = NULL, error = NULL,
                            created_at = ?, completed_at = NULL
                        WHERE effect_type = ? AND idempotency_key = ?
                          AND status = 'failed'
                        """
                    ),
                    (
                        self.db.json_value(request or {}),
                        now,
                        effect_type,
                        idempotency_key,
                    ),
                )
                created = retried.rowcount == 1
            row = conn.execute(
                self.db.sql(
                    "SELECT * FROM effect_executions "
                    "WHERE effect_type = ? AND idempotency_key = ?"
                ),
                (effect_type, idempotency_key),
            ).fetchone()
            conn.commit()
        result = dict(row)
        result["request"] = _decode(result.pop("request_json"))
        if result.get("result_json") is not None:
            result["result"] = _decode(result["result_json"])
        return result, created

    def complete(
        self,
        effect_id: str,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> bool:
        with self.db.connect() as conn:
            cursor = conn.execute(
                self.db.sql(
                    """
                    UPDATE effect_executions
                    SET status = ?, result_json = ?, error = ?, completed_at = ?
                    WHERE id = ? AND status = 'started'
                    """
                ),
                (
                    "failed" if error else "completed",
                    self.db.json_value(result) if result is not None else None,
                    error,
                    _timestamp(),
                    effect_id,
                ),
            )
            conn.commit()
        return cursor.rowcount == 1


class ConfigRepository:
    """Key-value system configuration with audit trail."""

    # Known config keys — validated on write.
    KNOWN_KEYS = frozenset({
        "write_back_mode",
        "notify_owner_email",
        "followup_notify_email",
        "intake_new_project_owner_email",
        "intake_quote_request_owner_email",
        "intake_support_issue_owner_email",
        "intake_general_inquiry_owner_email",
        "intake_unclassified_owner_email",
        "approval_confidence_threshold",
        "approval_rules",
        "intake_check_existing_records",
    })

    def __init__(self, database: Database) -> None:
        self.db = database

    def get(self, key: str) -> str | None:
        with self.db.connect() as conn:
            row = conn.execute(
                self.db.sql("SELECT value FROM system_config WHERE key = ?"),
                (key,),
            ).fetchone()
        return dict(row)["value"] if row else None

    def get_all(self) -> dict[str, str]:
        with self.db.connect() as conn:
            rows = conn.execute(
                self.db.sql("SELECT key, value FROM system_config ORDER BY key"),
            ).fetchall()
        return {dict(r)["key"]: dict(r)["value"] for r in rows}

    def set(self, key: str, value: str, *, changed_by: str) -> str:
        if key not in self.KNOWN_KEYS:
            raise ValueError(f"unknown config key: {key}")
        now = _timestamp()
        old_value = self.get(key)
        with self.db.connect() as conn:
            conn.execute(
                self.db.sql(
                    """
                    INSERT INTO system_config (key, value, updated_at, updated_by)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT (key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at,
                        updated_by = excluded.updated_by
                    """
                ),
                (key, value.strip(), now, changed_by),
            )
            conn.execute(
                self.db.sql(
                    """
                    INSERT INTO config_audit_log
                        (id, config_key, old_value, new_value, changed_by, changed_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """
                ),
                (str(uuid.uuid4()), key, old_value, value.strip(), changed_by, now),
            )
            conn.commit()
        return value.strip()

    def audit_log(self, key: str | None = None, *, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            if key:
                rows = conn.execute(
                    self.db.sql(
                        "SELECT * FROM config_audit_log WHERE config_key = ? "
                        "ORDER BY changed_at DESC LIMIT ?"
                    ),
                    (key, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    self.db.sql(
                        "SELECT * FROM config_audit_log "
                        "ORDER BY changed_at DESC LIMIT ?"
                    ),
                    (limit,),
                ).fetchall()
        return [dict(r) for r in rows]


class Persistence:
    """Convenient aggregate exposing all Intake repositories."""

    def __init__(self, database: Database | None = None, *, migrate: bool = True) -> None:
        self.database = database or Database()
        if migrate:
            self.database.migrate()
        self.intake = IntakeRepository(self.database)
        self.jobs = JobRepository(self.database)
        self.webhooks = WebhookDeliveryRepository(self.database)
        self.operators = OperatorRepository(self.database)
        self.classifications = ClassificationAttemptRepository(self.database)
        self.effects = EffectRepository(self.database)
        self.config = ConfigRepository(self.database)
