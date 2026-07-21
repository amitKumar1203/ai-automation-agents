"""Tests for admin operator management and config endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import auth
from backend.routes import admin
from persistence import Database, Persistence


def _principal_headers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    email: str,
    role: str,
) -> dict[str, str]:
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
def admin_client(monkeypatch: pytest.MonkeyPatch, tmp_path) -> TestClient:
    store = Persistence(Database("", sqlite_path=tmp_path / "admin.db"))
    store.operators.ensure("admin@example.com", display_name="Admin User")
    store.operators.set_role("admin@example.com", "admin")
    store.operators.ensure("operator@example.com", display_name="Operator User")
    monkeypatch.setattr(admin, "Persistence", lambda: store)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin")
    return TestClient(app)


def test_list_operators_requires_admin(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _principal_headers(
        monkeypatch,
        email="operator@example.com",
        role="operator",
    )
    response = admin_client.get("/api/admin/operators", headers=headers)
    assert response.status_code == 403


def test_admin_can_list_and_update_operators(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _principal_headers(
        monkeypatch,
        email="admin@example.com",
        role="admin",
    )
    listed = admin_client.get("/api/admin/operators", headers=headers)
    assert listed.status_code == 200
    emails = {row["email"] for row in listed.json()}
    assert "operator@example.com" in emails

    updated = admin_client.patch(
        "/api/admin/operators/operator@example.com",
        headers=headers,
        json={"role": "reviewer"},
    )
    assert updated.status_code == 200
    assert updated.json()["role"] == "reviewer"

    disabled = admin_client.patch(
        "/api/admin/operators/operator@example.com",
        headers=headers,
        json={"active": False},
    )
    assert disabled.status_code == 200
    assert disabled.json()["active"] is False


def test_admin_cannot_demote_self(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = _principal_headers(
        monkeypatch,
        email="admin@example.com",
        role="admin",
    )
    response = admin_client.patch(
        "/api/admin/operators/admin@example.com",
        headers=headers,
        json={"role": "operator"},
    )
    assert response.status_code == 400


def test_admin_config_is_read_only_snapshot(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "ops@example.com")
    monkeypatch.setenv("WRITE_BACK_MODE", "dry_run")
    headers = _principal_headers(
        monkeypatch,
        email="admin@example.com",
        role="admin",
    )
    response = admin_client.get("/api/admin/config", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["notify_owner_email"] == "ops@example.com"
    assert payload["write_back_mode"] == "dry_run"
    assert any(
        owner["category"] == "new_project" for owner in payload["category_owners"]
    )
    assert any(
        rule["agent_name"] == "vendor_followup"
        for rule in payload["approval_rules"]
    )
