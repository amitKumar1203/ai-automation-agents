"""Central Supervisor escalation path for stuck / failed / overdue items."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable

from persistence.repositories import Job
from supervisor.write_back import (
    get_notify_owner_email,
    get_write_back_mode,
    is_live_write_back,
)

SendEmailFn = Callable[..., dict[str, Any]]


def _detail(payload: dict[str, Any]) -> str:
    return json.dumps(payload, default=str)


def build_escalation_payload(
    *,
    reason: str,
    agent_name: str | None = None,
    task_id: str | None = None,
    entry_id: str | None = None,
    job_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Structured escalation marker stored on audit / notify payloads."""
    payload: dict[str, Any] = {
        "escalation": True,
        "reason": reason,
        "escalated_at": datetime.now(timezone.utc).isoformat(),
        "agent_name": agent_name,
        "task_id": task_id,
        "entry_id": entry_id,
        "job_id": job_id,
    }
    if extra:
        payload["extra"] = extra
    return payload


def merge_escalation_marker(
    execution_detail: dict[str, Any] | str | None,
    *,
    reason: str,
    agent_name: str | None = None,
    task_id: str | None = None,
    entry_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach a Supervisor escalation marker onto an executor detail payload."""
    if isinstance(execution_detail, str):
        try:
            base = json.loads(execution_detail)
        except (ValueError, TypeError):
            base = {"raw": execution_detail}
    elif isinstance(execution_detail, dict):
        base = dict(execution_detail)
    else:
        base = {}
    base["escalation"] = build_escalation_payload(
        reason=reason,
        agent_name=agent_name,
        task_id=task_id,
        entry_id=entry_id,
        extra=extra,
    )
    return base


def notify_escalation(
    payload: dict[str, Any],
    *,
    send_email: SendEmailFn | None = None,
) -> dict[str, Any]:
    """Notify the configured owner about a Supervisor escalation."""
    owner = get_notify_owner_email()
    mode = get_write_back_mode()
    planned = {
        "action": "SUPERVISOR_ESCALATION",
        "notify_owner": owner,
        "mode": mode,
        **payload,
    }
    if not owner:
        return {
            "execution_status": "SKIPPED",
            "execution_detail": "NOTIFY_OWNER_EMAIL not configured",
            "planned": planned,
        }
    if not is_live_write_back():
        return {
            "execution_status": "DRY_RUN",
            "execution_detail": _detail(planned),
        }

    email_fn = send_email or _default_send_email
    reason = str(payload.get("reason") or "escalation")
    agent = payload.get("agent_name") or "—"
    task = payload.get("task_id") or payload.get("job_id") or "—"
    subject = f"[Escalation] {reason} — {agent}"
    body_text = (
        f"Supervisor escalation\n\n"
        f"Reason: {reason}\n"
        f"Agent: {agent}\n"
        f"Task/Job: {task}\n"
        f"Entry: {payload.get('entry_id') or '—'}\n"
        f"Time: {payload.get('escalated_at')}\n"
    )
    effect = email_fn(
        to=owner,
        subject=subject,
        body_text=body_text,
        body_html=f"<pre>{body_text}</pre>",
    )
    return {
        "execution_status": "SUCCESS",
        "execution_detail": _detail({"planned": planned, "effects": {"email": effect}}),
    }


def escalate_dead_job(job: Job) -> dict[str, Any]:
    """Escalate when a Supervisor queue job exhausts retries."""
    payload = build_escalation_payload(
        reason="job_dead",
        agent_name=(job.payload or {}).get("agent_name"),
        task_id=(job.payload or {}).get("entry_id"),
        job_id=job.id,
        extra={
            "queue": job.queue,
            "job_type": job.job_type,
            "last_error": job.last_error,
            "attempts": job.attempts,
        },
    )
    return notify_escalation(payload)


def escalate_stale_pending(
    *,
    older_than_hours: float | None = None,
) -> dict[str, Any]:
    """Escalate audit entries pending approval longer than the threshold."""
    from supervisor.audit_log import get_audit_log

    hours = older_than_hours
    if hours is None:
        raw = (os.getenv("SUPERVISOR_STALE_PENDING_HOURS") or "48").strip()
        try:
            hours = float(raw)
        except ValueError:
            hours = 48.0

    now = datetime.now(timezone.utc)
    pending = get_audit_log(pending_review_only=True, dedupe_by_task=True)
    escalated: list[dict[str, Any]] = []
    for entry in pending:
        try:
            ts = datetime.fromisoformat(str(entry["timestamp"]).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        age_hours = (now - ts).total_seconds() / 3600.0
        if age_hours < hours:
            continue
        payload = build_escalation_payload(
            reason="stale_pending_approval",
            agent_name=entry.get("agent_name"),
            task_id=entry.get("task_id"),
            entry_id=entry.get("id"),
            extra={"age_hours": round(age_hours, 1), "threshold_hours": hours},
        )
        notify_escalation(payload)
        escalated.append(
            {
                "entry_id": entry.get("id"),
                "agent_name": entry.get("agent_name"),
                "task_id": entry.get("task_id"),
                "age_hours": round(age_hours, 1),
            }
        )
    return {
        "ok": True,
        "threshold_hours": hours,
        "escalated_count": len(escalated),
        "escalated": escalated,
    }


def _default_send_email(
    *,
    to: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> dict[str, Any]:
    from integrations.gmail_client import get_gmail_service, send_email

    return send_email(
        get_gmail_service(),
        to=to,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
    )
