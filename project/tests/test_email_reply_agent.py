"""Tests for EmailReplyMonitoringAgent."""

from datetime import datetime, timedelta, timezone

import pytest

from agents.email_reply_agent import EmailReplyMonitoringAgent
from models.task import EmailMessage, EmailThread


NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=timezone.utc)
AGENT = EmailReplyMonitoringAgent()


@pytest.fixture(autouse=True)
def _force_default_threshold() -> None:
    """Keep unit tests on the default 24h window regardless of host env."""
    EmailReplyMonitoringAgent.THRESHOLD_HOURS = 24.0


def _thread(
    messages: list[EmailMessage],
    thread_id: str = "thread-1",
    subject: str = "",
) -> EmailThread:
    return EmailThread(thread_id=thread_id, messages=messages, subject=subject)


def test_client_message_30_hours_old_is_unanswered() -> None:
    """Client's last message older than 24h should be flagged as unanswered."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=30),
                text="Any update on my order?",
            )
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["hours_pending"] == 30.0
    assert result.data["status"] == "UNANSWERED"
    assert result.confidence == 1.0
    assert result.requires_approval is True
    assert "pending reply" in result.reasoning
    assert result.data["draft_reply"]
    assert "Thank you for your message" in result.data["draft_reply"]


def test_client_message_50_hours_old_is_critical() -> None:
    """Past 2× SLA should elevate to CRITICAL with HITL."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=50),
                text="Still waiting on my order.",
            )
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["status"] == "CRITICAL"
    assert result.requires_approval is True
    assert "CRITICAL" in result.reasoning
    assert result.data["draft_reply"]


def test_client_message_20_hours_old_is_at_risk() -> None:
    """Past 75% of SLA but under threshold → AT_RISK (no HITL)."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=20),
                text="Quick question about delivery.",
            )
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["status"] == "AT_RISK"
    assert result.requires_approval is False
    assert "Approaching SLA" in result.reasoning
    assert result.data["draft_reply"]


def test_client_message_10_hours_old_is_ok() -> None:
    """Client's last message within early window should be OK."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=10),
                text="Quick question about delivery.",
            )
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["hours_pending"] == 10.0
    assert result.data["status"] == "OK"
    assert result.confidence == 1.0
    assert "within" in result.reasoning.lower()
    assert result.data["draft_reply"] == ""


def test_urgent_keywords_raise_priority() -> None:
    """ASAP / cancel cues should mark priority high and list keywords."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=30),
                text="This is URGENT — please cancel my order ASAP.",
            )
        ],
        subject="Need refund today",
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["priority"] == "high"
    keywords = result.data["urgency_keywords"]
    assert "urgent" in keywords
    assert "asap" in keywords
    assert "cancel" in keywords or "refund" in keywords or "today" in keywords
    assert "prioritising" in result.data["draft_reply"].lower() or "prioritizing" in result.data["draft_reply"].lower()


def test_team_replied_after_client_is_not_unanswered() -> None:
    """When team sent the last message, thread should not be unanswered."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=48),
                text="When will this ship?",
            ),
            EmailMessage(
                sender="team",
                timestamp=NOW - timedelta(hours=2),
                text="It ships tomorrow.",
            ),
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["hours_pending"] == 2.0
    assert result.data["status"] == "OK"
    assert "team has already replied" in result.reasoning.lower()


def test_internal_last_message_is_not_unanswered() -> None:
    """Same-domain internal senders must not trigger unanswered client alerts."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=48),
                text="Any update?",
            ),
            EmailMessage(
                sender="internal",
                timestamp=NOW - timedelta(hours=30),
                text="FYI — looping in the team.",
            ),
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["hours_pending"] == 30.0
    assert result.data["status"] == "OK"
    assert result.confidence == 1.0
    assert result.requires_approval is False
    assert "pending reply" not in result.reasoning.lower()
    assert "internal" in result.reasoning.lower()
    assert "not from an external client" in result.reasoning.lower()


def test_exactly_24_hours_is_not_unanswered() -> None:
    """Exactly 24h old uses strict > threshold, so it is NOT unanswered."""
    thread = _thread(
        [
            EmailMessage(
                sender="client",
                timestamp=NOW - timedelta(hours=24),
                text="Following up.",
            )
        ]
    )

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["hours_pending"] == 24.0
    # At exactly SLA boundary: AT_RISK (past 75%) but not yet UNANSWERED.
    assert result.data["status"] == "AT_RISK"


def test_empty_messages_list_handled_gracefully() -> None:
    """Empty thread should not crash and should return zero confidence."""
    thread = EmailThread(thread_id="empty-thread", messages=[])

    result = AGENT.execute(thread, current_time=NOW)

    assert result.data["thread_id"] == "empty-thread"
    assert result.confidence == 0.0
    assert result.requires_approval is False
    assert result.reasoning == "No messages found"


def test_threshold_can_be_lowered_for_live_demo() -> None:
    """A lowered THRESHOLD_HOURS (as via EMAIL_THRESHOLD_HOURS) flags sooner."""
    previous = EmailReplyMonitoringAgent.THRESHOLD_HOURS
    try:
        EmailReplyMonitoringAgent.THRESHOLD_HOURS = 0.5  # 30 minutes
        thread = _thread(
            [
                EmailMessage(
                    sender="client",
                    timestamp=NOW - timedelta(hours=1),
                    text="Still waiting.",
                )
            ]
        )

        result = AGENT.execute(thread, current_time=NOW)

        assert result.data["hours_pending"] == 1.0
        # 1h == 2×0.5 → not yet CRITICAL (strict >); still UNANSWERED.
        assert result.data["status"] == "UNANSWERED"
        assert "pending reply" in result.reasoning.lower()
    finally:
        EmailReplyMonitoringAgent.THRESHOLD_HOURS = previous
