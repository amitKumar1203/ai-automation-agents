"""Supervisor monitoring, queue, and end-to-end task status routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_roles
from backend.services.agent_job_worker import (
    drain_agent_jobs,
    enqueue_event,
    list_supervisor_jobs,
    queue_depth_summary,
)
from persistence import Persistence
from supervisor.audit_log import get_dashboard_overview, get_task_status
from supervisor.escalation import escalate_stale_pending
from supervisor.router import known_event_sources, route_event

router = APIRouter()
_reviewer = require_roles("reviewer", "admin")


@router.get("/status")
def supervisor_live_status() -> dict:
    """Live status of agents, workflows, queue depth, and escalations."""
    overview = get_dashboard_overview()
    return {
        "ok": True,
        "pending_approval_count": overview["pending_approval_count"],
        "pending_by_agent": overview["pending_by_agent"],
        "last_run_by_agent": overview["last_run_by_agent"],
        "recent_failures": overview.get("recent_failures") or [],
        "open_escalations": overview.get("open_escalations") or [],
        "queue": overview.get("queue") or queue_depth_summary(),
        "write_back_mode": overview["write_back_mode"],
        "kpis": overview.get("kpis") or {},
        "event_sources": list(known_event_sources()),
    }


@router.get("/tasks/{task_id}")
def supervisor_task_status(task_id: str) -> dict:
    """End-to-end status for a task/project id."""
    return get_task_status(task_id)


@router.get("/jobs")
def list_jobs(
    status: str | None = Query(default=None, pattern="^(pending|running|succeeded|dead)$"),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict:
    """List Supervisor queue jobs (agent_poll + writeback_retry)."""
    jobs = list_supervisor_jobs(status=status, limit=limit)
    return {"ok": True, "total": len(jobs), "jobs": jobs}


@router.post("/jobs/{job_id}/retry", dependencies=[Depends(_reviewer)])
def retry_dead_job(job_id: str) -> dict:
    """Requeue a dead-lettered Supervisor job (reviewer/admin)."""
    store = Persistence()
    job = store.jobs.retry_dead(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Dead job not found")
    return {
        "ok": True,
        "job": {
            "id": job.id,
            "queue": job.queue,
            "job_type": job.job_type,
            "status": job.status,
        },
    }


@router.post("/route/{event_source}")
def route_and_enqueue(event_source: str) -> dict:
    """Evaluate an event, enqueue agent poll jobs, and optionally drain."""
    try:
        routed = route_event(event_source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    enqueued = enqueue_event(event_source, trigger="api")
    return {
        "ok": True,
        "routed": [
            {"job_type": t.job_type, "agent_name": t.agent_name} for t in routed
        ],
        "enqueue": enqueued,
    }


@router.post("/drain")
def drain_jobs(limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """Drain a bounded Supervisor job batch (also used by cron)."""
    return drain_agent_jobs(limit=limit)


@router.post("/escalate-stale", dependencies=[Depends(_reviewer)])
def escalate_stale(
    older_than_hours: float | None = Query(default=None, ge=1),
) -> dict:
    """Escalate audit items pending approval longer than the threshold."""
    return escalate_stale_pending(older_than_hours=older_than_hours)
