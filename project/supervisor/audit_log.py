"""Persistent audit log for supervisor executions.

Production uses PostgreSQL when ``DATABASE_URL`` is configured. Local
development and tests retain the lightweight SQLite backend.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.agent_result import AgentResult
from supervisor.write_back import get_write_back_mode

# Default local path; tests may override via ``configure_database``.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "audit_log.db"
_db_path: str = str(_DEFAULT_DB_PATH)
_use_uri: bool = False
_database_url: str = (os.getenv("DATABASE_URL") or "").strip()
_backend: str = "postgres" if _database_url else "sqlite"


def configure_database(path: str, *, uri: bool = False) -> None:
    """Force a SQLite database path (used by local development and tests).

    Args:
        path: Filesystem path or SQLite URI for the database file.
        uri: When True, treat ``path`` as a SQLite URI (e.g. shared memory).
    """
    global _backend, _database_url, _db_path, _use_uri
    _backend = "sqlite"
    _database_url = ""
    _db_path = path
    _use_uri = uri
    if not uri and path not in {":memory:"}:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    init_db()


def configure_postgres(database_url: str) -> None:
    """Switch to PostgreSQL (primarily useful for integration tests)."""
    global _backend, _database_url
    if not database_url.strip():
        raise ValueError("database_url must not be empty")
    _backend = "postgres"
    _database_url = database_url.strip()
    init_db()


def _connect() -> Any:
    """Open a short-lived PostgreSQL or SQLite connection."""
    if _backend == "postgres":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL is set but psycopg is not installed"
            ) from exc
        return psycopg.connect(_database_url, row_factory=dict_row)

    if not _use_uri and _db_path not in {":memory:"}:
        Path(_db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_db_path, uri=_use_uri)
    conn.row_factory = sqlite3.Row
    return conn


def _sql(query: str) -> str:
    """Translate SQLite qmark placeholders to psycopg placeholders."""
    return query.replace("?", "%s") if _backend == "postgres" else query


def _table_columns(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("PRAGMA table_info(audit_entries)").fetchall()
    return {str(row["name"]) for row in rows}


def init_db() -> None:
    """Create the audit_entries table and migrate new columns if needed."""
    with _connect() as conn:
        if _backend == "postgres":
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_entries (
                    id TEXT PRIMARY KEY,
                    agent_name TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    result_data TEXT NOT NULL,
                    confidence DOUBLE PRECISION NOT NULL,
                    reasoning TEXT NOT NULL,
                    final_approval_needed BOOLEAN NOT NULL,
                    approval_status TEXT NOT NULL DEFAULT 'PENDING',
                    approved_by TEXT,
                    approved_at TEXT,
                    execution_status TEXT,
                    execution_detail TEXT,
                    input_json TEXT
                )
                """
            )
            conn.execute(
                "ALTER TABLE audit_entries "
                "ADD COLUMN IF NOT EXISTS execution_status TEXT"
            )
            conn.execute(
                "ALTER TABLE audit_entries "
                "ADD COLUMN IF NOT EXISTS execution_detail TEXT"
            )
            conn.execute(
                "ALTER TABLE audit_entries "
                "ADD COLUMN IF NOT EXISTS input_json TEXT"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_timestamp "
                "ON audit_entries (timestamp DESC)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_audit_pending "
                "ON audit_entries (approval_status, final_approval_needed)"
            )
            conn.commit()
            return

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_entries (
                id TEXT PRIMARY KEY,
                agent_name TEXT NOT NULL,
                task_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                result_data TEXT NOT NULL,
                confidence REAL NOT NULL,
                reasoning TEXT NOT NULL,
                final_approval_needed INTEGER NOT NULL,
                approval_status TEXT NOT NULL DEFAULT 'PENDING',
                approved_by TEXT,
                approved_at TEXT,
                execution_status TEXT,
                execution_detail TEXT,
                input_json TEXT
            )
            """
        )
        columns = _table_columns(conn)
        if "execution_status" not in columns:
            conn.execute(
                "ALTER TABLE audit_entries ADD COLUMN execution_status TEXT"
            )
        if "execution_detail" not in columns:
            conn.execute(
                "ALTER TABLE audit_entries ADD COLUMN execution_detail TEXT"
            )
        if "input_json" not in columns:
            conn.execute(
                "ALTER TABLE audit_entries ADD COLUMN input_json TEXT"
            )
        conn.commit()


_SELECT_COLUMNS = """
    id, agent_name, task_id, timestamp, result_data,
    confidence, reasoning, final_approval_needed,
    approval_status, approved_by, approved_at,
    execution_status, execution_detail, input_json
