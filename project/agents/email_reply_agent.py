"""Email Reply Monitoring Agent — SLA bands, urgency, and draft replies."""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import EmailThread

# Only genuine external clients trigger unanswered alerts.
# "team" and "internal" (same-domain colleagues) never do.
EXTERNAL_SENDER_TYPES: frozenset[str] = frozenset({"client"})

# Hours past threshold → CRITICAL (defaults to 2× SLA).
_CRITICAL_MULTIPLIER = float(os.environ.get("EMAIL_CRITICAL_MULTIPLIER", "2"))
# Fraction of threshold → AT_RISK warning band (defaults to 75% of SLA).
_AT_RISK_RATIO = float(os.environ.get("EMAIL_AT_RISK_RATIO", "0.75"))

_URGENT_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\basap\b",
        r"\burgent\b",
        r"\bimmediately\b",
        r"\bemergency\b",
        r"\bcancel(?:lation)?\b",
        r"\bcomplaint\b",
        r"\bescalat(?:e|ion)\b",
        r"\bnot acceptable\b",
        r"\bdisappointed\b",
        r"\blawsuit\b",
        r"\brefund\b",
        r"\bdeadline\b",
        r"\bcritical\b",
        r"\bright away\b",
        r"\btoday\b",
        r"\boverdue\b",
        r"\bunacceptable\b",
    )
)

_HITL_STATUSES: frozenset[str] = frozenset({"UNANSWERED", "CRITICAL"})
_NEEDS_ATTENTION: frozenset[str] = frozenset({"AT_RISK", "UNANSWERED", "CRITICAL"})


