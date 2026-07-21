"""Tests for system config repository, admin config API, and DB→env fallback."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import auth
from backend.routes import admin
from persistence import Database, Persistence


def _admin_headers(monkeypatch):
    monkeypatch.setenv("TRUSTED_IDENTITY_SECRET", "identity-secret")
    monkeypatch.setattr(auth.time, "time", lambda: 1_700_000_001)
    sig = auth.sign_trusted_identity(
        "identity-secret",
        timestamp="1700000000",
        email="admin@example.com",
        role="admin",
    )
    return {
        "X-Principal-Email": "admin@example.com",
        "X-Principal-Role": "admin",
        "X-Principal-Timestamp": "1700000000",
        "X-Principal-Signature": sig,
    }


@pytest.fixture
def setup(monkeypatch, tmp_path):
    store = Persistence(Database("", sqlite_path=tmp_path / "cfg.db"))
    store.operators.ensure("admin@example.com", display_name="Admin")
    store.operators.set_role("admin@example.com", "admin")
    monkeypatch.setattr(admin, "Persistence", lambda: store)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin")
    return TestClient(app), store


def test_config_set_and_get(setup):
    client, store = setup
    store.config.set("write_back_mode", "live", changed_by="admin@test.com")
    assert store.config.get("write_back_mode") == "live"
    assert store.config.get("nonexistent") is None


def test_config_rejects_unknown_key(setup):
    _, store = setup
    with pytest.raises(ValueError, match="unknown config key"):
        store.config.set("bad_key", "val", changed_by="admin@test.com")


def test_config_audit_log(setup):
    _, store = setup
    store.config.set("notify_owner_email", "old@test.com", changed_by="a@t.com")
    store.config.set("notify_owner_email", "new@test.com", changed_by="b@t.com")
    log = store.config.audit_log("notify_owner_email")
    assert len(log) == 2
    assert log[0]["new_value"] == "new@test.com"
    assert log[0]["old_value"] == "old@test.com"
    assert log[1]["old_value"] is None


def test_api_put_config(setup, monkeypatch):
    client, _ = setup
    headers = _admin_headers(monkeypatch)
    resp = client.put(
        "/api/admin/config/write_back_mode",
        json={"value": "live"},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["value"] == "live"

    resp2 = client.get("/api/admin/config", headers=headers)
    assert resp2.json()["write_back_mode"] == "live"


def test_api_put_unknown_key(setup, monkeypatch):
    client, _ = setup
    headers = _admin_headers(monkeypatch)
    resp = client.put(
        "/api/admin/config/bad_key",
        json={"value": "x"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_config_overrides_env(setup, monkeypatch):
    client, store = setup
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "env@test.com")
    headers = _admin_headers(monkeypatch)

    # Before DB override, env shows
    resp = client.get("/api/admin/config", headers=headers)
    assert resp.json()["notify_owner_email"] == "env@test.com"

    # DB override takes precedence
    store.config.set("notify_owner_email", "db@test.com", changed_by="admin@test.com")
    resp2 = client.get("/api/admin/config", headers=headers)
    assert resp2.json()["notify_owner_email"] == "db@test.com"


def test_config_audit_api(setup, monkeypatch):
    client, store = setup
    headers = _admin_headers(monkeypatch)
    store.config.set("write_back_mode", "live", changed_by="admin@test.com")
    resp = client.get("/api/admin/config/audit", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
    assert resp.json()[0]["config_key"] == "write_back_mode"