"""


def _dedupe_latest_by_task(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the newest entry per (agent_name, task_id)."""
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for entry in entries:
        key = (entry["agent_name"], entry["task_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _supersede_stale_pending(
    conn: Any,
    *,
    agent_name: str,
    task_id: str,
    exclude_id: str,
) -> None:
    """Reject older pending approvals when the same task is run again."""
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        _sql(
            """
            UPDATE audit_entries
            SET approval_status = 'REJECTED',
                approved_by = 'superseded-by-rerun',
                approved_at = ?
            WHERE agent_name = ?
              AND task_id = ?
              AND approval_status = 'PENDING'
              AND final_approval_needed = ?
              AND id != ?
            """
        ),
        (
            now,
            agent_name,
            task_id,
            True if _backend == "postgres" else 1,
            exclude_id,
        ),
    )


def _list_audit_entries(
    *,
    approval_status: str | None = None,
    pending_review_only: bool = False,
    dedupe_by_task: bool = False,
    limit: int | None = None,
    offset: int = 0,
    prioritize_pending: bool = False,
) -> list[dict[str, Any]]:
    """Load audit entries with optional filters (newest first)."""
    if offset < 0:
        raise ValueError("offset must be >= 0")
    if limit is not None and limit < 1:
        raise ValueError("limit must be >= 1")

    where_parts: list[str] = []
    params: list[Any] = []
    if approval_status:
        where_parts.append("approval_status = ?")
        params.append(approval_status)
    if pending_review_only:
        where_parts.append("final_approval_needed = ?")
        params.append(True if _backend == "postgres" else 1)
        where_parts.append("approval_status = 'PENDING'")

    where_sql = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
    order_suffix = "id DESC" if _backend == "postgres" else "rowid DESC"
    if prioritize_pending and not where_parts:
        order_by = (
            "CASE WHEN approval_status = 'PENDING' "
            "AND final_approval_needed THEN 0 ELSE 1 END ASC, "
            f"timestamp DESC, {order_suffix}"
        )
    else:
        order_by = f"timestamp DESC, {order_suffix}"

    with _connect() as conn:
        rows = conn.execute(
            _sql(
                f"""
                SELECT {_SELECT_COLUMNS}
                FROM audit_entries
                {where_sql}
                ORDER BY {order_by}
                """
            ),
            tuple(params),
        ).fetchall()

    entries = [_row_to_entry(row) for row in rows]
    if dedupe_by_task:
        entries = _dedupe_latest_by_task(entries)
    if limit is not None:
        return entries[offset : offset + limit]
    return entries[offset:]


def log_execution(
    agent_name: str,
    task_id: str,
    result: AgentResult,
    final_approval_needed: bool,
    input_data: dict[str, Any] | None = None,
) -> str:
    """Persist an execution record and return its unique entry id.

    Args:
        agent_name: Registered agent that produced the result.
        task_id: Caller-supplied task identifier.
        result: Agent output to store.
        final_approval_needed: Supervisor's final approval decision.
        input_data: Optional JSON-serialisable task input snapshot.

    Returns:
        Newly created audit entry UUID string.
    """
    entry_id = str(uuid.uuid4())
    timestamp = datetime.now(timezone.utc).isoformat()
    input_json = (
        json.dumps(input_data, default=str) if input_data is not None else None
    )

    with _connect() as conn:
        _supersede_stale_pending(
            conn,
            agent_name=agent_name,
            task_id=task_id,
            exclude_id=entry_id,
        )
        conn.execute(
            _sql(
                """
            INSERT INTO audit_entries (
                id, agent_name, task_id, timestamp, result_data,
                confidence, reasoning, final_approval_needed,
                approval_status, approved_by, approved_at,
                execution_status, execution_detail, input_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', NULL, NULL, NULL, NULL, ?)
                """
            ),
            (
                entry_id,
                agent_name,
                task_id,
                timestamp,
                json.dumps(result.data),
                float(result.confidence),
                result.reasoning,
                final_approval_needed if _backend == "postgres"
                else (1 if final_approval_needed else 0),
                input_json,
            ),
        )
        conn.commit()

    return entry_id


