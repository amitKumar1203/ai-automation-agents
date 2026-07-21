"""Tests for Claude vision artwork verification (mocked Anthropic API)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agents.artwork_verification_agent import ArtworkVerificationAgent
from integrations.vision_verification import (
    VisionAnalysisError,
    VisionConfigError,
    analyze_artwork_image,
    get_anthropic_client,
)
from supervisor.approval_policy import requires_human_approval

# Tiny valid-looking PNG bytes (not a real image decode — API is mocked).
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _tool_response(payload: dict[str, Any]) -> SimpleNamespace:
    """Build a fake Claude messages response with a tool_use block."""
    block = SimpleNamespace(
        type="tool_use",
        name="report_artwork_verification",
        input=payload,
    )
    return SimpleNamespace(content=[block])


def test_analyze_artwork_match_parsed() -> None:
    """Mocked MATCH response is normalized into the expected structure."""
    payload = {
        "status": "MATCH",
        "confidence": 0.91,
        "reasoning": "Labeled 48x36 and design matches the spec.",
        "details": {"dimensions_visible": True, "notes": "Clean edges"},
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(payload)

    with patch(
        "integrations.vision_verification.get_anthropic_client",
        return_value=mock_client,
    ):
        result = analyze_artwork_image(
            artwork_image_bytes=_FAKE_PNG,
            artwork_media_type="image/png",
            spec_description="48in x 36in navy logo on white",
        )

    assert result["status"] == "MATCH"
    assert result["confidence"] == 0.91
    assert "Labeled 48x36" in result["reasoning"]
    assert result["details"]["dimensions_visible"] is True
    assert result["details"]["notes"] == "Clean edges"
    mock_client.messages.create.assert_called_once()


def test_execute_vision_mismatch_requires_approval() -> None:
    """Mocked MISMATCH maps to AgentResult with requires_approval True."""
    payload = {
        "status": "MISMATCH",
        "confidence": 0.88,
        "reasoning": "Width labeled 60in vs expected 48in.",
        "details": {"dimensions_visible": True, "notes": "Wrong size"},
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(payload)

    agent = ArtworkVerificationAgent()
    with patch(
        "integrations.vision_verification.get_anthropic_client",
        return_value=mock_client,
    ):
        result = agent.execute_vision(
            artwork_image_bytes=_FAKE_PNG,
            artwork_media_type="image/png",
            spec_description="48in x 36in",
            project_id="PRJ-V1",
        )

    assert result.data["status"] == "MISMATCH"
    assert result.requires_approval is True
    assert result.confidence == 0.88
    assert result.data["project_id"] == "PRJ-V1"
    assert requires_human_approval("artwork_verification", result) is True


def test_execute_vision_uncertain_requires_approval() -> None:
    """UNCERTAIN is conservative — human review required."""
    payload = {
        "status": "UNCERTAIN",
        "confidence": 0.4,
        "reasoning": "Image is blurry; dimensions not readable.",
        "details": {"dimensions_visible": False, "notes": "Low quality photo"},
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(payload)

    agent = ArtworkVerificationAgent()
    with patch(
        "integrations.vision_verification.get_anthropic_client",
        return_value=mock_client,
    ):
        result = agent.execute_vision(
            artwork_image_bytes=_FAKE_PNG,
            artwork_media_type="image/png",
            spec_description="48in x 36in",
        )

    assert result.data["status"] == "UNCERTAIN"
    assert result.requires_approval is True
    assert result.data["dimensions_visible"] is False
    assert requires_human_approval("artwork_verification", result) is True


def test_analyze_artwork_api_failure_raises_vision_analysis_error() -> None:
    """API exceptions are wrapped as VisionAnalysisError."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("rate limit")

    with patch(
        "integrations.vision_verification.get_anthropic_client",
        return_value=mock_client,
    ):
        with pytest.raises(VisionAnalysisError, match="rate limit"):
            analyze_artwork_image(
                artwork_image_bytes=_FAKE_PNG,
                artwork_media_type="image/png",
                spec_description="any spec",
            )


def test_missing_anthropic_api_key_raises_config_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing ANTHROPIC_API_KEY raises VisionConfigError."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(VisionConfigError, match="ANTHROPIC_API_KEY"):
        get_anthropic_client()
