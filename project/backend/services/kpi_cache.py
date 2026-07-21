"""Database helpers for caching last successful agent-run KPI summaries."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from supervisor import audit_log


def _connect() -> Any:
    """Reuse the audit DB connection settings."""
    return audit_log._connect()  # noqa: SLF001 — shared DB file


def init_kpi_table() -> None:
    """Create the kpi_snapshots table if needed."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS kpi_snapshots (
                agent_key TEXT PRIMARY KEY,
                updated_at TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.commit()


def save_kpi_snapshot(agent_key: str, payload: dict[str, Any]) -> None:
    """Upsert a KPI snapshot for an agent family."""
    init_kpi_table()
    stamp = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            audit_log._sql(  # noqa: SLF001 — shared database dialect
                """
            INSERT INTO kpi_snapshots (agent_key, updated_at, payload)
            VALUES (?, ?, ?)
            ON CONFLICT(agent_key) DO UPDATE SET
                updated_at = excluded.updated_at,
                payload = excluded.payload
                """
            ),
            (agent_key, stamp, json.dumps(payload, default=str)),
        )
        conn.commit()


def get_all_kpi_snapshots() -> dict[str, Any]:
    """Return all KPI snapshots keyed by agent_key with updated_at."""
    init_kpi_table()
    with _connect() as conn:
        rows = conn.execute(
            "SELECT agent_key, updated_at, payload FROM kpi_snapshots"
        ).fetchall()
    out: dict[str, Any] = {}
    for row in rows:
        out[str(row["agent_key"])] = {
            "updated_at": row["updated_at"],
            **json.loads(row["payload"]),
        }
    return out


init_kpi_table()
