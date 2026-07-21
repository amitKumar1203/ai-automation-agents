"""Tests for post-approval action executor and write-back wiring."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from backend.main import app
from models.agent_result import AgentResult
from supervisor.action_executor import execute_approved_action
from supervisor.audit_log import get_audit_entry, log_execution


def _entry(
    agent_name: str,
    data: dict,
    *,
    execution_status: str | None = None,
) -> dict:
    return {
        "id": "test-id",
        "agent_name": agent_name,
        "task_id": "T-1",
        "result": {"data": data, "confidence": 1.0, "reasoning": "r"},
        "execution_status": execution_status,
        "execution_detail": None,
    }


def test_vendor_dry_run_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")
    send = MagicMock()
    monday = MagicMock()

    outcome = execute_approved_action(
        _entry(
            "vendor_followup",
            {
                "status": "SEND_REMINDER",
                "vendor_name": "Acme",
                "project_id": "P1",
                "hours_pending": 50,
                "monday_item_id": "123",
            },
        ),
        send_email=send,
        update_monday_column=monday,
    )

    assert outcome["execution_status"] == "DRY_RUN"
    send.assert_not_called()
    monday.assert_not_called()
    detail = json.loads(outcome["execution_detail"])
    assert detail["action"] == "SEND_REMINDER"


def test_vendor_live_sends_email_and_escalates_monday(monkeypatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")
    send = MagicMock(return_value={"id": "m1"})
    monday = MagicMock(return_value={"changed_item_id": "123"})

    outcome = execute_approved_action(
        _entry(
            "vendor_followup",
            {
                "status": "ESCALATE",
                "vendor_name": "Acme",
                "project_id": "P1",
                "hours_pending": 100,
                "monday_item_id": "123",
            },
        ),
        send_email=send,
        update_monday_column=monday,
    )

    assert outcome["execution_status"] == "SUCCESS"
    send.assert_called_once()
    monday.assert_called_once()
    assert monday.call_args.kwargs["label"] == "Escalate"
    kwargs = send.call_args.kwargs
    assert "Vendor Escalation" in kwargs["subject"]
    assert "Vendor Agent" in kwargs["body_html"]
    assert "Acme" in kwargs["body_text"]


def test_artwork_live_sends_branded_html_email(monkeypatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")
    send = MagicMock(return_value={"id": "m-artwork"})

    outcome = execute_approved_action(
        _entry(
            "artwork_verification",
            {
                "status": "MISMATCH",
                "project_id": "ART-1",
                "artwork_width_inches": 48,
                "artwork_height_inches": 36,
                "spec_width_inches": 48,
                "spec_height_inches": 32,
            },
        ),
        send_email=send,
    )

    assert outcome["execution_status"] == "SUCCESS"
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert "Artwork review needed" in kwargs["subject"]
    assert "Artwork Agent" in kwargs["body_html"]
    assert "48 × 36" in kwargs["body_html"]


def test_followup_live_sends_branded_html_email(monkeypatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.setenv("FOLLOWUP_NOTIFY_EMAIL", "ops@example.com")
    monkeypatch.setenv("DASHBOARD_URL", "https://console.example.com/audit-log")
    send = MagicMock(return_value={"id": "m-followup"})

    outcome = execute_approved_action(
        _entry(
            "automated_followup",
            {
                "status": "SEND_FOLLOWUP",
                "project_id": "P-203",
                "project_name": "Delta Infra",
                "stage": "Approved",
                "days_inactive": 12.2,
            },
        ),
        send_email=send,
    )

    assert outcome["execution_status"] == "SUCCESS"
    send.assert_called_once()
    kwargs = send.call_args.kwargs
    assert kwargs["subject"] == "Action required: Delta Infra · P-203"
    assert "Project Follow-Up" in kwargs["body_html"]
    assert "Review in Ops Console" in kwargs["body_html"]
    assert "https://console.example.com/audit-log" in kwargs["body_html"]
    assert "Delta Infra" in kwargs["body_text"]


def test_po_dry_run_includes_draft(monkeypatch) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    create = MagicMock()
    update = MagicMock()

    outcome = execute_approved_action(
        _entry(
            "po_automation",
            {
                "status": "PO_READY_FOR_RELEASE",
                "project_id": "PRJ-1",
                "client_name": "Client",
                "salesforce_id": "a00xx",
                "draft_po": {
                    "project_id": "PRJ-1",
                    "client_name": "Client",
                    "vendor_name": "V",
                    "estimated_amount": 1000.0,
                },
            },
        ),
        create_salesforce_record=create,
        update_salesforce_record=update,
    )

    assert outcome["execution_status"] == "DRY_RUN"
    create.assert_not_called()
    update.assert_not_called()


def test_po_live_marks_po_exists(monkeypatch) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.delenv("SALESFORCE_PO_OBJECT", raising=False)
    create = MagicMock()
    update = MagicMock(return_value={"success": True})
    sync = MagicMock(return_value={"skipped": True})

    outcome = execute_approved_action(
        _entry(
            "po_automation",
            {
                "status": "PO_READY_FOR_RELEASE",
                "project_id": "PRJ-1",
                "salesforce_id": "a00xx",
                "draft_po": {"project_id": "PRJ-1", "estimated_amount": 10},
            },
        ),
        create_salesforce_record=create,
        update_salesforce_record=update,
        sync_monday_po=sync,
    )

    assert outcome["execution_status"] == "SUCCESS"
    create.assert_not_called()
    update.assert_called_once_with(
        "Approved_Project__c",
        "a00xx",
        {"PO_Exists__c": True},
    )
    sync.assert_called_once()


def test_idempotent_skip_when_already_executed() -> None:
    outcome = execute_approved_action(
        _entry(
            "vendor_followup",
            {"status": "SEND_REMINDER"},
            execution_status="DRY_RUN",
        )
    )
    assert outcome["execution_status"] == "DRY_RUN"


def test_approve_api_persists_dry_run_execution(monkeypatch) -> None:
    monkeypatch.delenv("WRITE_BACK_MODE", raising=False)
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")

    entry_id = log_execution(
        "vendor_followup",
        "P-API",
        AgentResult(
            data={
                "status": "SEND_REMINDER",
                "vendor_name": "Acme",
                "project_id": "P-API",
                "hours_pending": 60,
            },
            confidence=1.0,
            requires_approval=True,
            reasoning="remind",
        ),
        True,
    )

    client = TestClient(app)
    response = client.post(
        f"/api/audit-log/{entry_id}/approve",
        json={"approved_by": "amit"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_status"] == "APPROVED"
    assert body["execution_status"] == "DRY_RUN"
    assert body["execution_detail"]

    stored = get_audit_entry(entry_id)
    assert stored is not None
    assert stored["execution_status"] == "DRY_RUN"


def test_dashboard_overview_endpoint() -> None:
    log_execution(
        "po_automation",
        "PRJ-OV",
        AgentResult(
            data={"status": "PO_READY_FOR_RELEASE", "project_id": "PRJ-OV"},
            confidence=1.0,
            requires_approval=True,
            reasoning="ready",
        ),
        True,
    )
    client = TestClient(app)
    response = client.get("/api/dashboard/overview")
    assert response.status_code == 200
    body = response.json()
    assert body["pending_approval_count"] >= 1
    assert "write_back_mode" in body
    assert isinstance(body["recent_entries"], list)
