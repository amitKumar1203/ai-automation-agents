"""Photo Analysis Agent — survey photo field extraction (Phase 3)."""

from typing import Any

from agents.base_agent import BaseAgent
from integrations.phase3_vision import analyze_survey_photo
from models.agent_result import AgentResult


class PhotoAnalysisAgent(BaseAgent):
    """Extract branding, installation type, and suggested fields from survey photos."""

    def execute(self, task: Any) -> AgentResult:
        return AgentResult(
            data={"status": "SKIPPED", "reason": "on_demand_vision_only"},
            confidence=1.0,
            requires_approval=False,
            reasoning="Use POST /api/phase3/photo-analysis/analyze with survey photo.",
        )

    def execute_vision(
        self,
        *,
        survey_image_bytes: bytes,
        survey_media_type: str,
        context: str = "",
        project_id: str = "",
        monday_item_id: str = "",
    ) -> AgentResult:
        vision = analyze_survey_photo(
            survey_image_bytes=survey_image_bytes,
            survey_media_type=survey_media_type,
            context=context,
        )
        status = str(vision["status"])
        details = vision.get("details") or {}
        requires_approval = status in {"ISSUES_FOUND", "LOW_CONFIDENCE"}

        return AgentResult(
            data={
                "project_id": project_id,
                "monday_item_id": monday_item_id,
                "status": status,
                "branding_detected": str(details.get("branding_detected") or ""),
                "installation_type": str(details.get("installation_type") or ""),
                "suggested_fields": str(details.get("suggested_fields") or ""),
                "issues": str(details.get("issues") or ""),
            },
            confidence=float(vision["confidence"]),
            requires_approval=requires_approval,
            reasoning=str(vision["reasoning"]),
        )
