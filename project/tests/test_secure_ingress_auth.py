"""Focused tests for signed ingress, operator roles, and trusted principals."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import auth
from backend.auth import Principal
from backend.routes import intake_webhook
from persistence import Database, Persistence


def _webhook_headers(secret: str, raw: bytes, *, timestamp: int = 1_700_000_000) -> dict:
    source, delivery_id = "website", "delivery-123"
    message = f"{timestamp}\n{source}\n{delivery_id}\n".encode() + raw
    signature = hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()
    return {
        "X-Webhook-Timestamp": str(timestamp),
        "X-Webhook-Source": source,
        "X-Webhook-Delivery-ID": delivery_id,
        "X-Webhook-Signature": f"sha256={signature}",
        "Content-Type": "application/json",
    }


def test_webhook_signature_and_replay_window() -> None:
    raw = b'{"text":"hello"}'
    headers = _webhook_headers("secret", raw)
    intake_webhook.verify_webhook_signature(
        secret="secret",
        timestamp=headers["X-Webhook-Timestamp"],
        source=headers["X-Webhook-Source"],
        delivery_id=headers["X-Webhook-Delivery-ID"],
        signature=headers["X-Webhook-Signature"],
        raw_body=raw,
        now=1_700_000_001,
    )
    with pytest.raises(HTTPException, match="Invalid webhook signature"):
        intake_webhook.verify_webhook_signature(
            secret="secret",
            timestamp=headers["X-Webhook-Timestamp"],
            source=headers["X-Webhook-Source"],
            delivery_id=headers["X-Webhook-Delivery-ID"],
            signature=headers["X-Webhook-Signature"],
            raw_body=raw + b" ",
            now=1_700_000_001,
        )
    with pytest.raises(HTTPException, match="replay window"):
        intake_webhook.verify_webhook_signature(
            secret="secret",
            timestamp=headers["X-Webhook-Timestamp"],
            source=headers["X-Webhook-Source"],
            delivery_id=headers["X-Webhook-Delivery-ID"],
            signature=headers["X-Webhook-Signature"],
            raw_body=raw,
            now=1_700_001_000,
        )


def test_webhook_delivery_is_queued_once(monkeypatch, tmp_path) -> None:
    store = Persistence(Database("", sqlite_path=tmp_path / "ingress.db"))
    monkeypatch.setenv("INTAKE_WEBHOOK_SECRET", "secret")
    monkeypatch.setattr(intake_webhook, "get_persistence", lambda: store)
    monkeypatch.setattr(intake_webhook.time, "time", lambda: 1_700_000_001)
    app = FastAPI()
    app.include_router(intake_webhook.router, prefix="/intake")
    client = TestClient(app)
    raw = json.dumps(
        {"submitted_by": "client@example.com", "text": "Please quote this."},
        separators=(",", ":"),
    ).encode()
    headers = _webhook_headers("secret", raw)

    first = client.post("/intake", content=raw, headers=headers)
    replay = client.post("/intake", content=raw, headers=headers)

    assert first.status_code == replay.status_code == 202
    assert first.json()["submission_id"] == replay.json()["submission_id"]
    assert first.json()["status"] == "classification_queued"
    assert first.json()["replay"] is False
    assert replay.json()["replay"] is True
    assert len(store.jobs.list_for_submission(first.json()["submission_id"])) == 1


def test_operator_role_default_lookup_and_preservation(tmp_path) -> None:
    store = Persistence(Database("", sqlite_path=tmp_path / "roles.db"))
    created = store.operators.ensure("User@Example.com", display_name="User")
    assert created["email"] == "user@example.com"
    assert created["role"] == "operator"
    assert store.operators.set_role("user@example.com", "reviewer")
    existing = store.operators.ensure(
        "user@example.com",
        display_name="Updated User",
        default_role="admin",
    )
    assert existing["role"] == "reviewer"
    assert store.operators.get("USER@example.com")["display_name"] == "Updated User"


def test_trusted_principal_signature_and_rbac(monkeypatch) -> None:
    monkeypatch.setenv("TRUSTED_IDENTITY_SECRET", "identity-secret")
    monkeypatch.setattr(auth.time, "time", lambda: 1_700_000_001)
    signature = auth.sign_trusted_identity(
        "identity-secret",
        timestamp="1700000000",
        email="reviewer@example.com",
        role="reviewer",
    )
    principal = auth.require_trusted_principal(
        x_principal_email="reviewer@example.com",
        x_principal_role="reviewer",
        x_principal_timestamp="1700000000",
        x_principal_signature=signature,
    )
    assert principal == Principal("reviewer@example.com", "reviewer")
    assert auth.require_roles("reviewer", "admin")(principal=principal) == principal
    with pytest.raises(HTTPException) as denied:
        auth.require_roles("admin")(principal=principal)
    assert denied.value.status_code == 403
    with pytest.raises(HTTPException) as forged:
        auth.require_trusted_principal(
            x_principal_email="admin@example.com",
            x_principal_role="admin",
            x_principal_timestamp="1700000000",
            x_principal_signature=signature,
        )
    assert forged.value.status_code == 401
