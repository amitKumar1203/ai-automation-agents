"""Email Reply Monitoring Agent — detects unanswered client messages."""

import os
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import EmailThread

# Only genuine external clients trigger unanswered alerts.
# "team" and "internal" (same-domain colleagues) never do.
EXTERNAL_SENDER_TYPES: frozenset[str] = frozenset({"client"})


class EmailReplyMonitoringAgent(BaseAgent):
    """Monitors email threads for client messages that exceed the reply threshold.

    The reply window defaults to 24 hours and can be overridden via the
    ``EMAIL_THRESHOLD_HOURS`` environment variable (fractional hours allowed,
    e.g. ``0.0167`` ≈ 1 minute) for live Gmail demos without changing code.

    Sender categories (from Gmail domain matching):
    - ``team``: authenticated user's own address
    - ``internal``: same email domain as the user (colleagues)
    - ``client``: external address; only this type can be flagged unanswered
    """

    THRESHOLD_HOURS: float = float(os.environ.get("EMAIL_THRESHOLD_HOURS", 24))

    def execute(
        self,
        task: EmailThread,
        current_time: datetime | None = None,
    ) -> AgentResult:
        """Analyze an email thread and determine if a client reply is overdue.

        Args:
            task: The email thread to evaluate.
            current_time: Optional fixed timestamp for testing; defaults to UTC now.

        Returns:
            AgentResult indicating whether the thread is unanswered and why.
        """
        now = current_time if current_time is not None else datetime.now(timezone.utc)

        if not task.messages:
            return AgentResult(
                data={"thread_id": task.thread_id},
                confidence=0.0,
                requires_approval=False,
                reasoning="No messages found",
            )

        last_message = task.messages[-1]
        hours_pending = self._hours_since(last_message.timestamp, now)
        is_external = last_message.sender in EXTERNAL_SENDER_TYPES

        if is_external and hours_pending > self.THRESHOLD_HOURS:
            client_email = getattr(last_message, "sender_email", None) or ""
            return AgentResult(
                data={
                    "thread_id": task.thread_id,
                    "hours_pending": round(hours_pending, 1),
                    "status": "UNANSWERED",
                    "client_email": client_email,
                    "subject": getattr(task, "subject", None) or "",
                },
                confidence=1.0,
                requires_approval=True,
                reasoning=(
                    f"Client message pending reply for {round(hours_pending, 1)} hours "
                    f"(threshold: {self.THRESHOLD_HOURS:.0f}h)"
                ),
            )

        if last_message.sender == "team":
            reason = "No action needed: team has already replied"
        elif last_message.sender == "internal":
            reason = (
                "No action needed: last message is internal, "
                "not from an external client"
            )
        else:
            reason = (
                f"No action needed: client message is within "
                f"{self.THRESHOLD_HOURS:.0f}h threshold "
                f"({round(hours_pending, 1)} hours pending)"
            )

        return AgentResult(
            data={
                "thread_id": task.thread_id,
                "hours_pending": round(hours_pending, 1),
                "status": "OK",
            },
            confidence=1.0,
            requires_approval=False,
            reasoning=reason,
        )

    @staticmethod
    def _hours_since(past: datetime, now: datetime) -> float:
        """Return the number of hours elapsed between two timestamps."""
        delta = now - past
        return delta.total_seconds() / 3600
