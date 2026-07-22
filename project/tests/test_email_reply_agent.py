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


def _thread(messages: list[EmailMessage], thread_id: str = "thread-1") -> EmailThread:
    return EmailThread(thread_id=thread_id, messages=messages)


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


def test_client_message_10_hours_old_is_not_unanswered() -> None:
    """Client's last message within 24h should not require action."""
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
    assert result.confidence == 1.0
    assert "within" in result.reasoning.lower()


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
    assert "within" in result.reasoning.lower()


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
    assert "pending reply" in result.reasoning.lower()
