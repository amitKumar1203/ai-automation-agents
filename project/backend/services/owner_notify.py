"""Autonomous owner notifications for unanswered client emails."""

from __future__ import annotations

import json
from typing import Any

from supervisor.write_back import get_notify_owner_email, get_write_back_mode, is_live_write_back


def notify_unanswered_threads(unanswered: list[dict[str, Any]]) -> dict[str, Any]:
    """Notify the configured owner about unanswered threads (never replies to clients).

    In dry-run mode, returns a planned payload only. In live mode, sends one
    digest email to ``NOTIFY_OWNER_EMAIL``.
    """
    owner = get_notify_owner_email()
    mode = get_write_back_mode()
    planned = {
        "action": "UNANSWERED_OWNER_DIGEST",
        "count": len(unanswered),
        "thread_ids": [row.get("thread_id") for row in unanswered],
        "notify_owner": owner,
        "mode": mode,
    }

    if not unanswered:
        return {"execution_status": "SKIPPED", "execution_detail": "No unanswered threads"}

    if not owner:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": "NOTIFY_OWNER_EMAIL not configured",
            "planned": planned,
        }

    if not is_live_write_back():
        return {
            "execution_status": "DRY_RUN",
            "execution_detail": json.dumps(planned, default=str),
        }

    from integrations.email_templates import build_email_unanswered_digest
    from integrations.gmail_client import get_gmail_service, send_email

    subject, body_text, body_html = build_email_unanswered_digest(threads=unanswered)
    effect = send_email(
        get_gmail_service(),
        to=owner,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
    return {
        "execution_status": "SUCCESS",
        "execution_detail": json.dumps(
            {"planned": planned, "effects": {"email": effect}},
            default=str,
        ),
    }