def _row_to_entry(row: Any) -> dict[str, Any]:
    """Convert a database row into the public audit entry dict shape."""
    keys = set(row.keys())
    input_payload = None
    if "input_json" in keys and row["input_json"]:
        try:
            input_payload = json.loads(row["input_json"])
        except (ValueError, TypeError):
            input_payload = {"raw": row["input_json"]}
    return {
        "id": row["id"],
        "agent_name": row["agent_name"],
        "task_id": row["task_id"],
        "timestamp": row["timestamp"],
        "input": input_payload,
        "result": {
            "data": json.loads(row["result_data"]),
            "confidence": float(row["confidence"]),
            "reasoning": row["reasoning"],
        },
        "final_approval_needed": bool(row["final_approval_needed"]),
        "approval_status": row["approval_status"],
        "approved_by": row["approved_by"],
        "approved_at": row["approved_at"],
        "execution_status": row["execution_status"] if "execution_status" in keys else None,
        "execution_detail": row["execution_detail"] if "execution_detail" in keys else None,
    }


def get_audit_entry(entry_id: str) -> dict[str, Any] | None:
    """Return a single audit entry by id, or None if not found."""
    with _connect() as conn:
        row = conn.execute(
            _sql(
                f"""
            SELECT {_SELECT_COLUMNS}
            FROM audit_entries
            WHERE id = ?
                """
            ),
            (entry_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_entry(row)


def count_audit_log(
    *,
    approval_status: str | None = None,
    pending_review_only: bool = False,
    dedupe_by_task: bool = False,
) -> int:
    """Return the number of audit entries matching optional filters."""
    return len(
        _list_audit_entries(
            approval_status=approval_status,
            pending_review_only=pending_review_only,
            dedupe_by_task=dedupe_by_task,
        )
    )


def get_audit_log_counts() -> dict[str, int]:
    """Summary counts for audit log tabs."""
    return {
        "pending_review": count_audit_log(pending_review_only=True, dedupe_by_task=True),
        "approved": count_audit_log(approval_status="APPROVED"),
        "rejected": count_audit_log(approval_status="REJECTED"),
        "all": count_audit_log(),
    }


def get_audit_log(
    *,
    limit: int | None = None,
    offset: int = 0,
    prioritize_pending: bool = False,
    approval_status: str | None = None,
    pending_review_only: bool = False,
    dedupe_by_task: bool = False,
) -> list[dict[str, Any]]:
    """Return audit entries, most recent first.

    When ``prioritize_pending`` is True, entries that still need
    approve/reject (PENDING + final_approval_needed) come first, then the
    rest — both groups newest-first. Ignored when an explicit filter is set.

    When ``limit`` is set, returns one page starting at ``offset``.
    """
    return _list_audit_entries(
        approval_status=approval_status,
        pending_review_only=pending_review_only,
        dedupe_by_task=dedupe_by_task,
        limit=limit,
        offset=offset,
        prioritize_pending=prioritize_pending,
    )


def get_dashboard_overview() -> dict[str, Any]:
    """Aggregate pending approvals and recent activity for the overview page."""
    from backend.services.kpi_cache import get_all_kpi_snapshots

    entries = get_audit_log()
    pending = [
        e
        for e in entries
        if e["final_approval_needed"] and e["approval_status"] == "PENDING"
    ]
    by_agent: dict[str, int] = {}
    for entry in pending:
        name = entry["agent_name"]
        by_agent[name] = by_agent.get(name, 0) + 1

    last_by_agent: dict[str, str] = {}
    for entry in entries:
        name = entry["agent_name"]
        if name not in last_by_agent:
            last_by_agent[name] = entry["timestamp"]

    failed = [
        e for e in entries if e.get("execution_status") == "FAILED"
    ][:10]

    escalations = [
        e
        for e in entries
        if _entry_has_escalation(e)
    ][:15]

    queue_summary: dict[str, Any] = {"totals": {}, "by_queue": {}}
    try:
        from backend.services.agent_job_worker import queue_depth_summary

        queue_summary = queue_depth_summary()
    except Exception:
        pass

    return {
        "pending_approval_count": len(pending),
        "pending_by_agent": by_agent,
        "last_run_by_agent": last_by_agent,
        "recent_entries": entries[:15],
        "recent_failures": failed,
        "open_escalations": escalations,
        "queue": queue_summary,
        "write_back_mode": get_write_back_mode(),
        "kpis": get_all_kpi_snapshots(),
    }


def _entry_has_escalation(entry: dict[str, Any]) -> bool:
    detail = entry.get("execution_detail")
    if not detail:
        data = (entry.get("result") or {}).get("data") or {}
        return str(data.get("status") or "") == "ESCALATE" and entry.get(
            "approval_status"
        ) == "PENDING"
    if isinstance(detail, str):
        return '"escalation": true' in detail or '"escalation":true' in detail
    return False


def get_task_status(task_id: str) -> dict[str, Any]:
    """End-to-end status for a task/project id across audit + queue jobs."""
    entries = [
        e for e in get_audit_log() if e.get("task_id") == task_id
    ]
    related_jobs: list[dict[str, Any]] = []
    try:
        from backend.services.agent_job_worker import list_supervisor_jobs

        for job in list_supervisor_jobs(limit=100):
            payload = job.get("payload") or {}
            if (
                payload.get("entry_id") in {e["id"] for e in entries}
                or job.get("entry_id") in {e["id"] for e in entries}
            ):
                related_jobs.append(job)
    except Exception:
        pass

    latest = entries[0] if entries else None
    return {
        "task_id": task_id,
        "found": bool(entries),
        "latest": latest,
        "audit_entries": entries[:25],
        "jobs": related_jobs,
        "has_escalation": any(_entry_has_escalation(e) for e in entries),
        "pending_approval": bool(
            latest
            and latest.get("final_approval_needed")
            and latest.get("approval_status") == "PENDING"
        ),
        "execution_status": (latest or {}).get("execution_status"),
        "approval_status": (latest or {}).get("approval_status"),
    }


def update_approval_status(
    entry_id: str,
    new_status: str,
    approved_by: str,
) -> dict[str, Any] | None:
    """Update a PENDING audit entry to APPROVED or REJECTED.

    Args:
        entry_id: UUID of the audit entry.
        new_status: Must be ``APPROVED`` or ``REJECTED``.
        approved_by: Free-text identifier of the decision maker.

    Returns:
        Updated entry dict on success, or ``None`` if the entry does not exist
        or is no longer in ``PENDING`` state.

    Raises:
        ValueError: If ``new_status`` is not APPROVED or REJECTED.
    """
    allowed = {"APPROVED", "REJECTED"}
    if new_status not in allowed:
        raise ValueError(
            f"Invalid approval status '{new_status}'. Must be one of: {sorted(allowed)}"
        )

    approved_at = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        cursor = conn.execute(
            _sql(
                """
            UPDATE audit_entries
            SET approval_status = ?, approved_by = ?, approved_at = ?
            WHERE id = ? AND approval_status = 'PENDING'
                """
            ),
            (new_status, approved_by, approved_at, entry_id),
        )
        conn.commit()
        if cursor.rowcount != 1:
            return None

        row = conn.execute(
            _sql(
                f"""
            SELECT {_SELECT_COLUMNS}
            FROM audit_entries
            WHERE id = ?
                """
            ),
            (entry_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_entry(row)


def update_execution_outcome(
    entry_id: str,
    execution_status: str,
    execution_detail: str | dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Persist post-approval execution outcome on an audit entry."""
    if isinstance(execution_detail, dict):
        detail_text = json.dumps(execution_detail, default=str)
    else:
        detail_text = execution_detail

    with _connect() as conn:
        cursor = conn.execute(
            _sql(
                """
            UPDATE audit_entries
            SET execution_status = ?, execution_detail = ?
            WHERE id = ?
                """
            ),
            (execution_status, detail_text, entry_id),
        )
        conn.commit()
        if cursor.rowcount != 1:
            return None

        row = conn.execute(
            _sql(
                f"""
            SELECT {_SELECT_COLUMNS}
            FROM audit_entries
            WHERE id = ?
                """
            ),
            (entry_id,),
        ).fetchone()

    if row is None:
        return None
    return _row_to_entry(row)


def clear_audit_log() -> None:
    """Delete all audit rows. Intended for test cleanup (keeps table structure)."""
    with _connect() as conn:
        conn.execute("DELETE FROM audit_entries")
        conn.commit()


# Ensure the production database and table exist on import.
init_db()
