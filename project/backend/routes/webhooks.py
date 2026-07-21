"""Inbound webhooks for Make.com / external systems to trigger agent batches.

Automated triggers go through the Supervisor event router → durable queue.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import require_cron_secret
from backend.services.agent_job_worker import drain_agent_jobs, enqueue_event

router = APIRouter(dependencies=[Depends(require_cron_secret)])


def _enqueue_and_drain(event_source: str, *, drain: bool = True, limit: int = 10) -> dict:
    try:
        enqueued = enqueue_event(event_source, trigger="webhook")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    drained = drain_agent_jobs(limit=limit) if drain else None
    return {
        "ok": True,
        "event_source": event_source,
        "enqueue": enqueued,
        "drain": drained,
    }


@router.post("/gmail")
def webhook_gmail(drain: bool = Query(default=True)) -> dict:
    """Route Gmail event → email agent poll job."""
    return _enqueue_and_drain("gmail", drain=drain)


@router.post("/monday")
def webhook_monday(drain: bool = Query(default=True)) -> dict:
    """Route Monday event → vendor/storefront/installer poll jobs."""
    return _enqueue_and_drain("monday", drain=drain)


@router.post("/salesforce")
def webhook_salesforce(drain: bool = Query(default=True)) -> dict:
    """Route Salesforce event → PO + follow-up poll jobs."""
    return _enqueue_and_drain("salesforce", drain=drain)


@router.post("/followup")
def webhook_followup(drain: bool = Query(default=True)) -> dict:
    """Route follow-up event → automated follow-up poll job."""
    return _enqueue_and_drain("followup", drain=drain)


@router.post("/all")
def webhook_all(drain: bool = Query(default=True)) -> dict:
    """Route all event sources → fan-out agent poll jobs."""
    return _enqueue_and_drain("all", drain=drain, limit=20)
