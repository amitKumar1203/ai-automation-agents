"""Automated RBAC role matrix — maps doc expectations to API behavior."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from backend import auth
from backend.main import app
from backend.routes import admin
from models.agent_result import AgentResult
from persistence import Database, Persistence
from supervisor.audit_log import log_execution


def _sample_result() -> AgentResult:
    return AgentResult(
        data={"project_id": "PRJ-1", "status": "PO_READY_FOR_RELEASE"},
        confidence=1.0,
        requires_approval=False,
        reasoning="test",
    )


def _headers(monkeypatch: pytest.MonkeyPatch, *, email: str, role: str) -> dict[str, str]:
    monkeypatch.setenv("TRUSTED_IDENTITY_SECRET", "identity-secret")
    monkeypatch.setattr(auth.time, "time", lambda: 1_700_000_001)
    signature = auth.sign_trusted_identity(
        "identity-secret",
        timestamp="1700000000",
        email=email,
        role=role,
    )
    return {
        "X-Principal-Email": email,
        "X-Principal-Role": role,
        "X-Principal-Timestamp": "1700000000",
        "X-Principal-Signature": signature,
    }


@pytest.fixture
def rbac_client(monkeypatch: pytest.MonkeyPatch, tmp_path):
    store = Persistence(Database("", sqlite_path=tmp_path / "rbac.db"))
    store.operators.ensure("operator@example.com")
    store.operators.ensure("reviewer@example.com")
    store.operators.set_role("reviewer@example.com", "reviewer")
    store.operators.ensure("admin@example.com")
    store.operators.set_role("admin@example.com", "admin")
    monkeypatch.setattr(admin, "Persistence", lambda: store)
    monkeypatch.setattr("persistence.Persistence", lambda: store)
    return TestClient(app), store


# (role, path, method, expected_status)
READ_MATRIX = [
    ("operator", "/api/dashboard/overview", "GET", 200),
    ("operator", "/api/audit-log", "GET", 200),
    ("operator", "/api/admin/operators", "GET", 403),
    ("operator", "/api/admin/config", "GET", 403),
    ("reviewer", "/api/dashboard/overview", "GET", 200),
    ("reviewer", "/api/audit-log", "GET", 200),
    ("reviewer", "/api/admin/operators", "GET", 403),
    ("reviewer", "/api/admin/config", "GET", 403),
    ("admin", "/api/dashboard/overview", "GET", 200),
    ("admin", "/api/audit-log", "GET", 200),
    ("admin", "/api/admin/operators", "GET", 200),
    ("admin", "/api/admin/config", "GET", 200),
]


@pytest.mark.parametrize("role,path,method,expected", READ_MATRIX)
def test_read_access_matrix(
    rbac_client,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    path: str,
    method: str,
    expected: int,
) -> None:
    client, _ = rbac_client
    headers = _headers(monkeypatch, email=f"{role}@example.com", role=role)
    response = client.request(method, path, headers=headers)
    assert response.status_code == expected


def test_operator_cannot_approve_audit(rbac_client, monkeypatch) -> None:
    client, _ = rbac_client
    entry_id = log_execution("po_automation", "RBAC-1", _sample_result(), True)
    headers = _headers(monkeypatch, email="operator@example.com", role="operator")
    response = client.post(
        f"/api/audit-log/{entry_id}/approve",
        headers=headers,
        json={"approved_by": "operator@example.com"},
    )
    assert response.status_code == 403


def test_reviewer_can_approve_audit(rbac_client, monkeypatch) -> None:
    client, _ = rbac_client
    entry_id = log_execution("po_automation", "RBAC-2", _sample_result(), True)
    headers = _headers(monkeypatch, email="reviewer@example.com", role="reviewer")
    response = client.post(
        f"/api/audit-log/{entry_id}/approve",
        headers=headers,
        json={"approved_by": "reviewer@example.com"},
    )
    assert response.status_code == 200
    assert response.json()["approved_by"] == "reviewer@example.com"


def test_admin_can_update_config(rbac_client, monkeypatch) -> None:
    client, store = rbac_client
    headers = _headers(monkeypatch, email="admin@example.com", role="admin")
    response = client.put(
        "/api/admin/config/write_back_mode",
        headers=headers,
        json={"value": "dry_run"},
    )
    assert response.status_code == 200
    assert store.config.get("write_back_mode") == "dry_run"


def test_reviewer_cannot_update_config(rbac_client, monkeypatch) -> None:
    client, _ = rbac_client
    headers = _headers(monkeypatch, email="reviewer@example.com", role="reviewer")
    response = client.put(
        "/api/admin/config/write_back_mode",
        headers=headers,
        json={"value": "live"},
    )
    assert response.status_code == 403


def test_admin_can_update_operator_role(rbac_client, monkeypatch) -> None:
    client, _ = rbac_client
    headers = _headers(monkeypatch, email="admin@example.com", role="admin")
    response = client.patch(
        "/api/admin/operators/operator@example.com",
        headers=headers,
        json={"role": "reviewer"},
    )
    assert response.status_code == 200
    assert response.json()["role"] == "reviewer"


def test_cron_blocked_without_secret_in_production(monkeypatch) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("CRON_SECRET", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    client = TestClient(app)
    assert client.get("/api/cron/poll-all").status_code == 503


def test_health_is_public() -> None:
    client = TestClient(app)
    assert client.get("/").status_code == 200
    assert client.get("/").json()["status"] == "ok"
