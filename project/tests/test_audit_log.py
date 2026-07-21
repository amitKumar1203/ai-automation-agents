"""Tests for the SQLite-backed audit log."""

import uuid

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from models.agent_result import AgentResult
from supervisor.audit_log import (
    clear_audit_log,
    get_audit_log,
    log_execution,
    update_approval_status,
)


def _sample_result(*, confidence: float = 1.0) -> AgentResult:
    return AgentResult(
        data={"project_id": "PRJ-1", "status": "MATCH"},
        confidence=confidence,
        requires_approval=False,
        reasoning="test reasoning",
    )


def test_log_execution_returns_valid_entry_id() -> None:
    """log_execution should return a UUID string entry id."""
    entry_id = log_execution("artwork_verification", "PRJ-1", _sample_result(), False)

    uuid.UUID(entry_id)
    entries = get_audit_log()
    assert len(entries) == 1
    assert entries[0]["id"] == entry_id


def test_get_audit_log_shape_and_pending_status() -> None:
    """New entries should match the public dict shape with PENDING approval."""
    log_execution("po_automation", "PRJ-2", _sample_result(), True)
    entry = get_audit_log()[0]

    assert set(entry.keys()) >= {
        "id",
        "agent_name",
        "task_id",
        "timestamp",
        "result",
        "final_approval_needed",
        "approval_status",
        "approved_by",
        "approved_at",
    }
    assert entry["agent_name"] == "po_automation"
    assert entry["task_id"] == "PRJ-2"
    assert entry["result"]["data"]["project_id"] == "PRJ-1"
    assert entry["result"]["confidence"] == 1.0
    assert entry["result"]["reasoning"] == "test reasoning"
    assert entry["final_approval_needed"] is True
    assert entry["approval_status"] == "PENDING"
    assert entry["approved_by"] is None
    assert entry["approved_at"] is None


def test_get_audit_log_newest_first() -> None:
    """Entries should be ordered most recent first."""
    first_id = log_execution("a", "T1", _sample_result(), False)
    second_id = log_execution("b", "T2", _sample_result(), False)

    entries = get_audit_log()
    assert [entry["id"] for entry in entries] == [second_id, first_id]


def test_get_audit_log_pagination() -> None:
    """limit/offset should return a page without changing newest-first order."""
    from supervisor.audit_log import count_audit_log

    ids = [
        log_execution(f"agent-{i}", f"T-{i}", _sample_result(), False)
        for i in range(5)
    ]
    assert count_audit_log() == 5
    page = get_audit_log(limit=2, offset=0)
    assert [entry["id"] for entry in page] == [ids[4], ids[3]]
    page2 = get_audit_log(limit=2, offset=2)
    assert [entry["id"] for entry in page2] == [ids[2], ids[1]]


def test_api_audit_log_pagination() -> None:
    """GET /api/audit-log should return a paginated payload."""
    for i in range(3):
        log_execution("po_automation", f"PAGE-{i}", _sample_result(), False)
    client = TestClient(app)

    response = client.get("/api/audit-log?limit=2&offset=0&status=all")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["limit"] == 2
    assert body["offset"] == 0
    assert body["next_offset"] == 2
    assert len(body["items"]) == 2

    page2 = client.get("/api/audit-log?limit=2&offset=2&status=all").json()
    assert page2["next_offset"] is None
    assert len(page2["items"]) == 1
    assert page2["items"][0]["task_id"] == "PAGE-0"


def test_get_audit_log_prioritize_pending() -> None:
    """Pending approvals should sort before auto/decided entries."""
    auto_id = log_execution("a", "AUTO", _sample_result(), False)
    pending_old = log_execution("b", "PEND-OLD", _sample_result(), True)
    pending_new = log_execution("c", "PEND-NEW", _sample_result(), True)
    decided = log_execution("d", "DECIDED", _sample_result(), True)
    update_approval_status(decided, "APPROVED", "reviewer")

    ordered = get_audit_log(prioritize_pending=True)
    assert [e["id"] for e in ordered] == [
        pending_new,
        pending_old,
        decided,
        auto_id,
    ]

    client = TestClient(app)
    items = client.get("/api/audit-log?limit=10&offset=0&status=all").json()["items"]
    assert [e["task_id"] for e in items] == [
        "PEND-NEW",
        "PEND-OLD",
        "DECIDED",
        "AUTO",
    ]


def test_clear_audit_log_empties_table() -> None:
    """clear_audit_log should remove all rows but leave the table usable."""
    log_execution("email_reply_monitoring", "T-1", _sample_result(), False)
    assert len(get_audit_log()) == 1

    clear_audit_log()
    assert get_audit_log() == []

    log_execution("email_reply_monitoring", "T-2", _sample_result(), False)
    assert len(get_audit_log()) == 1


def test_approve_pending_entry() -> None:
    """Approving a PENDING entry should set APPROVED fields."""
    entry_id = log_execution("po_automation", "PRJ-A", _sample_result(), True)

    updated = update_approval_status(entry_id, "APPROVED", "amit")

    assert updated is not None
    assert updated["approval_status"] == "APPROVED"
    assert updated["approved_by"] == "amit"
    assert updated["approved_at"] is not None
    assert get_audit_log()[0]["approval_status"] == "APPROVED"


