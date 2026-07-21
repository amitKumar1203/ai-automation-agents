"""Installation Quality Control Agent — install vs reference comparison (Phase 3)."""

from typing import Any

from agents.base_agent import BaseAgent
from integrations.phase3_vision import analyze_installation_qc
from models.agent_result import AgentResult


class InstallationQCAgent(BaseAgent):
    """Compare installation photos against approved renderings for QC sign-off."""

    def execute(self, task: Any) -> AgentResult:
        return AgentResult(
            data={"status": "SKIPPED", "reason": "on_demand_vision_only"},
            confidence=1.0,
            requires_approval=False,
            reasoning=(
                "Use POST /api/phase3/installation-qc/analyze with install + reference."
            ),
        )

    def execute_vision(
        self,
        *,
        install_image_bytes: bytes,
        install_media_type: str,
        reference_image_bytes: bytes,
        reference_media_type: str,
        spec_notes: str = "",
        project_id: str = "",
        monday_item_id: str = "",
    ) -> AgentResult:
        vision = analyze_installation_qc(
            install_image_bytes=install_image_bytes,
            install_media_type=install_media_type,
            reference_image_bytes=reference_image_bytes,
            reference_media_type=reference_media_type,
            spec_notes=spec_notes,
        )
        status = str(vision["status"])
        details = vision.get("details") or {}
        requires_approval = status in {"FAIL", "NEEDS_REVIEW", "LOW_CONFIDENCE"}

        return AgentResult(
            data={
                "project_id": project_id,
                "monday_item_id": monday_item_id,
                "status": status,
                "defects": str(details.get("defects") or ""),
                "alignment_score": str(details.get("alignment_score") or ""),
                "recommendation": str(details.get("recommendation") or ""),
            },
            confidence=float(vision["confidence"]),
            requires_approval=requires_approval,
            reasoning=str(vision["reasoning"]),
        )
