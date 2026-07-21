"""Database configuration and lightweight migration runner for Intake storage."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_MIGRATIONS = Path(__file__).resolve().parent / "migrations"


class Database:
    """PostgreSQL-first database handle with a SQLite local/test fallback."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        sqlite_path: str | Path | None = None,
        sqlite_uri: bool = False,
    ) -> None:
        url = (database_url if database_url is not None else os.getenv("DATABASE_URL", "")).strip()
        self.backend = "postgres" if url else "sqlite"
        self.database_url = url
        self.sqlite_path = str(sqlite_path or (_PROJECT_ROOT / "data" / "audit_log.db"))
        self.sqlite_uri = sqlite_uri

    @classmethod
    def from_audit_log(cls) -> "Database":
        """Use the currently configured audit database, including pytest overrides."""
        from supervisor import audit_log

        if getattr(audit_log, "_backend", "sqlite") == "postgres":
            return cls(str(getattr(audit_log, "_database_url")))
        return cls(
            "",
            sqlite_path=str(getattr(audit_log, "_db_path")),
            sqlite_uri=bool(getattr(audit_log, "_use_uri", False)),
        )

    def sql(self, query: str) -> str:
        return query.replace("?", "%s") if self.backend == "postgres" else query

    def json_value(self, value: Any) -> Any:
        if self.backend == "postgres":
            from psycopg.types.json import Jsonb

            return Jsonb(value)
        import json

        return json.dumps(value, separators=(",", ":"), default=str)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        if self.backend == "postgres":
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:
                raise RuntimeError(
                    "PostgreSQL persistence requires psycopg[binary]"
                ) from exc
            conn = psycopg.connect(self.database_url, row_factory=dict_row)
        else:
            if not self.sqlite_uri and self.sqlite_path != ":memory:":
                Path(self.sqlite_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(
                self.sqlite_path,
                uri=self.sqlite_uri,
                timeout=30,
                isolation_level=None,
            )
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 30000")
            if self.sqlite_path != ":memory:":
                conn.execute("PRAGMA journal_mode = WAL")
        try:
            yield conn
        finally:
            conn.close()

    def migrate(self) -> None:
        """Apply each versioned SQL migration exactly once."""
        dialect = self.backend
        migration_dir = _MIGRATIONS / dialect
        with self.connect() as conn:
            if dialect == "sqlite":
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS intake_schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                applied = {
                    str(row["version"])
                    for row in conn.execute(
                        "SELECT version FROM intake_schema_migrations"
                    ).fetchall()
                }
                for path in sorted(migration_dir.glob("*.sql")):
                    if path.name in applied:
                        continue
                    # SQLite executescript controls its own transaction. Including
                    # the version row in that script keeps each migration atomic.
                    version = path.name.replace("'", "''")
                    applied_at = _utc_now().replace("'", "''")
                    script = path.read_text(encoding="utf-8")
                    conn.executescript(
                        "BEGIN IMMEDIATE;\n"
                        + script
                        + "\nINSERT INTO intake_schema_migrations "
                        + "(version, applied_at) "
                        + f"VALUES ('{version}', '{applied_at}');\nCOMMIT;"
                    )
                return

            conn.execute("BEGIN")
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS intake_schema_migrations (
                        version TEXT PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    )
                    """
                )
                applied = {
                    str(row["version"])
                    for row in conn.execute(
                        "SELECT version FROM intake_schema_migrations"
                    ).fetchall()
                }
                for path in sorted(migration_dir.glob("*.sql")):
                    if path.name in applied:
                        continue
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute(
                        self.sql(
                            "INSERT INTO intake_schema_migrations "
                            "(version, applied_at) VALUES (?, ?)"
                        ),
                        (path.name, _utc_now()),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def migrate(database: Database | None = None) -> Database:
    """Migrate and return a configured database handle."""
    db = database or Database()
    db.migrate()
    return db
