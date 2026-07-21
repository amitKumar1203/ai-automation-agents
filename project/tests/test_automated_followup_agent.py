"""Tests for Automated Follow-Up agent (env-driven SLA, live SF source)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from agents.automated_followup_agent import AutomatedFollowUpAgent
from models.task import ProjectActivity
from supervisor.approval_policy import requires_human_approval
from supervisor.write_back import get_followup_notify_email


NOW = datetime(2026, 7, 16, 12, 0, tzinfo=timezone.utc)


def _project(days_ago: float, **kwargs) -> ProjectActivity:
    return ProjectActivity(
        project_id=kwargs.get("project_id", "PRJ-1"),
        project_name=kwargs.get("project_name", "Demo"),
        last_activity_at=NOW - timedelta(days=days_ago),
        stage=kwargs.get("stage", "Design"),
        owner_email=kwargs.get("owner_email", ""),
    )


def test_ok_within_inactive_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLLOWUP_INACTIVE_DAYS", "7")
    monkeypatch.setenv("FOLLOWUP_ESCALATE_DAYS", "14")
    agent = AutomatedFollowUpAgent()
    result = agent.execute(_project(3), current_time=NOW)
    assert result.data["status"] == "OK"
    assert requires_human_approval("automated_followup", result) is False


def test_send_followup_after_inactive_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLLOWUP_INACTIVE_DAYS", "7")
    monkeypatch.setenv("FOLLOWUP_ESCALATE_DAYS", "14")
    agent = AutomatedFollowUpAgent()
    result = agent.execute(_project(9), current_time=NOW)
    assert result.data["status"] == "SEND_FOLLOWUP"
    assert requires_human_approval("automated_followup", result) is True


def test_escalate_after_escalate_days(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOLLOWUP_INACTIVE_DAYS", "7")
    monkeypatch.setenv("FOLLOWUP_ESCALATE_DAYS", "14")
    agent = AutomatedFollowUpAgent()
    result = agent.execute(_project(20), current_time=NOW)
    assert result.data["status"] == "ESCALATE"
    assert requires_human_approval("automated_followup", result) is True


def test_followup_notify_email_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")
    monkeypatch.setenv("FOLLOWUP_NOTIFY_EMAIL", "pm@example.com")
    assert get_followup_notify_email() == "pm@example.com"
    monkeypatch.delenv("FOLLOWUP_NOTIFY_EMAIL", raising=False)
    assert get_followup_notify_email() == "ops@example.com"


def test_followup_batch_api_uses_salesforce(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FOLLOWUP_INACTIVE_DAYS", "7")
    monkeypatch.setenv("FOLLOWUP_ESCALATE_DAYS", "14")
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")

    real_now = datetime.now(timezone.utc)
    fake = [
        ProjectActivity(
            project_id="P-1",
            project_name="Acme",
            last_activity_at=real_now - timedelta(days=10),
            stage="Design",
            owner_email="ops@example.com",
        ),
        ProjectActivity(
            project_id="P-2",
            project_name="Beta",
            last_activity_at=real_now - timedelta(days=2),
            stage="Install",
            owner_email="ops@example.com",
        ),
    ]

    import os

    from fastapi.testclient import TestClient

    from backend.main import app

    headers = {}
    key = (os.getenv("API_KEY") or "").strip()
    if key:
        headers["X-API-Key"] = key

    with patch(
        "backend.services.agent_runs.get_project_activities",
        return_value=fake,
    ), patch(
        "backend.services.agent_runs.save_kpi_snapshot",
        lambda *args, **kwargs: None,
    ):
        client = TestClient(app)
        response = client.get(
            "/api/followup-agent/run?source=salesforce",
            headers=headers,
        )
    assert response.status_code == 200
    body = response.json()
    assert body["total_projects"] == 2
    assert body["followup_count"] >= 1
    assert body["ok_count"] >= 1
