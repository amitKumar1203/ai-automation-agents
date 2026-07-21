"""Claude vision integration for Phase 3 agents (rendering, mock-up, photo, QC).

Uses the same Anthropic client and image helpers as artwork verification.
Each agent gets a forced tool schema with domain-specific status enums.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from integrations.vision_verification import (
    VisionAnalysisError,
    VisionConfigError,
    _image_block,
    get_anthropic_client,
)

_VISION_MODEL = "claude-sonnet-4-5"
_DEFAULT_TIMEOUT = 90.0


def _extract_tool_result(response: Any, tool_name: str) -> dict[str, Any]:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(
            block, "name", None
        ) == tool_name:
            tool_input = getattr(block, "input", None)
            if isinstance(tool_input, dict):
                return tool_input
    raise VisionAnalysisError(
        f"Claude did not return a structured result for tool '{tool_name}'."
    )


def _call_vision_tool(
    *,
    tool_name: str,
    tool_schema: dict[str, Any],
    content_blocks: list[dict[str, Any]],
    prompt: str,
    normalize: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    client = get_anthropic_client()
    messages_content = [*content_blocks, {"type": "text", "text": prompt}]
    try:
        response = client.messages.create(
            model=_VISION_MODEL,
            max_tokens=1536,
            tools=[tool_schema],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[{"role": "user", "content": messages_content}],
        )
    except VisionAnalysisError:
        raise
    except Exception as exc:
        raise VisionAnalysisError(f"Claude vision analysis failed: {exc}") from exc
    return normalize(_extract_tool_result(response, tool_name))


def _normalize_base(
    raw: dict[str, Any],
    *,
    allowed_statuses: set[str],
    details_keys: tuple[str, ...],
) -> dict[str, Any]:
    status = str(raw.get("status", "")).upper().strip()
    if status not in allowed_statuses:
        raise VisionAnalysisError(
            f"Unexpected status '{raw.get('status')}'. "
            f"Expected one of: {', '.join(sorted(allowed_statuses))}."
        )
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError) as exc:
        raise VisionAnalysisError("Vision confidence must be a number.") from exc
    confidence = max(0.0, min(1.0, confidence))
    reasoning = str(raw.get("reasoning") or "").strip()
    if not reasoning:
        raise VisionAnalysisError("Vision reasoning was empty.")
    details_raw = raw.get("details") or {}
    if not isinstance(details_raw, dict):
        details_raw = {}
    details = {key: details_raw.get(key, "") for key in details_keys}
    return {
        "status": status,
        "confidence": confidence,
        "reasoning": reasoning,
        "details": details,
    }


_RENDERING_TOOL = "report_rendering_analysis"
_RENDERING_STATUSES = {"READY_FOR_REVIEW", "APPROVED_INTERNAL", "LOW_CONFIDENCE"}


def analyze_rendering(
    *,
    site_image_bytes: bytes,
    site_media_type: str,
    design_brief: str,
    artwork_image_bytes: Optional[bytes] = None,
    artwork_media_type: Optional[str] = None,
) -> dict[str, Any]:
    """Assess a storefront/site photo and produce rendering guidance."""
    content: list[dict[str, Any]] = [
        _image_block(site_image_bytes, site_media_type),
    ]
    has_artwork = bool(artwork_image_bytes)
    if has_artwork:
        if not artwork_media_type:
            raise VisionAnalysisError(
                "artwork_media_type is required when artwork_image_bytes is provided."
            )
        content.append(_image_block(artwork_image_bytes, artwork_media_type))

    prompt = (
        "You are an expert window graphics designer reviewing a site photo for "
        "rendering production.\n\n"
        "Tasks:\n"
        "1. Describe the window/storefront context (frame count, material, lighting).\n"
        "2. Propose 2–3 design alternatives based on the brief"
        f"{' and artwork reference' if has_artwork else ''}.\n"
        "3. Decide status:\n"
        "   - APPROVED_INTERNAL: sufficient for internal designer handoff\n"
        "   - READY_FOR_REVIEW: needs designer review before client/external use\n"
        "   - LOW_CONFIDENCE: image quality or context insufficient\n\n"
        f"Design brief:\n{design_brief.strip() or '(none provided)'}\n\n"
        f"Call the {_RENDERING_TOOL} tool with structured output."
    )

    tool = {
        "name": _RENDERING_TOOL,
        "description": "Structured rendering assessment for designer workflow.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": sorted(_RENDERING_STATUSES),
                },
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
                "details": {
                    "type": "object",
                    "properties": {
                        "window_type": {"type": "string"},
                        "design_alternatives": {"type": "string"},
                        "color_palette": {"type": "string"},
                        "notes": {"type": "string"},
                    },
                    "required": [
                        "window_type",
                        "design_alternatives",
                        "color_palette",
                        "notes",
                    ],
                },
            },
            "required": ["status", "confidence", "reasoning", "details"],
        },
    }

    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        return _normalize_base(
            raw,
            allowed_statuses=_RENDERING_STATUSES,
            details_keys=(
                "window_type",
                "design_alternatives",
                "color_palette",
                "notes",
            ),
        )

    return _call_vision_tool(
        tool_name=_RENDERING_TOOL,
        tool_schema=tool,
        content_blocks=content,
        prompt=prompt,
        normalize=normalize,
    )


_MOCKUP_TOOL = "report_mockup_analysis"
_MOCKUP_STATUSES = {"READY_FOR_EXTERNAL_SHARE", "NEEDS_REVISION", "LOW_CONFIDENCE"}


def analyze_mockup(
    *,
    site_image_bytes: bytes,
    site_media_type: str,
    artwork_image_bytes: bytes,
    artwork_media_type: str,
    brief: str = "",
) -> dict[str, Any]:
    """Assess whether a site photo + artwork composite is client-ready."""
    content = [
        _image_block(site_image_bytes, site_media_type),
        _image_block(artwork_image_bytes, artwork_media_type),
    ]
    prompt = (
        "You are reviewing a window graphics mock-up composed from a site photo "
        "and artwork overlay.\n\n"
        "Evaluate alignment, scale, readability, and brand consistency.\n"
        "Status meanings:\n"
        "  READY_FOR_EXTERNAL_SHARE — polished enough to share with client\n"
        "  NEEDS_REVISION — visible issues; designer must revise\n"
        "  LOW_CONFIDENCE — cannot judge reliably\n\n"
        f"Brief:\n{brief.strip() or '(none provided)'}\n\n"
        f"Call the {_MOCKUP_TOOL} tool."
    )
    tool = {
        "name": _MOCKUP_TOOL,
        "description": "Mock-up readiness assessment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": sorted(_MOCKUP_STATUSES)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
                "details": {
                    "type": "object",
                    "properties": {
                        "alignment_notes": {"type": "string"},
                        "scale_assessment": {"type": "string"},
                        "revision_items": {"type": "string"},
                    },
                    "required": [
                        "alignment_notes",
                        "scale_assessment",
                        "revision_items",
                    ],
                },
            },
            "required": ["status", "confidence", "reasoning", "details"],
        },
    }

    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        return _normalize_base(
            raw,
            allowed_statuses=_MOCKUP_STATUSES,
            details_keys=("alignment_notes", "scale_assessment", "revision_items"),
        )

    return _call_vision_tool(
        tool_name=_MOCKUP_TOOL,
        tool_schema=tool,
        content_blocks=content,
        prompt=prompt,
        normalize=normalize,
    )


_PHOTO_TOOL = "report_photo_analysis"
_PHOTO_STATUSES = {"ANALYZED", "ISSUES_FOUND", "LOW_CONFIDENCE"}


def analyze_survey_photo(
    *,
    survey_image_bytes: bytes,
    survey_media_type: str,
    context: str = "",
) -> dict[str, Any]:
    """Analyze a survey/site photo for branding and installation context."""
    content = [_image_block(survey_image_bytes, survey_media_type)]
    prompt = (
        "You are analyzing a survey photograph for a window graphics installation project.\n\n"
        "Detect: existing branding/signage, installation surface type, obstacles, "
        "and suggest project field values.\n"
        "Status:\n"
        "  ANALYZED — clear findings\n"
        "  ISSUES_FOUND — problems (access, damage, conflicting branding)\n"
        "  LOW_CONFIDENCE — image unusable\n\n"
        f"Context:\n{context.strip() or '(none provided)'}\n\n"
        f"Call the {_PHOTO_TOOL} tool."
    )
    tool = {
        "name": _PHOTO_TOOL,
        "description": "Survey photo field extraction.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": sorted(_PHOTO_STATUSES)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
                "details": {
                    "type": "object",
                    "properties": {
                        "branding_detected": {"type": "string"},
                        "installation_type": {"type": "string"},
                        "suggested_fields": {"type": "string"},
                        "issues": {"type": "string"},
                    },
                    "required": [
                        "branding_detected",
                        "installation_type",
                        "suggested_fields",
                        "issues",
                    ],
                },
            },
            "required": ["status", "confidence", "reasoning", "details"],
        },
    }

    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        return _normalize_base(
            raw,
            allowed_statuses=_PHOTO_STATUSES,
            details_keys=(
                "branding_detected",
                "installation_type",
                "suggested_fields",
                "issues",
            ),
        )

    return _call_vision_tool(
        tool_name=_PHOTO_TOOL,
        tool_schema=tool,
        content_blocks=content,
        prompt=prompt,
        normalize=normalize,
    )


_QC_TOOL = "report_installation_qc"
_QC_STATUSES = {"PASS", "FAIL", "NEEDS_REVIEW", "LOW_CONFIDENCE"}


def analyze_installation_qc(
    *,
    install_image_bytes: bytes,
    install_media_type: str,
    reference_image_bytes: bytes,
    reference_media_type: str,
    spec_notes: str = "",
) -> dict[str, Any]:
    """Compare an installation photo against an approved rendering/reference."""
    content = [
        _image_block(install_image_bytes, install_media_type),
        _image_block(reference_image_bytes, reference_media_type),
    ]
    prompt = (
        "You are performing installation quality control for window graphics.\n\n"
        "Compare the installation photo (first image) against the approved "
        "reference/rendering (second image).\n"
        "Check: alignment, bubbles/wrinkles, seams, wrong window selection, "
        "color match, trim.\n"
        "Status:\n"
        "  PASS — meets spec\n"
        "  FAIL — clear defect\n"
        "  NEEDS_REVIEW — ambiguous; human QC required\n"
        "  LOW_CONFIDENCE — cannot compare reliably\n\n"
        f"Spec notes:\n{spec_notes.strip() or '(none provided)'}\n\n"
        f"Call the {_QC_TOOL} tool."
    )
    tool = {
        "name": _QC_TOOL,
        "description": "Installation QC comparison result.",
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {"type": "string", "enum": sorted(_QC_STATUSES)},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                "reasoning": {"type": "string"},
                "details": {
                    "type": "object",
                    "properties": {
                        "defects": {"type": "string"},
                        "alignment_score": {"type": "string"},
                        "recommendation": {"type": "string"},
                    },
                    "required": ["defects", "alignment_score", "recommendation"],
                },
            },
            "required": ["status", "confidence", "reasoning", "details"],
        },
    }

    def normalize(raw: dict[str, Any]) -> dict[str, Any]:
        return _normalize_base(
            raw,
            allowed_statuses=_QC_STATUSES,
            details_keys=("defects", "alignment_score", "recommendation"),
        )

    return _call_vision_tool(
        tool_name=_QC_TOOL,
        tool_schema=tool,
        content_blocks=content,
        prompt=prompt,
        normalize=normalize,
    )


__all__ = [
    "VisionAnalysisError",
    "VisionConfigError",
    "analyze_installation_qc",
    "analyze_mockup",
    "analyze_rendering",
    "analyze_survey_photo",
]
