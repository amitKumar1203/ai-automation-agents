"""Vendor Follow-Up Agent — tracks overdue vendor quote responses."""

from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import VendorQuoteRequest


class VendorFollowUpAgent(BaseAgent):
    """Monitors vendor quote requests and flags reminders or escalations."""

    REMINDER_THRESHOLD_HOURS: float = 48
    ESCALATION_THRESHOLD_HOURS: float = 96

    def execute(
        self,
        task: VendorQuoteRequest,
        current_time: datetime | None = None,
    ) -> AgentResult:
        """Analyze a vendor quote request and determine follow-up status.

        Args:
            task: The vendor quote request to evaluate.
            current_time: Optional fixed timestamp for testing; defaults to UTC now.

        Returns:
            AgentResult with status OK, WAITING, SEND_REMINDER, ESCALATE,
            or INVALID_DATE (when ``request_sent_at`` is in the future).
        """
        now = current_time if current_time is not None else datetime.now(timezone.utc)

        def _base_data(**extra: object) -> dict:
            payload: dict = {
                "vendor_name": task.vendor_name,
                "project_id": task.project_id,
                **extra,
            }
            if task.monday_item_id:
                payload["monday_item_id"] = task.monday_item_id
            return payload

        if task.quote_received:
            hours_pending = 0.0
            if task.quote_received_at is not None:
                hours_pending = round(
                    self._hours_since(task.request_sent_at, task.quote_received_at),
                    1,
                )
            return AgentResult(
                data=_base_data(hours_pending=hours_pending, status="OK"),
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Vendor '{task.vendor_name}' has already sent a quote "
                    f"for project '{task.project_id}' — no action needed"
                ),
            )

        hours_pending = round(self._hours_since(task.request_sent_at, now), 1)

        # Future request_sent_at is a board data-entry issue, not a follow-up case.
        if hours_pending < 0:
            sent_date = task.request_sent_at.date().isoformat()
            return AgentResult(
                data=_base_data(hours_pending=hours_pending, status="INVALID_DATE"),
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Data issue: request_sent_at for vendor '{task.vendor_name}' "
                    f"project '{task.project_id}' is in the future ({sent_date}). "
                    f"Please check the Monday.com board — this entry cannot be "
                    f"evaluated correctly."
                ),
            )

        if hours_pending > self.ESCALATION_THRESHOLD_HOURS:
            return AgentResult(
                data=_base_data(hours_pending=hours_pending, status="ESCALATE"),
                confidence=1.0,
                requires_approval=True,
                reasoning=(
                    f"Vendor '{task.vendor_name}' has not responded in "
                    f"{hours_pending} hours (escalation threshold: "
                    f"{self.ESCALATION_THRESHOLD_HOURS:.0f}h) — escalate for human decision"
                ),
            )

        if hours_pending > self.REMINDER_THRESHOLD_HOURS:
            return AgentResult(
                data=_base_data(hours_pending=hours_pending, status="SEND_REMINDER"),
                confidence=1.0,
                requires_approval=True,
                reasoning=(
                    f"Vendor '{task.vendor_name}' has not responded in "
                    f"{hours_pending} hours (reminder threshold: "
                    f"{self.REMINDER_THRESHOLD_HOURS:.0f}h) — reminder recommended"
                ),
            )

        return AgentResult(
            data=_base_data(hours_pending=hours_pending, status="WAITING"),
            confidence=1.0,
            requires_approval=False,
            reasoning=(
                f"Vendor '{task.vendor_name}' request is within "
                f"{self.REMINDER_THRESHOLD_HOURS:.0f}h threshold "
                f"({hours_pending} hours pending) — waiting"
            ),
        )

    @staticmethod
    def _hours_since(past: datetime, now: datetime) -> float:
        """Return the number of hours elapsed between two timestamps."""
        delta = now - past
        return delta.total_seconds() / 3600
