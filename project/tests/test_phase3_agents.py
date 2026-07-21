"""Tests for Phase 3 vision agents (mocked Anthropic API)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from agents.ai_mockup_agent import AIMockupAgent
from agents.ai_rendering_agent import AIRenderingAgent
from agents.installation_qc_agent import InstallationQCAgent
from agents.photo_analysis_agent import PhotoAnalysisAgent
from integrations.phase3_vision import analyze_mockup, analyze_rendering
from supervisor.approval_policy import requires_human_approval
from supervisor.action_executor import execute_approved_action

_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 24


def _tool_response(tool_name: str, payload: dict[str, Any]) -> SimpleNamespace:
    block = SimpleNamespace(type="tool_use", name=tool_name, input=payload)
    return SimpleNamespace(content=[block])


def test_rendering_ready_for_review_requires_approval() -> None:
    payload = {
        "status": "READY_FOR_REVIEW",
        "confidence": 0.86,
        "reasoning": "Design needs designer polish before client use.",
        "details": {
            "window_type": "Double-hung vinyl",
            "design_alternatives": "Navy logo centered; white border variant",
            "color_palette": "Navy, white",
            "notes": "Good site context",
        },
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(
        "report_rendering_analysis", payload
    )
    agent = AIRenderingAgent()
    with patch(
        "integrations.phase3_vision.get_anthropic_client",
        return_value=mock_client,
    ):
        result = agent.execute_vision(
            site_image_bytes=_FAKE_PNG,
            site_media_type="image/png",
            design_brief="48x36 navy logo",
            project_id="P-301",
        )
    assert result.data["status"] == "READY_FOR_REVIEW"
    assert requires_human_approval("ai_rendering", result) is True


def test_mockup_external_share_requires_approval() -> None:
    payload = {
        "status": "READY_FOR_EXTERNAL_SHARE",
        "confidence": 0.9,
        "reasoning": "Composite looks client-ready.",
        "details": {
            "alignment_notes": "Centered well",
            "scale_assessment": "Proportional",
            "revision_items": "None",
        },
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(
        "report_mockup_analysis", payload
    )
    agent = AIMockupAgent()
    with patch(
        "integrations.phase3_vision.get_anthropic_client",
        return_value=mock_client,
    ):
        result = agent.execute_vision(
            site_image_bytes=_FAKE_PNG,
            site_media_type="image/png",
            artwork_image_bytes=_FAKE_PNG,
            artwork_media_type="image/png",
            project_id="P-302",
        )
    assert result.data["status"] == "READY_FOR_EXTERNAL_SHARE"
    assert requires_human_approval("ai_mockup", result) is True


def test_photo_analysis_issues_requires_approval() -> None:
    payload = {
        "status": "ISSUES_FOUND",
        "confidence": 0.82,
        "reasoning": "Conflicting legacy signage visible.",
        "details": {
            "branding_detected": "Old vinyl decal",
            "installation_type": "Interior window",
            "suggested_fields": "Remove legacy decal before install",
            "issues": "Access ladder needed",
        },
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(
        "report_photo_analysis", payload
    )
    agent = PhotoAnalysisAgent()
    with patch(
        "integrations.phase3_vision.get_anthropic_client",
        return_value=mock_client,
    ):
        result = agent.execute_vision(
            survey_image_bytes=_FAKE_PNG,
            survey_media_type="image/png",
            project_id="P-303",
        )
    assert result.data["status"] == "ISSUES_FOUND"
    assert requires_human_approval("photo_analysis", result) is True


def test_installation_qc_fail_requires_approval() -> None:
    payload = {
        "status": "FAIL",
        "confidence": 0.88,
        "reasoning": "Visible bubbles along bottom seam.",
        "details": {
            "defects": "Bubbles, misaligned bottom edge",
            "alignment_score": "Poor",
            "recommendation": "Re-install lower panel",
        },
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(
        "report_installation_qc", payload
    )
    agent = InstallationQCAgent()
    with patch(
        "integrations.phase3_vision.get_anthropic_client",
        return_value=mock_client,
    ):
        result = agent.execute_vision(
            install_image_bytes=_FAKE_PNG,
            install_media_type="image/png",
            reference_image_bytes=_FAKE_PNG,
            reference_media_type="image/png",
            project_id="P-304",
        )
    assert result.data["status"] == "FAIL"
    assert requires_human_approval("installation_qc", result) is True


def test_analyze_rendering_parses_match() -> None:
    payload = {
        "status": "APPROVED_INTERNAL",
        "confidence": 0.93,
        "reasoning": "Clear storefront, internal handoff OK.",
        "details": {
            "window_type": "Single pane",
            "design_alternatives": "Full bleed logo",
            "color_palette": "Red, white",
            "notes": "",
        },
    }
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _tool_response(
        "report_rendering_analysis", payload
    )
    with patch(
        "integrations.phase3_vision.get_anthropic_client",
        return_value=mock_client,
    ):
        result = analyze_rendering(
            site_image_bytes=_FAKE_PNG,
            site_media_type="image/png",
            design_brief="Red logo full bleed",
        )
    assert result["status"] == "APPROVED_INTERNAL"


def test_mockup_writeback_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "dry_run")
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "owner@example.com")
    outcome = execute_approved_action(
        {
            "agent_name": "ai_mockup",
            "result": {
                "data": {
                    "status": "READY_FOR_EXTERNAL_SHARE",
                    "project_id": "P-99",
                    "alignment_notes": "Good",
                    "scale_assessment": "OK",
                }
            },
        }
    )
    assert outcome["execution_status"] == "DRY_RUN"


def test_installation_qc_writeback_skipped_for_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    outcome = execute_approved_action(
        {
            "agent_name": "installation_qc",
            "result": {"data": {"status": "PASS", "project_id": "P-1"}},
        }
    )
    assert outcome["execution_status"] == "SKIPPED"
