"""Automated Follow-Up Agent — flags stalled / inactive projects (rule-based)."""

from __future__ import annotations

from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import ProjectActivity
from supervisor.write_back import get_followup_escalate_days, get_followup_inactive_days


class AutomatedFollowUpAgent(BaseAgent):
    """Monitors project inactivity and recommends follow-up or escalation.

    Thresholds come from env (no code change to tune for production):
    - ``FOLLOWUP_INACTIVE_DAYS`` (default 7) → ``SEND_FOLLOWUP``
    - ``FOLLOWUP_ESCALATE_DAYS`` (default 14) → ``ESCALATE``
    """

    def execute(
        self,
        task: ProjectActivity,
        current_time: datetime | None = None,
    ) -> AgentResult:
        """Evaluate whether a project has gone silent beyond SLA thresholds."""
        now = current_time if current_time is not None else datetime.now(timezone.utc)
        inactive_days = get_followup_inactive_days()
        escalate_days = get_followup_escalate_days()

        days_inactive = round(self._days_since(task.last_activity_at, now), 1)

        def _base(**extra: object) -> dict:
            payload: dict = {
                "project_id": task.project_id,
                "project_name": task.project_name,
                "stage": task.stage,
                "owner_email": task.owner_email,
                "days_inactive": days_inactive,
                "inactive_threshold_days": inactive_days,
                "escalate_threshold_days": escalate_days,
                **extra,
            }
            if task.monday_item_id:
                payload["monday_item_id"] = task.monday_item_id
            return payload

        if days_inactive < 0:
            return AgentResult(
                data=_base(status="INVALID_DATE"),
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Data issue: last_activity_at for '{task.project_id}' is in the "
                    f"future — fix the source record before evaluating follow-up."
                ),
            )

        if days_inactive >= escalate_days:
            return AgentResult(
                data=_base(status="ESCALATE"),
                confidence=1.0,
                requires_approval=True,
                reasoning=(
                    f"Project '{task.project_name}' ({task.project_id}) inactive for "
                    f"{days_inactive} days (escalate ≥ {escalate_days:g}d) — "
                    f"escalate to owner / ops"
                ),
            )

        if days_inactive >= inactive_days:
            return AgentResult(
                data=_base(status="SEND_FOLLOWUP"),
                confidence=1.0,
                requires_approval=True,
                reasoning=(
                    f"Project '{task.project_name}' ({task.project_id}) inactive for "
                    f"{days_inactive} days (follow-up ≥ {inactive_days:g}d) — "
                    f"send follow-up recommended"
                ),
            )

        return AgentResult(
            data=_base(status="OK"),
            confidence=1.0,
            requires_approval=False,
            reasoning=(
                f"Project '{task.project_name}' ({task.project_id}) active within "
                f"{inactive_days:g}d threshold ({days_inactive} days since last activity)"
            ),
        )

    @staticmethod
    def _days_since(past: datetime, now: datetime) -> float:
        return (now - past).total_seconds() / 86400
