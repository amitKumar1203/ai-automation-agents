"""Tests for webhooks, cron, owner notify, and Monday PO dry-run sync."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.main import app
from backend.services.owner_notify import notify_unanswered_threads
from models.agent_result import AgentResult
from supervisor.action_executor import execute_approved_action
from supervisor.audit_log import log_execution


def test_cron_poll_all_without_secret(monkeypatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setattr(
        "backend.routes.cron.enqueue_event",
        lambda event_source, trigger="cron": {
            "ok": True,
            "event_source": event_source,
            "enqueued": 1,
            "jobs": [],
        },
    )
    monkeypatch.setattr(
        "backend.routes.cron.drain_agent_jobs",
        lambda limit=20: {"ok": True, "claimed": 1, "succeeded": 1},
    )
    monkeypatch.setattr(
        "backend.routes.cron.escalate_stale_pending",
        lambda: {"ok": True, "escalated_count": 0},
    )
    client = TestClient(app)
    response = client.get("/api/cron/poll-all")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["enqueue"]["enqueued"] == 1
    assert body["drain"]["succeeded"] == 1


def test_cron_requires_secret_in_production(monkeypatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    client = TestClient(app)
    response = client.get("/api/cron/poll-all")
    assert response.status_code == 503


def test_webhook_requires_secret_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("CRON_SECRET", "secret-123")
    client = TestClient(app)
    denied = client.post("/api/webhooks/monday")
    assert denied.status_code == 401

    monkeypatch.setattr(
        "backend.routes.webhooks.enqueue_event",
        lambda event_source, trigger="webhook": {
            "ok": True,
            "event_source": event_source,
            "enqueued": 2,
            "routed": [
                {"job_type": "poll_vendor", "agent_name": "vendor_followup"},
            ],
            "jobs": [],
        },
    )
    monkeypatch.setattr(
        "backend.routes.webhooks.drain_agent_jobs",
        lambda limit=10: {"ok": True, "claimed": 0, "succeeded": 0},
    )
    ok = client.post(
        "/api/webhooks/monday",
        headers={"X-Cron-Secret": "secret-123"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["event_source"] == "monday"
    assert body["enqueue"]["enqueued"] == 2


def test_owner_notify_dry_run(monkeypatch) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")
    outcome = notify_unanswered_threads(
        [{"thread_id": "T1", "hours_pending": 30, "last_message_text": "hi"}]
    )
    assert outcome["execution_status"] == "DRY_RUN"


def test_po_dry_run_includes_monday_sync(monkeypatch) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    sync = MagicMock()
    outcome = execute_approved_action(
        {
            "agent_name": "po_automation",
            "result": {
                "data": {
                    "status": "PO_READY_FOR_RELEASE",
                    "project_id": "PRJ-9",
                    "draft_po": {"project_id": "PRJ-9"},
                }
            },
        },
        sync_monday_po=sync,
    )
    assert outcome["execution_status"] == "DRY_RUN"
    detail = json.loads(outcome["execution_detail"])
    assert detail["monday_po_sync"] is True
    sync.assert_not_called()


def test_po_live_calls_monday_sync(monkeypatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.delenv("SALESFORCE_PO_OBJECT", raising=False)
    create = MagicMock()
    update = MagicMock(return_value={"success": True})
    sync = MagicMock(return_value={"item_id": "1", "po_number": "PO-PRJ-9"})

    outcome = execute_approved_action(
        {
            "agent_name": "po_automation",
            "result": {
                "data": {
                    "status": "PO_READY_FOR_RELEASE",
                    "project_id": "PRJ-9",
                    "salesforce_id": "a00x",
                    "draft_po": {"project_id": "PRJ-9", "estimated_amount": 10},
                }
            },
        },
        create_salesforce_record=create,
        update_salesforce_record=update,
        sync_monday_po=sync,
    )
    assert outcome["execution_status"] == "SUCCESS"
    sync.assert_called_once()
    assert sync.call_args.kwargs["project_id"] == "PRJ-9"


def test_agent_routes_require_api_key(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "key-abc")
    client = TestClient(app)
    denied = client.get("/api/email-agent/run?source=mock")
    assert denied.status_code == 401
    assert denied.json()["detail"] == "Unauthorized"

    ok = client.get(
        "/api/email-agent/run?source=mock",
        headers={"X-API-Key": "key-abc"},
    )
    assert ok.status_code == 200


def test_health_stays_public(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "key-abc")
    client = TestClient(app)
    assert client.get("/").status_code == 200


def test_approve_requires_api_key_when_set(monkeypatch) -> None:
    monkeypatch.setenv("API_KEY", "key-abc")
    entry_id = log_execution(
        "vendor_followup",
        "P1",
        AgentResult(
            data={"status": "SEND_REMINDER", "vendor_name": "V", "project_id": "P1"},
            confidence=1.0,
            requires_approval=True,
            reasoning="r",
        ),
        True,
    )
    client = TestClient(app)
    denied = client.post(
        f"/api/audit-log/{entry_id}/approve",
        json={"approved_by": "amit"},
    )
    assert denied.status_code == 401

    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    ok = client.post(
        f"/api/audit-log/{entry_id}/approve",
        json={"approved_by": "amit"},
        headers={"X-API-Key": "key-abc"},
    )
    assert ok.status_code == 200
