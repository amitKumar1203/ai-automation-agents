"""Tests for Supervisor routing, queue, escalation, and audit input."""

from __future__ import annotations

import pytest

from models.agent_result import AgentResult
from models.task import VendorQuoteRequest
from persistence import Persistence
from persistence.database import Database
from supervisor.approval_policy import RISKY_STATUS_MAP, requires_human_approval
from supervisor.audit_log import configure_database, get_audit_entry, log_execution
from supervisor.escalation import build_escalation_payload, merge_escalation_marker
from supervisor.router import route_event, route_event_job_types
from supervisor.supervisor import Supervisor


@pytest.fixture()
def mem_audit(tmp_path, monkeypatch):
    db = tmp_path / "audit.db"
    configure_database(str(db))
    return db


@pytest.fixture()
def mem_jobs(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "")
    return Persistence(Database("", sqlite_path=tmp_path / "supervisor_jobs.db"))


def test_route_gmail_to_email_agent() -> None:
    targets = route_event("gmail")
    assert len(targets) == 1
    assert targets[0].agent_name == "email_reply_monitoring"
    assert targets[0].job_type == "poll_email"


def test_route_all_fanout_unique_jobs() -> None:
    jobs = route_event_job_types("all")
    assert "poll_email" in jobs
    assert "poll_vendor" in jobs
    assert "poll_po" in jobs
    assert len(jobs) == len(set(jobs))


def test_route_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown event source"):
        route_event("not-a-source")


def test_phase3_approval_stubs_reserved() -> None:
    assert "READY_FOR_EXTERNAL_SHARE" in RISKY_STATUS_MAP["ai_mockup"]
    assert "FAIL" in RISKY_STATUS_MAP["installation_qc"]


def test_enqueue_and_list_agent_poll_jobs(mem_jobs: Persistence) -> None:
    from backend.services.agent_job_worker import (
        AGENT_POLL_QUEUE,
        enqueue_event,
        list_supervisor_jobs,
        queue_depth_summary,
    )

    result = enqueue_event("gmail", store=mem_jobs, trigger="test", delivery_id="d1")
    assert result["enqueued"] == 1
    jobs = list_supervisor_jobs(store=mem_jobs, status="pending")
    assert any(j["job_type"] == "poll_email" for j in jobs)
    depth = queue_depth_summary(store=mem_jobs)
    assert depth["totals"]["pending"] >= 1
    assert AGENT_POLL_QUEUE in depth["by_queue"]


def test_log_execution_stores_input(mem_audit) -> None:
    result = AgentResult(
        data={"status": "OK", "project_id": "P1"},
        confidence=1.0,
        requires_approval=False,
        reasoning="ok",
    )
    entry_id = log_execution(
        "vendor_followup",
        "P1",
        result,
        False,
        input_data={"vendor_name": "Acme", "project_id": "P1"},
    )
    entry = get_audit_entry(entry_id)
    assert entry is not None
    assert entry["input"]["vendor_name"] == "Acme"
    assert entry["result"]["data"]["status"] == "OK"


def test_supervisor_execute_persists_input(mem_audit) -> None:
    from datetime import datetime, timezone

    task = VendorQuoteRequest(
        vendor_name="Acme",
        project_id="PRJ-IN",
        request_sent_at=datetime.now(timezone.utc),
        quote_received=True,
    )
    outcome = Supervisor().execute_task("vendor_followup", task, "PRJ-IN")
    entry = get_audit_entry(outcome["entry_id"])
    assert entry is not None
    assert entry["input"] is not None
    assert entry["input"]["project_id"] == "PRJ-IN"


def test_merge_escalation_marker() -> None:
    merged = merge_escalation_marker(
        {"planned": {"action": "ESCALATE"}},
        reason="agent_escalate",
        agent_name="vendor_followup",
        task_id="P1",
    )
    assert merged["escalation"]["escalation"] is True
    assert merged["escalation"]["reason"] == "agent_escalate"


def test_build_escalation_payload_shape() -> None:
    payload = build_escalation_payload(reason="job_dead", job_id="j1")
    assert payload["escalation"] is True
    assert payload["job_id"] == "j1"


def test_unanswered_requires_approval() -> None:
    result = AgentResult(
        data={"status": "UNANSWERED", "thread_id": "T1"},
        confidence=1.0,
        requires_approval=False,
        reasoning="late",
    )
    assert requires_human_approval("email_reply_monitoring", result) is True
