"""Artwork Verification Agent — rule-based and vision-based checks."""

from datetime import datetime
from typing import Optional

from agents.base_agent import BaseAgent
from integrations.vision_verification import analyze_artwork_image
from models.agent_result import AgentResult
from models.task import ArtworkSubmission


class ArtworkVerificationAgent(BaseAgent):
    """Compare submitted artwork dimensions to project window specs.

    Status (rule-based ``execute``):
    - MATCH when both width and height are within ±0.25 in
    - MISMATCH when either dimension exceeds tolerance (requires approval)

    Vision path (``execute_vision``) is additive and uses Claude image analysis.
    """

    TOLERANCE_INCHES: float = 0.25

    def execute(
        self,
        task: ArtworkSubmission,
        current_time: datetime | None = None,
    ) -> AgentResult:
        """Compare artwork dims to the project spec.

        Args:
            task: The artwork submission to evaluate.
            current_time: Unused; accepted for interface consistency with other agents.

        Returns:
            AgentResult with status MATCH or MISMATCH.
        """
        _ = current_time

        art_w = float(task.artwork_width_inches)
        art_h = float(task.artwork_height_inches)
        width_diff = abs(art_w - task.spec_width_inches)
        height_diff = abs(art_h - task.spec_height_inches)
        width_diff_r = round(width_diff, 2)
        height_diff_r = round(height_diff, 2)

        data = {
            "project_id": task.project_id,
            "width_diff": width_diff_r,
            "height_diff": height_diff_r,
            "artwork_width_inches": round(art_w, 2),
            "artwork_height_inches": round(art_h, 2),
            "spec_width_inches": round(task.spec_width_inches, 2),
            "spec_height_inches": round(task.spec_height_inches, 2),
        }

        if width_diff <= self.TOLERANCE_INCHES and height_diff <= self.TOLERANCE_INCHES:
            return AgentResult(
                data={**data, "status": "MATCH"},
                confidence=1.0,
                requires_approval=False,
                reasoning=(
                    f"Artwork dimensions match spec within tolerance "
                    f"(±{self.TOLERANCE_INCHES}in)"
                ),
            )

        mismatch_parts: list[str] = []
        if width_diff > self.TOLERANCE_INCHES:
            mismatch_parts.append(
                f"Width mismatch: artwork {art_w}in vs "
                f"spec {task.spec_width_inches}in (diff {width_diff_r}in, "
                f"exceeds ±{self.TOLERANCE_INCHES}in tolerance)"
            )
        if height_diff > self.TOLERANCE_INCHES:
            mismatch_parts.append(
                f"Height mismatch: artwork {art_h}in vs "
                f"spec {task.spec_height_inches}in (diff {height_diff_r}in, "
                f"exceeds ±{self.TOLERANCE_INCHES}in tolerance)"
            )

        return AgentResult(
            data={**data, "status": "MISMATCH"},
            confidence=1.0,
            requires_approval=True,
            reasoning="; ".join(mismatch_parts),
        )

    def execute_vision(
        self,
        artwork_image_bytes: bytes,
        artwork_media_type: str,
        spec_description: str,
        spec_image_bytes: Optional[bytes] = None,
        spec_media_type: Optional[str] = None,
        project_id: str = "",
    ) -> AgentResult:
        """Verify artwork using Claude vision against a text and/or image spec.

        This path is additive to ``execute()`` and does not alter the rule-based
        numeric comparison. MISMATCH and UNCERTAIN always request human review;
        only MATCH maps to ``requires_approval=False`` (Supervisor confidence
        rules may still escalate low-confidence MATCH results).

        Args:
            artwork_image_bytes: Raw bytes of the uploaded artwork image.
            artwork_media_type: MIME type of the artwork image.
            spec_description: Text description of expected dimensions/design.
            spec_image_bytes: Optional reference/spec image bytes.
            spec_media_type: MIME type of the optional spec image.
            project_id: Optional project identifier for audit/UI context.

        Returns:
            AgentResult with vision status, confidence, and reasoning.
        """
        vision = analyze_artwork_image(
            artwork_image_bytes=artwork_image_bytes,
            artwork_media_type=artwork_media_type,
            spec_description=spec_description,
            spec_image_bytes=spec_image_bytes,
            spec_media_type=spec_media_type,
        )

        status = str(vision["status"])
        details = vision.get("details") or {}
        dimensions_visible = bool(details.get("dimensions_visible", False))
        reasoning = str(vision["reasoning"])
        confidence = float(vision["confidence"])

        requires_approval = status != "MATCH"

        return AgentResult(
            data={
                "project_id": project_id,
                "status": status,
                "vision_reasoning": reasoning,
                "dimensions_visible": dimensions_visible,
            },
            confidence=confidence,
            requires_approval=requires_approval,
            reasoning=reasoning,
        )