def test_reject_pending_entry() -> None:
    """Rejecting a PENDING entry should set REJECTED fields."""
    entry_id = log_execution("artwork_verification", "PRJ-B", _sample_result(), True)

    updated = update_approval_status(entry_id, "REJECTED", "reviewer-1")

    assert updated is not None
    assert updated["approval_status"] == "REJECTED"
    assert updated["approved_by"] == "reviewer-1"
    assert updated["approved_at"] is not None


def test_approve_already_approved_returns_none() -> None:
    """Re-approving a decided entry should fail cleanly."""
    entry_id = log_execution("po_automation", "PRJ-C", _sample_result(), True)
    assert update_approval_status(entry_id, "APPROVED", "amit") is not None
    assert update_approval_status(entry_id, "APPROVED", "amit") is None


def test_approve_nonexistent_returns_none() -> None:
    """Unknown entry ids should return None."""
    assert update_approval_status(str(uuid.uuid4()), "APPROVED", "amit") is None


def test_invalid_status_raises_value_error() -> None:
    """Internal invalid status strings must raise ValueError."""
    entry_id = log_execution("po_automation", "PRJ-D", _sample_result(), True)
    with pytest.raises(ValueError, match="Invalid approval status"):
        update_approval_status(entry_id, "MAYBE", "amit")


def test_api_approve_success() -> None:
    """POST /approve should return the updated entry."""
    entry_id = log_execution("po_automation", "PRJ-E", _sample_result(), True)
    client = TestClient(app)

    response = client.post(
        f"/api/audit-log/{entry_id}/approve",
        json={"approved_by": "amit"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == entry_id
    assert body["approval_status"] == "APPROVED"
    assert body["approved_by"] == "amit"


def test_api_approve_already_decided_returns_409() -> None:
    """POST /approve on an already-approved entry should return 409."""
    entry_id = log_execution("po_automation", "PRJ-F", _sample_result(), True)
    client = TestClient(app)
    assert (
        client.post(
            f"/api/audit-log/{entry_id}/approve",
            json={"approved_by": "amit"},
        ).status_code
        == 200
    )

    response = client.post(
        f"/api/audit-log/{entry_id}/approve",
        json={"approved_by": "amit"},
    )
    assert response.status_code == 409


def test_api_approve_missing_entry_returns_404() -> None:
    """POST /approve for an unknown id should return 404."""
    client = TestClient(app)
    response = client.post(
        f"/api/audit-log/{uuid.uuid4()}/approve",
        json={"approved_by": "amit"},
    )
    assert response.status_code == 404


def test_api_reject_success() -> None:
    """POST /reject should mark the entry REJECTED."""
    entry_id = log_execution("vendor_followup", "PRJ-G", _sample_result(), True)
    client = TestClient(app)

    response = client.post(
        f"/api/audit-log/{entry_id}/reject",
        json={"approved_by": "ops"},
    )

    assert response.status_code == 200
    assert response.json()["approval_status"] == "REJECTED"
    assert response.json()["approved_by"] == "ops"


def test_api_approve_requires_reviewer_role(monkeypatch) -> None:
    """Operators cannot approve audit entries."""
    from backend import auth

    monkeypatch.setenv("TRUSTED_IDENTITY_SECRET", "identity-secret")
    monkeypatch.setattr(auth.time, "time", lambda: 1_700_000_001)
    entry_id = log_execution("po_automation", "PRJ-H", _sample_result(), True)
    signature = auth.sign_trusted_identity(
        "identity-secret",
        timestamp="1700000000",
        email="operator@example.com",
        role="operator",
    )
    headers = {
        "X-Principal-Email": "operator@example.com",
        "X-Principal-Role": "operator",
        "X-Principal-Timestamp": "1700000000",
        "X-Principal-Signature": signature,
    }
    client = TestClient(app)
    response = client.post(
        f"/api/audit-log/{entry_id}/approve",
        headers=headers,
        json={"approved_by": "operator@example.com"},
    )
    assert response.status_code == 403


def test_audit_log_supersedes_stale_pending_on_rerun() -> None:
    """A new run should reject older pending rows for the same task."""
    first_id = log_execution("installer_matching", "INST-1", _sample_result(), True)
    second_id = log_execution("installer_matching", "INST-1", _sample_result(), True)

    entries = get_audit_log(approval_status="REJECTED")
    superseded = [e for e in entries if e["id"] == first_id]
    assert len(superseded) == 1
    assert superseded[0]["approved_by"] == "superseded-by-rerun"

    pending = get_audit_log(pending_review_only=True)
    assert [e["id"] for e in pending] == [second_id]


def test_audit_log_status_filters_and_dedupe() -> None:
    """API tabs should filter by approval status and dedupe pending tasks."""
    log_execution("installer_matching", "INST-A", _sample_result(), True)
    log_execution("installer_matching", "INST-A", _sample_result(), True)
    approved_id = log_execution("installer_matching", "INST-B", _sample_result(), True)
    update_approval_status(approved_id, "APPROVED", "reviewer@example.com")

    client = TestClient(app)
    pending = client.get("/api/audit-log?status=pending").json()
    assert pending["total"] == 1
    assert pending["items"][0]["task_id"] == "INST-A"
    assert pending["counts"]["approved"] >= 1

    approved = client.get("/api/audit-log?status=approved").json()
    assert any(item["task_id"] == "INST-B" for item in approved["items"])