class EmailReplyMonitoringAgent(BaseAgent):
    """Monitors email threads for client messages that exceed the reply threshold.

    SLA bands (relative to ``EMAIL_THRESHOLD_HOURS``, default 24h):

    - ``OK`` — within the early window
    - ``AT_RISK`` — past 75% of threshold, still under SLA (visibility only)
    - ``UNANSWERED`` — past SLA (HITL owner notify)
    - ``CRITICAL`` — past 2× SLA (HITL, elevated severity)

    Also scores urgency from message keywords and drafts a suggested reply for
    any thread that needs attention.
    """

    THRESHOLD_HOURS: float = float(os.environ.get("EMAIL_THRESHOLD_HOURS", 24))

    def execute(
        self,
        task: EmailThread,
        current_time: datetime | None = None,
    ) -> AgentResult:
        """Analyze an email thread and determine SLA / urgency status.

        Args:
            task: The email thread to evaluate.
            current_time: Optional fixed timestamp for testing; defaults to UTC now.

        Returns:
            AgentResult indicating whether the thread needs attention and why.
        """
        now = current_time if current_time is not None else datetime.now(timezone.utc)

        if not task.messages:
            return AgentResult(
                data={"thread_id": task.thread_id, "status": "OK"},
                confidence=0.0,
                requires_approval=False,
                reasoning="No messages found",
            )

        last_message = task.messages[-1]
        hours_pending = self._hours_since(last_message.timestamp, now)
        is_external = last_message.sender in EXTERNAL_SENDER_TYPES
        subject = (getattr(task, "subject", None) or "").strip()
        client_email = getattr(last_message, "sender_email", None) or ""

        if not is_external:
            if last_message.sender == "team":
                reason = "No action needed: team has already replied"
            elif last_message.sender == "internal":
                reason = (
                    "No action needed: last message is internal, "
                    "not from an external client"
                )
            else:
                reason = "No action needed: last sender is not an external client"
            return AgentResult(
                data={
                    "thread_id": task.thread_id,
                    "hours_pending": round(hours_pending, 1),
                    "status": "OK",
                    "priority": "normal",
                    "urgency_keywords": [],
                    "draft_reply": "",
                    "subject": subject,
                    "client_email": client_email,
                },
                confidence=1.0,
                requires_approval=False,
                reasoning=reason,
            )

        status = self._sla_status(hours_pending)
        priority, keywords = self._score_urgency(
            subject=subject,
            text=last_message.text or "",
        )
        # Escalate priority when already past SLA.
        if status in _HITL_STATUSES and priority == "normal" and hours_pending > (
            self.THRESHOLD_HOURS * 1.5
        ):
            priority = "high"

        draft = ""
        if status in _NEEDS_ATTENTION:
            draft = self._draft_reply(
                subject=subject,
                last_text=last_message.text or "",
                priority=priority,
                status=status,
            )

        hours_rounded = round(hours_pending, 1)
        threshold = self.THRESHOLD_HOURS
        if status == "CRITICAL":
            reason = (
                f"CRITICAL: client message pending {hours_rounded}h "
                f"(>{threshold * _CRITICAL_MULTIPLIER:.0f}h = 2× SLA)"
            )
            if keywords:
                reason += f"; urgency cues: {', '.join(keywords[:4])}"
        elif status == "UNANSWERED":
            reason = (
                f"Client message pending reply for {hours_rounded} hours "
                f"(threshold: {threshold:.0f}h)"
            )
            if keywords:
                reason += f"; urgency cues: {', '.join(keywords[:4])}"
        elif status == "AT_RISK":
            reason = (
                f"Approaching SLA: client message pending {hours_rounded}h "
                f"(at-risk from {threshold * _AT_RISK_RATIO:.0f}h, "
                f"SLA {threshold:.0f}h)"
            )
            if keywords:
                reason += f"; urgency cues: {', '.join(keywords[:4])}"
        else:
            reason = (
                f"No action needed: client message is within "
                f"{threshold:.0f}h threshold "
                f"({hours_rounded} hours pending)"
            )

        return AgentResult(
            data={
                "thread_id": task.thread_id,
                "hours_pending": hours_rounded,
                "status": status,
                "priority": priority,
                "urgency_keywords": keywords,
                "draft_reply": draft,
                "client_email": client_email,
                "subject": subject,
            },
            confidence=1.0,
            requires_approval=status in _HITL_STATUSES,
            reasoning=reason,
        )

    def _sla_status(self, hours_pending: float) -> str:
        """Map pending hours onto OK / AT_RISK / UNANSWERED / CRITICAL."""
        threshold = self.THRESHOLD_HOURS
        critical_after = threshold * _CRITICAL_MULTIPLIER
        at_risk_after = threshold * _AT_RISK_RATIO
        if hours_pending > critical_after:
            return "CRITICAL"
        if hours_pending > threshold:
            return "UNANSWERED"
        if hours_pending > at_risk_after:
            return "AT_RISK"
        return "OK"

    @staticmethod
    def _score_urgency(*, subject: str, text: str) -> tuple[str, list[str]]:
        """Return (priority, matched_keywords) from subject + body."""
        blob = f"{subject}\n{text}"
        matched: list[str] = []
        for pattern in _URGENT_PATTERNS:
            found = pattern.search(blob)
            if found:
                token = found.group(0).lower()
                if token not in matched:
                    matched.append(token)
        return ("high" if matched else "normal", matched)

    @staticmethod
    def _draft_reply(
        *,
        subject: str,
        last_text: str,
        priority: str,
        status: str,
    ) -> str:
        """Build a professional suggested reply for reviewer approval."""
        snippet = " ".join((last_text or "").split())
        if len(snippet) > 180:
            snippet = snippet[:177].rstrip() + "…"
        if not snippet:
            snippet = "(no message body)"

        re_subject = subject if subject.lower().startswith("re:") else f"Re: {subject or 'your enquiry'}"
        urgency_line = ""
        if priority == "high" or status == "CRITICAL":
            urgency_line = (
                "I understand this is time-sensitive and I'm prioritising "
                "a full response for you.\n\n"
            )

        return (
            f"Subject: {re_subject}\n\n"
            "Hi,\n\n"
            "Thank you for your message — I'm following up on your note:\n\n"
            f'"{snippet}"\n\n'
            f"{urgency_line}"
            "We're looking into this now and will get back to you shortly "
            "with a clear update.\n\n"
            "Best regards"
        )

    @staticmethod
    def _hours_since(past: datetime, now: datetime) -> float:
        """Return the number of hours elapsed between two timestamps."""
        delta = now - past
        return delta.total_seconds() / 3600
