"""AI Mock-up Agent — assess site + artwork composite readiness (Phase 3)."""

from typing import Any

from agents.base_agent import BaseAgent
from integrations.phase3_vision import analyze_mockup
from models.agent_result import AgentResult


class AIMockupAgent(BaseAgent):
    """Evaluate mock-up quality before external client sharing."""

    def execute(self, task: Any) -> AgentResult:
        return AgentResult(
            data={"status": "SKIPPED", "reason": "on_demand_vision_only"},
            confidence=1.0,
            requires_approval=False,
            reasoning="Use POST /api/phase3/mockup/analyze with site + artwork images.",
        )

    def execute_vision(
        self,
        *,
        site_image_bytes: bytes,
        site_media_type: str,
        artwork_image_bytes: bytes,
        artwork_media_type: str,
        brief: str = "",
        project_id: str = "",
        client_email: str = "",
    ) -> AgentResult:
        vision = analyze_mockup(
            site_image_bytes=site_image_bytes,
            site_media_type=site_media_type,
            artwork_image_bytes=artwork_image_bytes,
            artwork_media_type=artwork_media_type,
            brief=brief,
        )
        status = str(vision["status"])
        details = vision.get("details") or {}
        requires_approval = status in {"READY_FOR_EXTERNAL_SHARE", "LOW_CONFIDENCE"}

        return AgentResult(
            data={
                "project_id": project_id,
                "status": status,
                "client_email": client_email,
                "alignment_notes": str(details.get("alignment_notes") or ""),
                "scale_assessment": str(details.get("scale_assessment") or ""),
                "revision_items": str(details.get("revision_items") or ""),
            },
            confidence=float(vision["confidence"]),
            requires_approval=requires_approval,
            reasoning=str(vision["reasoning"]),
        )
