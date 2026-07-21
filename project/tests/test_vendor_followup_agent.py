"""Tests for VendorFollowUpAgent."""

from datetime import datetime, timedelta, timezone

from agents.vendor_followup_agent import VendorFollowUpAgent
from models.task import VendorQuoteRequest

NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
AGENT = VendorFollowUpAgent()


def _request(
    *,
    hours_ago: float,
    quote_received: bool = False,
    quote_received_at: datetime | None = None,
    vendor_name: str = "Test Vendor",
    project_id: str = "PRJ-TEST",
) -> VendorQuoteRequest:
    return VendorQuoteRequest(
        vendor_name=vendor_name,
        project_id=project_id,
        request_sent_at=NOW - timedelta(hours=hours_ago),
        quote_received=quote_received,
        quote_received_at=quote_received_at,
    )


def test_quote_received_is_ok() -> None:
    """When a quote was already received, status should be OK."""
    task = _request(
        hours_ago=72,
        quote_received=True,
        quote_received_at=NOW - timedelta(hours=24),
    )

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "OK"
    assert result.confidence == 1.0
    assert result.requires_approval is False
    assert "already sent a quote" in result.reasoning


def test_within_threshold_is_waiting() -> None:
    """30 hours pending is within the 48h reminder threshold."""
    task = _request(hours_ago=30)

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "WAITING"
    assert result.data["hours_pending"] == 30.0
    assert result.requires_approval is False
    assert "waiting" in result.reasoning.lower()


def test_between_thresholds_is_send_reminder() -> None:
    """60 hours pending is past 48h but under 96h → SEND_REMINDER."""
    task = _request(hours_ago=60)

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "SEND_REMINDER"
    assert result.data["hours_pending"] == 60.0
    assert result.requires_approval is True
    assert "reminder recommended" in result.reasoning.lower()


def test_over_escalation_threshold_is_escalate() -> None:
    """100 hours pending is past 96h → ESCALATE."""
    task = _request(hours_ago=100)

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "ESCALATE"
    assert result.data["hours_pending"] == 100.0
    assert result.requires_approval is True
    assert "escalate" in result.reasoning.lower()


def test_exactly_48_hours_is_waiting_not_reminder() -> None:
    """Exactly 48h uses strict > threshold, so status is WAITING (not SEND_REMINDER)."""
    task = _request(hours_ago=48)

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "WAITING"
    assert result.data["hours_pending"] == 48.0
    assert result.requires_approval is False


def test_exactly_96_hours_is_reminder_not_escalate() -> None:
    """Exactly 96h uses strict > threshold, so status is SEND_REMINDER (not ESCALATE)."""
    task = _request(hours_ago=96)

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "SEND_REMINDER"
    assert result.data["hours_pending"] == 96.0
    assert result.requires_approval is True


def test_future_request_sent_at_is_invalid_date() -> None:
    """Negative hours_pending (future request_sent_at) flags INVALID_DATE."""
    # hours_ago=-5 → request_sent_at is 5 hours in the future
    task = _request(
        hours_ago=-5,
        vendor_name="Delta Corp",
        project_id="P-103",
    )

    result = AGENT.execute(task, current_time=NOW)

    assert result.data["status"] == "INVALID_DATE"
    assert result.data["hours_pending"] == -5.0
    assert result.confidence == 1.0
    assert result.requires_approval is False
    reasoning = result.reasoning.lower()
    assert "data issue" in reasoning
    assert "future" in reasoning

