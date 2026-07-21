"""AI Rendering Agent — site photo analysis and design alternatives (Phase 3)."""

from typing import Any, Optional

from agents.base_agent import BaseAgent
from integrations.phase3_vision import analyze_rendering
from models.agent_result import AgentResult


class AIRenderingAgent(BaseAgent):
    """Assess site photos and produce structured rendering guidance for designers."""

    def execute(self, task: Any) -> AgentResult:
        return AgentResult(
            data={"status": "SKIPPED", "reason": "on_demand_vision_only"},
            confidence=1.0,
            requires_approval=False,
            reasoning="Use POST /api/phase3/rendering/analyze with site photo upload.",
        )

    def execute_vision(
        self,
        *,
        site_image_bytes: bytes,
        site_media_type: str,
        design_brief: str,
        artwork_image_bytes: Optional[bytes] = None,
        artwork_media_type: Optional[str] = None,
        project_id: str = "",
    ) -> AgentResult:
        vision = analyze_rendering(
            site_image_bytes=site_image_bytes,
            site_media_type=site_media_type,
            design_brief=design_brief,
            artwork_image_bytes=artwork_image_bytes,
            artwork_media_type=artwork_media_type,
        )
        status = str(vision["status"])
        details = vision.get("details") or {}
        requires_approval = status in {"READY_FOR_REVIEW", "LOW_CONFIDENCE"}

        return AgentResult(
            data={
                "project_id": project_id,
                "status": status,
                "window_type": str(details.get("window_type") or ""),
                "design_alternatives": str(details.get("design_alternatives") or ""),
                "color_palette": str(details.get("color_palette") or ""),
                "notes": str(details.get("notes") or ""),
            },
            confidence=float(vision["confidence"]),
            requires_approval=requires_approval,
            reasoning=str(vision["reasoning"]),
        )
