"""Scheduled poll endpoints (Vercel Cron / external schedulers)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.auth import require_cron_secret
from backend.services.agent_job_worker import drain_agent_jobs, enqueue_event
from backend.services.intake_workflow import drain_intake_jobs
from supervisor.escalation import escalate_stale_pending

router = APIRouter(dependencies=[Depends(require_cron_secret)])


@router.get("/poll-all")
@router.post("/poll-all")
def poll_all(
    drain_limit: int = Query(default=20, ge=1, le=50),
    escalate_stale: bool = Query(default=True),
) -> dict:
    """Enqueue all agent polls via Supervisor router, then drain the queue."""
    enqueued = enqueue_event("all", trigger="cron")
    drained = drain_agent_jobs(limit=drain_limit)
    stale = escalate_stale_pending() if escalate_stale else None
    return {
        "ok": True,
        "enqueue": enqueued,
        "drain": drained,
        "stale_escalations": stale,
    }


@router.get("/agent-jobs")
@router.post("/agent-jobs")
def drain_agents(limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """Drain Supervisor agent_poll / writeback_retry jobs only."""
    return {"ok": True, "agents": drain_agent_jobs(limit=limit)}


@router.get("/intake")
@router.post("/intake")
def drain_intake(limit: int = Query(default=10, ge=1, le=50)) -> dict:
    """Drain a bounded Intake worker batch for one serverless invocation."""
    return {"ok": True, "intake": drain_intake_jobs(limit=limit)}
