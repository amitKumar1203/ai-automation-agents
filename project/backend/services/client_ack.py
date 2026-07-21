"""Template-based client acknowledgment for unanswered email threads (no AI)."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from supervisor.write_back import get_write_back_mode, is_live_write_back

SendEmailFn = Callable[..., dict[str, Any]]

_DEFAULT_SUBJECT_PREFIX = "Re: "
_DEFAULT_BODY = (
    "Hi,\n\n"
    "Thank you for your email. We have received your message and a member of "
    "our team will get back to you shortly.\n\n"
    "This is an automated acknowledgment.\n\n"
    "Best regards"
)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if os.getenv("VERCEL") or os.getenv("AUDIT_DB_DIR"):
    _DEFAULT_DB_PATH = Path(os.getenv("AUDIT_DB_DIR", "/tmp")) / "audit_log.db"
else:
    _DEFAULT_DB_PATH = _PROJECT_ROOT / "data" / "audit_log.db"


def is_client_auto_ack_enabled() -> bool:
    """Return whether unanswered threads may get a template client ack after approve.

    Default is off — client outbound email requires human approval (HITL).
    Set CLIENT_AUTO_ACK_ENABLED=true to allow post-approval client ack sends.
    """
    raw = (os.getenv("CLIENT_AUTO_ACK_ENABLED") or "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def get_ack_body() -> str:
    """Return the fixed acknowledgment body (optional env override, no AI)."""
    custom = (os.getenv("CLIENT_AUTO_ACK_BODY") or "").strip()
    return custom or _DEFAULT_BODY


def _connect() -> sqlite3.Connection:
    path = _DEFAULT_DB_PATH
    if path != Path(":memory:"):
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS client_ack_sent (
            thread_id TEXT PRIMARY KEY,
            client_email TEXT,
            sent_at TEXT NOT NULL,
            message_id TEXT
        )
        """
    )
    conn.commit()


def already_acked(thread_id: str) -> bool:
    """True if this thread already received a live client acknowledgment."""
    if not thread_id:
        return False
    with _connect() as conn:
        _ensure_table(conn)
        row = conn.execute(
            "SELECT 1 FROM client_ack_sent WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
    return row is not None


def mark_acked(thread_id: str, *, client_email: str, message_id: str | None) -> None:
    """Record a successful live ack so we do not send again for this thread."""
    with _connect() as conn:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT OR REPLACE INTO client_ack_sent
                (thread_id, client_email, sent_at, message_id)
            VALUES (?, ?, ?, ?)
            """,
            (
                thread_id,
                client_email,
                datetime.now(timezone.utc).isoformat(),
                message_id,
            ),
        )
        conn.commit()


def _ack_subject(subject: str | None) -> str:
    base = (subject or "").strip() or "your message"
    if base.lower().startswith("re:"):
        return base
    return f"{_DEFAULT_SUBJECT_PREFIX}{base}"


def send_client_acks(
    unanswered: list[dict[str, Any]],
    *,
    send_email: SendEmailFn | None = None,
) -> dict[str, Any]:
    """Send a template acknowledgment to each unanswered client (no AI).

    Skips threads that are already answered (caller should only pass UNANSWERED),
    already acked once, or missing a client email. Respects ``WRITE_BACK_MODE``.
    """
    if not is_client_auto_ack_enabled():
        return {
            "execution_status": "SKIPPED",
            "execution_detail": "CLIENT_AUTO_ACK_ENABLED is off",
        }

    if not unanswered:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": "No unanswered threads",
        }

    mode = get_write_back_mode()
    body = get_ack_body()
    outcomes: list[dict[str, Any]] = []

    for row in unanswered:
        thread_id = str(row.get("thread_id") or "")
        client_email = str(row.get("client_email") or "").strip()
        subject = _ack_subject(row.get("subject"))
        planned = {
            "action": "CLIENT_AUTO_ACK",
            "thread_id": thread_id,
            "to": client_email,
            "subject": subject,
            "mode": mode,
        }

        if not thread_id:
            outcomes.append(
                {
                    "execution_status": "SKIPPED",
                    "execution_detail": "Missing thread_id",
                    "planned": planned,
                }
            )
            continue

        if already_acked(thread_id):
            outcomes.append(
                {
                    "execution_status": "SKIPPED",
                    "execution_detail": "Already acknowledged for this thread",
                    "planned": planned,
                }
            )
            continue

        if not client_email:
            outcomes.append(
                {
                    "execution_status": "SKIPPED",
                    "execution_detail": "No client email on thread",
                    "planned": planned,
                }
            )
            continue

        if not is_live_write_back():
            outcomes.append(
                {
                    "execution_status": "DRY_RUN",
                    "execution_detail": json.dumps(planned, default=str),
                    "planned": planned,
                }
            )
            continue

        email_fn = send_email or _default_send_email
        try:
            from integrations.email_templates import build_client_ack_email

            ack_text, ack_html = build_client_ack_email(body_text=body)
            effect = email_fn(
                to=client_email,
                subject=subject,
                body_text=ack_text,
                body_html=ack_html,
                thread_id=thread_id,
            )
            mark_acked(
                thread_id,
                client_email=client_email,
                message_id=(effect or {}).get("id"),
            )
            outcomes.append(
                {
                    "execution_status": "SUCCESS",
                    "execution_detail": json.dumps(
                        {"planned": planned, "effects": {"email": effect}},
                        default=str,
                    ),
                    "planned": planned,
                }
            )
        except Exception as exc:  # noqa: BLE001 — per-thread failure must not abort batch
            outcomes.append(
                {
                    "execution_status": "FAILED",
                    "execution_detail": str(exc),
                    "planned": planned,
                }
            )

    statuses = {o["execution_status"] for o in outcomes}
    if statuses == {"SKIPPED"}:
        overall = "SKIPPED"
    elif "FAILED" in statuses and "SUCCESS" not in statuses and "DRY_RUN" not in statuses:
        overall = "FAILED"
    elif "SUCCESS" in statuses:
        overall = "SUCCESS"
    elif "DRY_RUN" in statuses:
        overall = "DRY_RUN"
    else:
        overall = "SKIPPED"

    return {
        "execution_status": overall,
        "count": len(outcomes),
        "results": outcomes,
    }


def _default_send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    thread_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from integrations.gmail_client import get_gmail_service, send_email as gmail_send

    return gmail_send(
        get_gmail_service(),
        to=to,
        subject=subject,
        body_text=body_text,
        thread_id=thread_id,
        **kwargs,
    )
