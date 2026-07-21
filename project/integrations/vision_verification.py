"""Claude vision integration for artwork image verification.

Calls the Anthropic API directly (image input) to compare an uploaded artwork
image against a text spec and/or optional reference image. Used by the
artwork verification agent's vision path — not by the rule-based numeric path.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = _PROJECT_ROOT / ".env"

load_dotenv(ENV_PATH)

# Reasonable upper bound for vision analysis (image + tool use).
_DEFAULT_TIMEOUT_SECONDS = 90.0
_VISION_MODEL = "claude-sonnet-4-5"
_TOOL_NAME = "report_artwork_verification"

_ALLOWED_MEDIA_TYPES = frozenset(
    {"image/jpeg", "image/png", "image/gif", "image/webp"}
)


class VisionConfigError(Exception):
    """Raised when Anthropic credentials or client config are missing/invalid."""


class VisionAnalysisError(Exception):
    """Raised when the Claude vision API call fails or returns unusable output."""


def get_anthropic_client() -> Any:
    """Return an initialized Anthropic client.

    Reads ``ANTHROPIC_API_KEY`` from the environment (via dotenv).

    Returns:
        An ``anthropic.Anthropic`` client instance.

    Raises:
        VisionConfigError: If ``ANTHROPIC_API_KEY`` is missing or empty.
    """
    api_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        raise VisionConfigError(
            "ANTHROPIC_API_KEY is not set. Add it to project/.env to use "
            "vision-based artwork verification."
        )

    try:
        import anthropic
    except ImportError as exc:
        raise VisionConfigError(
            "The 'anthropic' package is not installed. "
            "Run: pip install anthropic"
        ) from exc

    return anthropic.Anthropic(api_key=api_key, timeout=_DEFAULT_TIMEOUT_SECONDS)


def _normalize_media_type(media_type: str) -> str:
    """Normalize and validate an image media type for the Claude API."""
    normalized = (media_type or "").strip().lower().split(";")[0].strip()
    if normalized == "image/jpg":
        normalized = "image/jpeg"
    if normalized not in _ALLOWED_MEDIA_TYPES:
        raise VisionAnalysisError(
            f"Unsupported image media type '{media_type}'. "
            f"Allowed: {', '.join(sorted(_ALLOWED_MEDIA_TYPES))}"
        )
    return normalized


def _image_block(image_bytes: bytes, media_type: str) -> dict[str, Any]:
    """Build a Claude API image content block from raw bytes."""
    if not image_bytes:
        raise VisionAnalysisError("Image bytes are empty.")
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _normalize_media_type(media_type),
            "data": base64.standard_b64encode(image_bytes).decode("ascii"),
        },
    }


def _verification_tool() -> dict[str, Any]:
    """Tool schema forcing structured MATCH / MISMATCH / UNCERTAIN output."""
    return {
        "name": _TOOL_NAME,
        "description": (
            "Report the artwork verification outcome as structured fields. "
            "Be conservative: if image quality, labeling, or missing context "
            "makes the comparison unreliable, use UNCERTAIN rather than guessing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["MATCH", "MISMATCH", "UNCERTAIN"],
                    "description": (
                        "MATCH if the artwork clearly meets the spec; "
                        "MISMATCH if there is a clear problem; "
                        "UNCERTAIN if evidence is insufficient."
                    ),
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "Confidence in the status judgment (0.0–1.0).",
                },
                "reasoning": {
                    "type": "string",
                    "description": "Clear explanation of the judgment.",
                },
                "details": {
                    "type": "object",
                    "properties": {
                        "dimensions_visible": {
                            "type": "boolean",
                            "description": (
                                "True if width/height labels or measurable "
                                "dimensions are visible in the artwork image."
                            ),
                        },
                        "notes": {
                            "type": "string",
                            "description": "Extra notes on design, color, or quality.",
                        },
                    },
                    "required": ["dimensions_visible", "notes"],
                },
            },
            "required": ["status", "confidence", "reasoning", "details"],
        },
    }


def _build_prompt(spec_description: str, has_spec_image: bool) -> str:
    """Build the user prompt for vision artwork verification."""
    spec_image_note = (
        "A reference spec image is also attached — compare the artwork against it "
        "as well as the text description."
        if has_spec_image
        else "No reference spec image was provided — rely on the text description."
    )
    return (
        "You are verifying storefront/window artwork for a production workflow.\n\n"
        "Tasks:\n"
        "1. Describe what you see in the artwork image (any labeled or visible "
        "dimensions, and general design elements).\n"
        "2. Compare against the provided specification description"
        f"{' and the reference image' if has_spec_image else ''}.\n"
        "3. Decide MATCH, MISMATCH, or UNCERTAIN, and explain why.\n"
        "4. Assign a confidence score. Be conservative: if quality or labeling "
        "makes it hard to tell, choose UNCERTAIN and say so rather than guessing.\n\n"
        f"Specification description:\n{spec_description.strip() or '(none provided)'}\n\n"
        f"{spec_image_note}\n\n"
        f"Call the {_TOOL_NAME} tool with your final structured result."
    )


def _extract_tool_result(response: Any) -> dict[str, Any]:
    """Pull structured tool input from a Claude messages response."""
    for block in getattr(response, "content", []) or []:
        block_type = getattr(block, "type", None)
        if block_type == "tool_use" and getattr(block, "name", None) == _TOOL_NAME:
            tool_input = getattr(block, "input", None)
            if isinstance(tool_input, dict):
                return tool_input
    raise VisionAnalysisError(
        "Claude did not return a structured artwork verification result."
    )


def _normalize_analysis_result(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize the tool payload into the public result shape."""
    status = str(raw.get("status", "")).upper().strip()
    if status not in {"MATCH", "MISMATCH", "UNCERTAIN"}:
        raise VisionAnalysisError(
            f"Unexpected vision status '{raw.get('status')}'. "
            "Expected MATCH, MISMATCH, or UNCERTAIN."
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

    dimensions_visible = bool(details_raw.get("dimensions_visible", False))
    notes = str(details_raw.get("notes") or "").strip()

    return {
        "status": status,
        "confidence": confidence,
        "reasoning": reasoning,
        "details": {
            "dimensions_visible": dimensions_visible,
            "notes": notes,
        },
    }


def analyze_artwork_image(
    artwork_image_bytes: bytes,
    artwork_media_type: str,
    spec_description: str,
    spec_image_bytes: Optional[bytes] = None,
    spec_media_type: Optional[str] = None,
) -> dict:
    """Analyze an artwork image against a text spec and optional reference image.

    Args:
        artwork_image_bytes: Raw bytes of the submitted artwork image.
        artwork_media_type: MIME type of the artwork image (e.g. ``image/png``).
        spec_description: Human-readable specification (dimensions, design notes).
        spec_image_bytes: Optional raw bytes of a reference/spec image.
        spec_media_type: MIME type of the optional spec image.

    Returns:
        Dict with keys ``status``, ``confidence``, ``reasoning``, and ``details``
        (``dimensions_visible``, ``notes``).

    Raises:
        VisionConfigError: If the Anthropic client cannot be configured.
        VisionAnalysisError: On API failures, invalid images, or bad responses.
    """
    client = get_anthropic_client()

    content: list[dict[str, Any]] = [
        _image_block(artwork_image_bytes, artwork_media_type),
    ]

    has_spec_image = bool(spec_image_bytes)
    if has_spec_image:
        if not spec_media_type:
            raise VisionAnalysisError(
                "spec_media_type is required when spec_image_bytes is provided."
            )
        content.append(_image_block(spec_image_bytes, spec_media_type))

    content.append(
        {
            "type": "text",
            "text": _build_prompt(spec_description, has_spec_image=has_spec_image),
        }
    )

    try:
        response = client.messages.create(
            model=_VISION_MODEL,
            max_tokens=1024,
            tools=[_verification_tool()],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
            messages=[{"role": "user", "content": content}],
        )
    except VisionAnalysisError:
        raise
    except Exception as exc:
        raise VisionAnalysisError(
            f"Claude vision analysis failed: {exc}"
        ) from exc

    return _normalize_analysis_result(_extract_tool_result(response))
