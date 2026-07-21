"""Tests for DB-backed approval rules."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import auth
from backend.routes import admin
from models.agent_result import AgentResult
from persistence import Database, Persistence
from supervisor.approval_policy import (
    get_confidence_threshold,
    get_risky_statuses,
    requires_human_approval,
    serialize_risky_status_map,
)


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
    store = Persistence(Database("", sqlite_path=tmp_path / "approval.db"))
    store.operators.ensure("admin@example.com")
    store.operators.set_role("admin@example.com", "admin")
    monkeypatch.setattr(admin, "Persistence", lambda: store)
    monkeypatch.setattr("persistence.Persistence", lambda: store)
    app = FastAPI()
    app.include_router(admin.router, prefix="/api/admin")
    return TestClient(app), store


def test_confidence_threshold_from_db(setup):
    _, store = setup
    store.config.set("approval_confidence_threshold", "0.9", changed_by="admin@test.com")
    assert get_confidence_threshold() == 0.9


def test_risky_statuses_from_db(setup):
    _, store = setup
    rules = serialize_risky_status_map({"vendor_followup": {"ESCALATE"}})
    store.config.set("approval_rules", rules, changed_by="admin@test.com")
    assert get_risky_statuses("vendor_followup") == {"ESCALATE"}


def test_requires_approval_uses_db_threshold(setup):
    _, store = setup
    store.config.set("approval_confidence_threshold", "0.8", changed_by="admin@test.com")
    result = AgentResult(
        data={"thread_id": "T-1"},
        confidence=0.85,
        requires_approval=False,
        reasoning="ok",
    )
    assert requires_human_approval("email_reply_monitoring", result) is False

    low = AgentResult(
        data={"thread_id": "T-2"},
        confidence=0.7,
        requires_approval=False,
        reasoning="low",
    )
    assert requires_human_approval("email_reply_monitoring", low) is True


def test_api_update_approval_rule(setup, monkeypatch):
    client, store = setup
    headers = _admin_headers(monkeypatch)
    resp = client.put(
        "/api/admin/approval-rules/vendor_followup",
        json={"risky_statuses": ["ESCALATE"]},
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["risky_statuses"] == ["ESCALATE"]

    stored = json.loads(store.config.get("approval_rules") or "{}")
    assert stored["vendor_followup"] == ["ESCALATE"]


def test_api_invalid_confidence_threshold(setup, monkeypatch):
    client, _ = setup
    headers = _admin_headers(monkeypatch)
    resp = client.put(
        "/api/admin/config/approval_confidence_threshold",
        json={"value": "2.0"},
        headers=headers,
    )
    assert resp.status_code == 400
