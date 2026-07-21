"""Tests for the LLM-powered Intake & Classification Agent."""

from datetime import datetime, timezone
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from agents.intake_classification_agent import IntakeClassificationAgent
from backend.main import app
from backend.routes import intake_agent, intake_webhook
from integrations.classification_client import (
    ClassificationConfigError,
    get_anthropic_client,
)
from models.task import IntakeSubmission
from persistence import Database, Persistence


def _submission(text: str = "We need a new sign installed next month.") -> IntakeSubmission:
    """Build a deterministic intake task for agent tests."""
    return IntakeSubmission(
        submission_id="INT-TEST-1",
        submitted_by="client@example.com",
        text=text,
        submitted_at=datetime(2026, 7, 17, tzinfo=timezone.utc),
    )


def _anthropic_client_with_result(
    category: str,
    confidence: float,
    reasoning: str,
) -> MagicMock:
    """Build a fake Anthropic client returning one structured tool block."""
    client = MagicMock()
    client.messages.create.return_value = SimpleNamespace(
        content=[
            SimpleNamespace(
                type="tool_use",
                name="report_intake_classification",
                input={
                    "category": category,
                    "confidence": confidence,
                    "reasoning": reasoning,
                },
            )
        ]
    )
    return client


def test_high_confidence_new_project_is_auto_processed() -> None:
    """High-confidence, non-support classifications do not require review."""
    client = _anthropic_client_with_result(
        "new_project",
        0.93,
        "The client describes a new installation and timeline.",
    )
    with patch(
        "integrations.classification_client.get_anthropic_client",
        return_value=client,
    ):
        result = IntakeClassificationAgent().execute(_submission())

    assert result.data == {
        "submission_id": "INT-TEST-1",
        "category": "new_project",
        "submitted_by": "client@example.com",
    }
    assert result.confidence == 0.93
    assert result.requires_approval is False
    assert "Classified as 'new_project' (confidence: 0.93)" in result.reasoning
    call_kwargs = client.messages.create.call_args.kwargs
    assert call_kwargs["model"] == "claude-sonnet-4-5"
    assert call_kwargs["tool_choice"] == {
        "type": "tool",
        "name": "report_intake_classification",
    }


def test_support_issue_always_requires_approval() -> None:
    """Support issues require human eyes even at high confidence."""
    client = _anthropic_client_with_result(
        "support_issue",
        0.97,
        "The client reports damaged existing work.",
    )
    with patch(
        "integrations.classification_client.get_anthropic_client",
        return_value=client,
    ):
        result = IntakeClassificationAgent().execute(_submission())

    assert result.confidence == 0.97
    assert result.requires_approval is True


def test_low_confidence_classification_requires_approval() -> None:
    """Ambiguous classifications below 0.75 are routed for review."""
    client = _anthropic_client_with_result(
        "quote_request",
        0.5,
        "The inquiry mixes new-project and pricing intent.",
    )
    with patch(
        "integrations.classification_client.get_anthropic_client",
        return_value=client,
    ):
        result = IntakeClassificationAgent().execute(_submission())

    assert result.confidence == 0.5
    assert result.requires_approval is True


def test_api_failure_returns_manual_review_result() -> None:
    """A Claude failure does not crash the batch."""
    client = MagicMock()
    client.messages.create.side_effect = TimeoutError("request timed out")
    with patch(
        "integrations.classification_client.get_anthropic_client",
        return_value=client,
    ):
        result = IntakeClassificationAgent().execute(_submission())

    assert result.data["category"] == "unclassified"
    assert result.confidence == 0.0
    assert result.requires_approval is True
    assert "needs manual review" in result.reasoning


def test_missing_anthropic_api_key_raises_config_error() -> None:
    """Missing credentials fail with the classification-specific error."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ClassificationConfigError, match="ANTHROPIC_API_KEY"):
            get_anthropic_client()


def test_dashboard_endpoint_persists_and_queues_202(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Dashboard input is accepted durably without calling Claude inline."""
    store = Persistence(Database("", sqlite_path=tmp_path / "dashboard.db"))
    classifier = MagicMock()
    monkeypatch.setattr(intake_agent, "get_persistence", lambda: store)

    with patch(
        "integrations.classification_client.get_anthropic_client",
        classifier,
    ):
        response = TestClient(app).post(
            "/api/intake-agent/classify",
            json={
                "submission_id": "dashboard-1",
                "submitted_by": "client@example.com",
                "text": "Are you open on Saturdays?",
            },
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "classification_queued"
    assert payload["replay"] is False
    assert payload["status_url"].endswith(payload["submission_id"])
    assert len(store.jobs.list_for_submission(payload["submission_id"])) == 1
    classifier.assert_not_called()


def test_signed_webhook_endpoint_persists_and_queues_202(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Webhook input requires HMAC and is accepted without inline Claude."""
    store = Persistence(Database("", sqlite_path=tmp_path / "webhook.db"))
    secret = "test-webhook-secret"
    monkeypatch.setenv("INTAKE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(intake_webhook, "get_persistence", lambda: store)
    raw = json.dumps(
        {
            "submitted_by": "client@example.com",
            "text": "Are you open on Saturdays?",
        },
        separators=(",", ":"),
    ).encode()
    timestamp = str(int(time.time()))
    source, delivery_id = "website", "delivery-1"
    signature = hmac.new(
        secret.encode(),
        f"{timestamp}\n{source}\n{delivery_id}\n".encode() + raw,
        hashlib.sha256,
    ).hexdigest()
    headers = {
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Source": source,
        "X-Webhook-Delivery-ID": delivery_id,
        "X-Webhook-Signature": f"sha256={signature}",
        "Content-Type": "application/json",
    }
    classifier = MagicMock()

    with patch(
        "integrations.classification_client.get_anthropic_client",
        classifier,
    ):
        response = TestClient(app).post(
            "/api/webhooks/intake",
            content=raw,
            headers=headers,
        )

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "classification_queued"
    assert payload["replay"] is False
    assert len(store.jobs.list_for_submission(payload["submission_id"])) == 1
    classifier.assert_not_called()
