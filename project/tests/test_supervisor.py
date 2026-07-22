"""Tests for the Supervisor orchestration layer."""

from datetime import datetime, timedelta, timezone

import pytest

from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import EmailMessage, EmailThread, VendorQuoteRequest
from supervisor.agent_registry import get_agent, register_agent
from supervisor.approval_policy import requires_human_approval
from supervisor.audit_log import get_audit_log
from supervisor.supervisor import Supervisor


class _LowConfidenceAgent(BaseAgent):
    """Test double that always returns low confidence."""

    def execute(self, task: EmailThread) -> AgentResult:
        return AgentResult(
            data={"thread_id": task.thread_id},
            confidence=0.5,
            requires_approval=False,
            reasoning="Low confidence test result",
        )


NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _force_email_sla_defaults() -> None:
    """Isolate email SLA from project/.env demo overrides (e.g. 0.0167h)."""
    from agents.email_reply_agent import EmailReplyMonitoringAgent

    previous = EmailReplyMonitoringAgent.THRESHOLD_HOURS
    EmailReplyMonitoringAgent.THRESHOLD_HOURS = 24.0
    try:
        yield
    finally:
        EmailReplyMonitoringAgent.THRESHOLD_HOURS = previous


def test_register_and_retrieve_agent() -> None:
    """Registered agents can be looked up by name."""
    agent = get_agent("email_reply_monitoring")
    assert agent is not None

    register_agent("test_agent", _LowConfidenceAgent())
    assert get_agent("test_agent") is not None


def test_execute_task_returns_expected_structure() -> None:
    """execute_task should return agent name, task id, result, and approval flag."""
    supervisor = Supervisor()
    # 30h ago → UNANSWERED band (past 24h SLA, under 48h critical).
    pending_since = datetime.now(timezone.utc) - timedelta(hours=30)
    thread = EmailThread(
        thread_id="TEST-1",
        messages=[
            EmailMessage(
                sender="client",
                timestamp=pending_since,
            )
        ],
    )

    entry = supervisor.execute_task("email_reply_monitoring", thread, "TEST-1")

    assert entry["agent_name"] == "email_reply_monitoring"
    assert entry["task_id"] == "TEST-1"
    assert entry["entry_id"]
    assert entry["result"].confidence == 1.0
    # UNANSWERED is HITL — Supervisor requires approval before outbound mail.
    assert entry["result"].data.get("status") == "UNANSWERED"
    assert entry["final_approval_needed"] is True
    assert len(get_audit_log()) == 1
    assert get_audit_log()[0]["id"] == entry["entry_id"]
    assert get_audit_log()[0]["approval_status"] == "PENDING"
    assert get_audit_log()[0].get("input") is not None


def test_run_batch_aggregates_counts_correctly() -> None:
    """run_batch should aggregate approval counts across tasks."""
    supervisor = Supervisor()
    now = datetime.now(timezone.utc)
    threads = [
        EmailThread(
            thread_id="BATCH-1",
            messages=[
                EmailMessage(sender="client", timestamp=now - timedelta(hours=30))
            ],
        ),
        EmailThread(
            thread_id="BATCH-2",
            messages=[
                EmailMessage(sender="team", timestamp=now - timedelta(hours=1))
            ],
        ),
    ]

    summary = supervisor.run_batch(
        "email_reply_monitoring",
        threads,
        ["BATCH-1", "BATCH-2"],
    )

    assert summary["total"] == 2
    assert summary["needs_approval_count"] == 1
    assert summary["auto_processed_count"] == 1
    assert len(summary["results"]) == 2
    assert len(get_audit_log()) == 2


def test_approval_policy_low_confidence_forces_approval() -> None:
    """Confidence below 0.75 should force approval even if agent said False."""
    register_agent("low_confidence_test", _LowConfidenceAgent())
    result = AgentResult(
        data={},
        confidence=0.5,
        requires_approval=False,
        reasoning="test",
    )

    assert requires_human_approval("low_confidence_test", result) is True

    supervisor = Supervisor()
    thread = EmailThread(thread_id="LOW-1", messages=[])
    entry = supervisor.execute_task("low_confidence_test", thread, "LOW-1")

    assert entry["final_approval_needed"] is True


def test_unknown_agent_name_raises_clear_error() -> None:
    """Requesting an unregistered agent should raise a descriptive error."""
    supervisor = Supervisor()
    thread = EmailThread(thread_id="X-1", messages=[])

    with pytest.raises(KeyError, match="Agent 'does_not_exist' not found"):
        supervisor.execute_task("does_not_exist", thread, "X-1")


def test_vendor_followup_waiting_through_supervisor_does_not_force_approval() -> None:
    """WAITING vendor results should auto-process when confidence is high."""
    from supervisor.approval_policy import RISKY_STATUS_MAP

    assert "vendor_followup" in RISKY_STATUS_MAP
    assert "WAITING" not in RISKY_STATUS_MAP["vendor_followup"]

    supervisor = Supervisor()
    now = datetime.now(timezone.utc)
    task = VendorQuoteRequest(
        vendor_name="Safe Vendor",
        project_id="PRJ-SAFE",
        request_sent_at=now - timedelta(hours=10),
        quote_received=False,
    )
    entry = supervisor.execute_task("vendor_followup", task, "PRJ-SAFE")

    assert entry["result"].data["status"] == "WAITING"
    assert entry["result"].confidence == 1.0
    assert entry["result"].requires_approval is False
    assert entry["final_approval_needed"] is False


def test_vendor_followup_reminder_through_supervisor_forces_approval() -> None:
    """SEND_REMINDER vendor results must require approval via status map."""
    supervisor = Supervisor()
    now = datetime.now(timezone.utc)
    task = VendorQuoteRequest(
        vendor_name="Late Vendor",
        project_id="PRJ-LATE",
        request_sent_at=now - timedelta(hours=60),
        quote_received=False,
    )
    entry = supervisor.execute_task("vendor_followup", task, "PRJ-LATE")

    assert entry["result"].data["status"] == "SEND_REMINDER"
    assert entry["result"].confidence == 1.0
    assert entry["final_approval_needed"] is True
