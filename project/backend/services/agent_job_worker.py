"""Durable Supervisor agent poll + write-back retry worker.

Reuses Intake ``background_jobs`` (JobRepository) for Phase 1/2 agent polls
and failed post-approval write-back retries.
"""

from __future__ import annotations

import os
import random
import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from persistence import Persistence
from persistence.repositories import Job
from supervisor.router import RouteTarget, route_event

AGENT_POLL_QUEUE = "agent_poll"
WRITEBACK_RETRY_QUEUE = "writeback_retry"
WRITEBACK_RETRY_JOB = "retry_writeback"

_JOB_RUNNERS: dict[str, str] = {
    "poll_email": "email",
    "poll_vendor": "vendor",
    "poll_po": "po",
    "poll_followup": "followup",
    "poll_storefront": "storefront",
    "poll_installer": "installer",
}


def _int_env(name: str, default: int) -> int:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        return max(0.0, float(raw))
    except ValueError:
        return default


def _idempotency_hour_key(job_type: str, *, now: datetime | None = None) -> str:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d-%H")
    return f"{job_type}:{stamp}"


def enqueue_routes(
    targets: list[RouteTarget],
    *,
    store: Persistence | None = None,
    trigger: str = "cron",
    delivery_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Enqueue Supervisor poll jobs for routed targets."""
    persistence = store or Persistence()
    created: list[dict[str, Any]] = []
    reused: list[dict[str, Any]] = []
    for target in targets:
        key = (
            f"{target.job_type}:delivery:{delivery_id}"
            if delivery_id
            else _idempotency_hour_key(target.job_type, now=now)
        )
        job, was_created = persistence.jobs.enqueue(
            queue=AGENT_POLL_QUEUE,
            job_type=target.job_type,
            payload={
                "agent_name": target.agent_name,
                "event_source": target.event_source,
                "use_live": target.use_live,
                "trigger": trigger,
            },
            max_attempts=_int_env("AGENT_POLL_MAX_ATTEMPTS", 5),
            idempotency_key=key,
        )
        row = {
            "job_id": job.id,
            "job_type": job.job_type,
            "agent_name": target.agent_name,
            "created": was_created,
        }
        (created if was_created else reused).append(row)
    return {
        "ok": True,
        "enqueued": len(created),
        "reused": len(reused),
        "jobs": created + reused,
    }


def enqueue_event(
    event_source: str,
    *,
    store: Persistence | None = None,
    trigger: str = "webhook",
    delivery_id: str | None = None,
) -> dict[str, Any]:
    """Route an event source then enqueue agent poll jobs."""
    targets = route_event(event_source)
    result = enqueue_routes(
        targets,
        store=store,
        trigger=trigger,
        delivery_id=delivery_id,
    )
    result["event_source"] = event_source
    result["routed"] = [
        {"job_type": t.job_type, "agent_name": t.agent_name} for t in targets
    ]
    return result


def enqueue_writeback_retry(
    entry_id: str,
    *,
    store: Persistence | None = None,
    attempt_hint: int = 0,
) -> tuple[Job, bool]:
    """Enqueue automatic retry for a failed post-approval write-back."""
    persistence = store or Persistence()
    return persistence.jobs.enqueue(
        queue=WRITEBACK_RETRY_QUEUE,
        job_type=WRITEBACK_RETRY_JOB,
        payload={"entry_id": entry_id, "attempt_hint": attempt_hint},
        max_attempts=_int_env("WRITEBACK_RETRY_MAX_ATTEMPTS", 5),
        idempotency_key=f"writeback:{entry_id}:a{attempt_hint}",
    )


def _run_poll_job(job: Job) -> dict[str, Any]:
    """Execute the live batch runner for a poll job type."""
    from backend.services.agent_runs import (
        run_email_batch,
        run_followup_batch,
        run_installer_batch,
        run_po_batch,
        run_storefront_batch,
        run_vendor_batch,
    )

    use_live = bool((job.payload or {}).get("use_live", True))
    runners: dict[str, Callable[[], dict[str, Any]]] = {
        "poll_email": lambda: run_email_batch(
            use_real_gmail=use_live,
            notify_owner=False,
        ),
        "poll_vendor": lambda: run_vendor_batch(use_real_monday=use_live),
        "poll_po": lambda: run_po_batch(use_real_salesforce=use_live),
        "poll_followup": lambda: run_followup_batch(use_real_salesforce=use_live),
        "poll_storefront": lambda: run_storefront_batch(use_real_monday=use_live),
        "poll_installer": lambda: run_installer_batch(use_real_monday=use_live),
    }
    runner = runners.get(job.job_type)
    if runner is None:
        raise ValueError(f"Unsupported agent poll job_type '{job.job_type}'")
    summary = runner()
    if isinstance(summary, dict) and summary.get("error"):
        raise RuntimeError(str(summary["error"]))
    # Thin bulky results for job completion logging
    if isinstance(summary, dict) and "results" in summary:
        return {k: v for k, v in summary.items() if k != "results"}
    return summary if isinstance(summary, dict) else {"ok": True}


def _run_writeback_retry(job: Job) -> dict[str, Any]:
    from supervisor.action_executor import execute_approved_action
    from supervisor.audit_log import get_audit_entry, update_execution_outcome

    entry_id = str((job.payload or {}).get("entry_id") or "").strip()
    if not entry_id:
        raise ValueError("writeback_retry payload missing entry_id")
    entry = get_audit_entry(entry_id)
    if entry is None:
        raise ValueError(f"Audit entry '{entry_id}' not found")
    if entry.get("approval_status") != "APPROVED":
        return {
            "skipped": True,
            "reason": f"entry not APPROVED ({entry.get('approval_status')})",
        }
    if entry.get("execution_status") in {"SUCCESS", "DRY_RUN", "SKIPPED"}:
        return {
            "skipped": True,
            "reason": f"already {entry.get('execution_status')}",
        }
    outcome = execute_approved_action(entry)
    update_execution_outcome(
        entry_id,
        outcome["execution_status"],
        outcome.get("execution_detail"),
    )
    if outcome["execution_status"] == "FAILED":
        raise RuntimeError(
            str(outcome.get("execution_detail") or "write-back failed")
        )
    return outcome


def _process_job(job: Job, *, worker_id: str, store: Persistence) -> str:
    """Run one claimed job; return outcome label succeeded|retried|dead."""
    try:
        if job.queue == WRITEBACK_RETRY_QUEUE:
            _run_writeback_retry(job)
        else:
            _run_poll_job(job)
        store.jobs.complete(job.id, worker_id=worker_id)
        return "succeeded"
    except Exception as exc:  # noqa: BLE001 — persist failure + backoff
        base = _float_env("AGENT_JOB_RETRY_BASE_SECONDS", 30.0)
        cap = _float_env("AGENT_JOB_RETRY_MAX_SECONDS", 900.0)
        delay = min(cap, base * (2 ** max(0, job.attempts - 1)))
        delay *= 0.5 + random.random()
        updated = store.jobs.fail(
            job.id,
            worker_id=worker_id,
            error=str(exc),
            retry_delay_seconds=delay,
        )
        if updated is None:
            return "retried"
        if updated.status == "dead":
            # Escalation for dead jobs is best-effort.
            try:
                from supervisor.escalation import escalate_dead_job

                escalate_dead_job(updated)
            except Exception:
                pass
            return "dead"
        return "retried"


def drain_agent_jobs(
    *,
    limit: int = 10,
    store: Persistence | None = None,
    worker_id: str | None = None,
) -> dict[str, Any]:
    """Drain a bounded number of agent_poll + writeback_retry jobs."""
    persistence = store or Persistence()
    bounded = min(max(int(limit), 1), _int_env("AGENT_CRON_MAX_JOBS", 50))
    identity = worker_id or f"agent-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    counts = {"claimed": 0, "succeeded": 0, "retried": 0, "dead": 0}
    queues = (AGENT_POLL_QUEUE, WRITEBACK_RETRY_QUEUE)
    for index in range(bounded):
        job = None
        for queue in (queues[index % 2], queues[(index + 1) % 2]):
            job = persistence.jobs.claim(
                queue=queue,
                worker_id=identity,
                lease_seconds=_int_env("AGENT_JOB_LEASE_SECONDS", 120),
            )
            if job is not None:
                break
        if job is None:
            break
        counts["claimed"] += 1
        label = _process_job(job, worker_id=identity, store=persistence)
        counts[label] = counts.get(label, 0) + 1
    return {"ok": True, "worker_id": identity, **counts}


def list_supervisor_jobs(
    *,
    status: str | None = None,
    queue: str | None = None,
    limit: int = 50,
    store: Persistence | None = None,
) -> list[dict[str, Any]]:
    """List recent Supervisor queue jobs for dashboard / retry UI."""
    persistence = store or Persistence()
    jobs = persistence.jobs.list_jobs(
        queues=[AGENT_POLL_QUEUE, WRITEBACK_RETRY_QUEUE]
        if queue is None
        else [queue],
        status=status,
        limit=limit,
    )
    return [_job_to_dict(j) for j in jobs]


def queue_depth_summary(*, store: Persistence | None = None) -> dict[str, Any]:
    """Counts of pending/running/dead jobs for monitoring."""
    persistence = store or Persistence()
    return persistence.jobs.count_by_status(
        queues=[AGENT_POLL_QUEUE, WRITEBACK_RETRY_QUEUE]
    )


def _job_to_dict(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "queue": job.queue,
        "job_type": job.job_type,
        "payload": job.payload,
        "status": job.status,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "last_error": job.last_error,
        "available_at": str(job.available_at) if job.available_at else None,
        "dead_lettered_at": (
            str(job.dead_lettered_at) if job.dead_lettered_at else None
        ),
        "idempotency_key": job.idempotency_key,
        "agent_name": (job.payload or {}).get("agent_name"),
        "entry_id": (job.payload or {}).get("entry_id"),
    }
