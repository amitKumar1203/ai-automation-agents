"""Tests for per-status approval policy rules."""

from models.agent_result import AgentResult
from supervisor.approval_policy import (
    RISKY_STATUS_MAP,
    get_risky_statuses,
    requires_human_approval,
)


def _result(
    *,
    status: str | None = None,
    confidence: float = 1.0,
    requires_approval: bool = False,
    include_status: bool = True,
) -> AgentResult:
    data: dict = {"vendor_name": "Test", "project_id": "PRJ-1", "hours_pending": 1.0}
    if include_status and status is not None:
        data["status"] = status
    elif not include_status:
        data.pop("status", None)

    return AgentResult(
        data=data,
        confidence=confidence,
        requires_approval=requires_approval,
        reasoning="test",
    )


def test_vendor_send_reminder_forces_approval() -> None:
    """SEND_REMINDER is a risky status for vendor_followup."""
    result = _result(status="SEND_REMINDER", confidence=1.0, requires_approval=False)
    assert requires_human_approval("vendor_followup", result) is True


def test_vendor_escalate_forces_approval() -> None:
    """ESCALATE is a risky status for vendor_followup."""
    result = _result(status="ESCALATE", confidence=1.0, requires_approval=False)
    assert requires_human_approval("vendor_followup", result) is True


def test_vendor_waiting_does_not_force_approval() -> None:
    """WAITING is not risky — high confidence + agent False should return False."""
    result = _result(status="WAITING", confidence=1.0, requires_approval=False)
    assert requires_human_approval("vendor_followup", result) is False


def test_vendor_ok_does_not_force_approval() -> None:
    """OK is not risky — high confidence + agent False should return False."""
    result = _result(status="OK", confidence=1.0, requires_approval=False)
    assert requires_human_approval("vendor_followup", result) is False


def test_vendor_risky_status_with_low_confidence_still_true() -> None:
    """Risky status with low confidence still returns True without conflict."""
    result = _result(status="SEND_REMINDER", confidence=0.5, requires_approval=False)
    assert requires_human_approval("vendor_followup", result) is True


def test_email_unanswered_forces_approval() -> None:
    """UNANSWERED is a risky status for email_reply_monitoring (HITL)."""
    assert "UNANSWERED" in RISKY_STATUS_MAP["email_reply_monitoring"]
    assert "CRITICAL" in RISKY_STATUS_MAP["email_reply_monitoring"]
    result = AgentResult(
        data={"thread_id": "T-1", "hours_pending": 30.0, "status": "UNANSWERED"},
        confidence=1.0,
        requires_approval=False,
        reasoning="overdue",
    )
    assert requires_human_approval("email_reply_monitoring", result) is True


def test_email_critical_forces_approval() -> None:
    """CRITICAL is a risky status for email_reply_monitoring (HITL)."""
    result = AgentResult(
        data={"thread_id": "T-1", "hours_pending": 50.0, "status": "CRITICAL"},
        confidence=1.0,
        requires_approval=False,
        reasoning="critical",
    )
    assert requires_human_approval("email_reply_monitoring", result) is True


def test_email_at_risk_does_not_force_approval() -> None:
    """AT_RISK is visibility-only and does not require approval at high confidence."""
    result = AgentResult(
        data={"thread_id": "T-1", "hours_pending": 20.0, "status": "AT_RISK"},
        confidence=1.0,
        requires_approval=False,
        reasoning="approaching",
    )
    assert requires_human_approval("email_reply_monitoring", result) is False


def test_email_ok_does_not_force_approval() -> None:
    """OK email status does not require approval at high confidence."""
    result = AgentResult(
        data={"thread_id": "T-1", "hours_pending": 1.0, "status": "OK"},
        confidence=1.0,
        requires_approval=False,
        reasoning="within threshold",
    )
    assert requires_human_approval("email_reply_monitoring", result) is False


def test_email_agent_low_confidence_still_forces_approval() -> None:
    """Confidence check still applies to email agent."""
    result = AgentResult(
        data={"thread_id": "T-1", "status": "OK"},
        confidence=0.5,
        requires_approval=False,
        reasoning="uncertain",
    )
    assert requires_human_approval("email_reply_monitoring", result) is True


def test_missing_status_key_falls_through_safely() -> None:
    """Missing status for a mapped agent must not crash; fall through to confidence."""
    result = _result(include_status=False, confidence=1.0, requires_approval=False)
    assert "status" not in result.data
    assert requires_human_approval("vendor_followup", result) is False


def test_missing_status_with_low_confidence_returns_true() -> None:
    """Missing status still triggers approval via confidence check."""
    result = _result(include_status=False, confidence=0.4, requires_approval=False)
    assert requires_human_approval("vendor_followup", result) is True


def test_get_risky_statuses_helper() -> None:
    """Helper returns configured statuses or an empty set for unknown agents."""
    assert get_risky_statuses("vendor_followup") == {"SEND_REMINDER", "ESCALATE"}
    assert get_risky_statuses("po_automation") == {"PO_READY_FOR_RELEASE"}
    assert get_risky_statuses("artwork_verification") == {"MISMATCH", "UNCERTAIN"}
    assert get_risky_statuses("email_reply_monitoring") == {"UNANSWERED", "CRITICAL"}
    assert get_risky_statuses("unknown_agent") == set()


def test_artwork_uncertain_forces_approval() -> None:
    """UNCERTAIN is a risky status for artwork_verification."""
    result = _result(status="UNCERTAIN", confidence=1.0, requires_approval=False)
    assert requires_human_approval("artwork_verification", result) is True
