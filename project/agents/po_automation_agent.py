"""Purchase Order Automation Agent — prepares PO drafts for approved projects."""

from datetime import datetime, timezone

from agents.base_agent import BaseAgent
from models.agent_result import AgentResult
from models.task import ProjectApproval


class POAutomationAgent(BaseAgent):
    """Detects approved projects missing a PO and prepares a draft for release."""

    def execute(
        self,
        task: ProjectApproval,
        current_time: datetime | None = None,
    ) -> AgentResult:
        """Analyze a project approval and prepare a PO draft if needed.

        Args:
            task: The project approval to evaluate.
            current_time: Optional fixed timestamp for testing; defaults to UTC now.

        Returns:
            AgentResult with status ALREADY_EXISTS or PO_READY_FOR_RELEASE.
        """
        now = current_time if current_time is not None else datetime.now(timezone.utc)

        def _with_sf_id(payload: dict) -> dict:
            if task.salesforce_id:
                payload = {**payload, "salesforce_id": task.salesforce_id}
            return payload

        if task.po_exists:
            return AgentResult(
                data=_with_sf_id(
                    {
                        "project_id": task.project_id,
                        "client_name": task.client_name,
                        "status": "ALREADY_EXISTS",
                    }
                ),
                confidence=1.0,
                requires_approval=False,
                reasoning="PO already exists for this project, no action needed",
            )

        draft_po = {
            "project_id": task.project_id,
            "client_name": task.client_name,
            "vendor_name": task.vendor_name,
            "estimated_amount": task.estimated_amount,
            "generated_at": now.isoformat(),
        }

        return AgentResult(
            data=_with_sf_id(
                {
                    "project_id": task.project_id,
                    "client_name": task.client_name,
                    "status": "PO_READY_FOR_RELEASE",
                    "draft_po": draft_po,
                }
            ),
            confidence=1.0,
            requires_approval=True,
            reasoning=(
                f"PO draft prepared for project {task.project_id} "
                f"({task.client_name}) — ${task.estimated_amount:,.2f} — "
                f"awaiting release approval"
            ),
        )
