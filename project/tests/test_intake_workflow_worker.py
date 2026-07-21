"""Focused tests for the durable Intake workflow worker."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import Principal, require_trusted_principal
from backend.routes import intake_agent, intake_webhook
from backend.services import intake_workflow
from backend.services.intake_workflow import drain_intake_jobs, enqueue_classification
from integrations.classification_client import ClassificationConfigError
from persistence import Database, Persistence


@pytest.fixture
def store(tmp_path) -> Persistence:
    return Persistence(Database("", sqlite_path=tmp_path / "workflow.db"))


def _create(store: Persistence, external_id: str = "FORM-1") -> dict:
    submission, _ = store.intake.create_submission(
        source="website",
        external_submission_id=external_id,
        submitted_by="client@example.com",
        body="Please send a quote.",
    )
    enqueue_classification(store, submission["id"])
    return submission


class _Routing:
    def route(self, **kwargs):
        return {
            "status": "SUCCESS",
            "board": {"url": "https://monday.example/board/1"},
            "item": {"id": "item-1"},
            "request": kwargs,
        }


def test_high_confidence_classifies_routes_and_notifies(
    store: Persistence, monkeypatch
) -> None:
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "owner@example.com")
    submission = _create(store)
    classified = drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: {
            "category": "quote_request",
            "confidence": 0.95,
            "reasoning": "Explicit quote request.",
        },
    )
    assert classified["succeeded"] == 1
    assert store.intake.get_submission(submission["id"])["status"] == "routing_queued"

    routed = drain_intake_jobs(limit=1, store=store, routing_service=_Routing())
    current = store.intake.get_submission(submission["id"])
    assert routed["succeeded"] == 1
    assert current["status"] == "completed"
    assert current["monday_result"]["item"]["id"] == "item-1"
    assert current["notification_result"]["status"] == "DRY_RUN"


def test_low_confidence_waits_for_server_authenticated_review(
    store: Persistence, monkeypatch
) -> None:
    submission = _create(store)
    drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: {
            "category": "new_project",
            "confidence": 0.4,
            "reasoning": "Ambiguous request.",
        },
    )
    current = store.intake.get_submission(submission["id"])
    assert current["status"] == "awaiting_approval"

    monkeypatch.setattr(intake_agent, "get_persistence", lambda: store)
    app = FastAPI()
    app.include_router(intake_agent.router)
    app.dependency_overrides[intake_agent._reviewer] = lambda: Principal(
        "reviewer@example.com", "reviewer"
    )
    response = TestClient(app).post(
        f"/submissions/{submission['id']}/approve",
        json={"version": current["version"]},
    )
    assert response.status_code == 200
    assert response.json()["approval_actor"] == "reviewer@example.com"
    assert response.json()["status"] == "routing_queued"


def test_retryable_and_permanent_classification_failures(
    store: Persistence, monkeypatch
) -> None:
    monkeypatch.setenv("INTAKE_RETRY_BASE_SECONDS", "100")
    transient = _create(store, "TRANSIENT")
    result = drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    assert result["retried"] == 1
    assert store.intake.get_submission(transient["id"])["status"] == (
        "classification_retrying"
    )

    permanent = _create(store, "PERMANENT")
    result = drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: (_ for _ in ()).throw(
            ClassificationConfigError("missing key")
        ),
    )
    assert result["dead"] == 1
    assert store.intake.get_submission(permanent["id"])["status"] == (
        "classification_dead"
    )


def test_signed_webhook_persists_replays_202_without_classifier(
    store: Persistence, monkeypatch
) -> None:
    secret = "secret"
    monkeypatch.setenv("INTAKE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(intake_webhook, "get_persistence", lambda: store)
    app = FastAPI()
    app.include_router(intake_webhook.router, prefix="/intake")
    raw = json.dumps(
        {"submitted_by": "client@example.com", "text": "Please quote this."},
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
    client = TestClient(app)
    first = client.post("/intake", content=raw, headers=headers)
    replay = client.post("/intake", content=raw, headers=headers)
    assert first.status_code == replay.status_code == 202
    assert first.json()["submission_id"] == replay.json()["submission_id"]
    assert replay.json()["replay"] is True
    assert len(store.jobs.list_for_submission(first.json()["submission_id"])) == 1


@pytest.mark.parametrize(
    ("category", "expected_status"),
    [
        ("new_project", "routing_queued"),
        ("quote_request", "routing_queued"),
        ("general_inquiry", "routing_queued"),
        ("support_issue", "awaiting_approval"),
        ("unclassified", "awaiting_approval"),
    ],
)
def test_every_classification_category_reaches_expected_state(
    store: Persistence,
    category: str,
    expected_status: str,
) -> None:
    submission = _create(store, f"CATEGORY-{category}")

    result = drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: {
            "category": category,
            "confidence": 0.99,
            "reasoning": f"Mocked {category} classification.",
        },
    )

    current = store.intake.get_submission(submission["id"])
    assert result["succeeded"] == 1
    assert current["classification_category"] == category
    assert current["status"] == expected_status
    assert current["approval_status"] == (
        "not_required" if expected_status == "routing_queued" else "pending"
    )


def test_approval_category_correction_enforces_rbac_and_version(
    store: Persistence, monkeypatch
) -> None:
    submission = _create(store, "CORRECT-1")
    drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: {
            "category": "support_issue",
            "confidence": 0.99,
            "reasoning": "Existing installation problem.",
        },
    )
    current = store.intake.get_submission(submission["id"])
    monkeypatch.setattr(intake_agent, "get_persistence", lambda: store)
    app = FastAPI()
    app.include_router(intake_agent.router)
    app.dependency_overrides[require_trusted_principal] = lambda: Principal(
        "operator@example.com", "operator"
    )
    client = TestClient(app)
    path = f"/submissions/{submission['id']}/correct-category"

    forbidden = client.post(
        path,
        json={"version": current["version"], "category": "quote_request"},
    )
    assert forbidden.status_code == 403

    app.dependency_overrides[require_trusted_principal] = lambda: Principal(
        "reviewer@example.com", "reviewer"
    )
    corrected = client.post(
        path,
        json={"version": current["version"], "category": "quote_request"},
    )
    assert corrected.status_code == 200
    assert corrected.json()["classification_category"] == "quote_request"
    assert corrected.json()["approval_actor"] == "reviewer@example.com"
    assert corrected.json()["status"] == "routing_queued"

    stale = client.post(
        path,
        json={"version": current["version"], "category": "new_project"},
    )
    assert stale.status_code == 409
    assert len(
        [
            job
            for job in store.jobs.list_for_submission(submission["id"])
            if job.queue == "intake-routing"
        ]
    ) == 1


def test_gmail_notification_failure_retries_once_and_is_idempotent(
    store: Persistence, monkeypatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "live")
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setenv("INTAKE_RETRY_BASE_SECONDS", "0")
    monkeypatch.setattr(intake_workflow, "get_gmail_service", lambda: object())
    sends = iter([TimeoutError("Gmail timed out"), {"id": "message-1"}])

    def send(*args, **kwargs):
        outcome = next(sends)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(intake_workflow, "send_email", send)
    submission = _create(store, "GMAIL-RETRY")
    drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: {
            "category": "quote_request",
            "confidence": 0.99,
            "reasoning": "Explicit quote.",
        },
    )

    first = drain_intake_jobs(limit=1, store=store, routing_service=_Routing())
    assert first["retried"] == 1
    assert store.intake.get_submission(submission["id"])["status"] == "routing_retrying"

    second = drain_intake_jobs(limit=1, store=store, routing_service=_Routing())
    current = store.intake.get_submission(submission["id"])
    assert second["succeeded"] == 1
    assert current["status"] == "completed"
    assert current["notification_result"]["message"] == {"id": "message-1"}
    with store.database.connect() as conn:
        effect = conn.execute(
            "SELECT status FROM effect_executions "
            "WHERE effect_type = 'intake_category_owner_email'"
        ).fetchone()
    assert effect["status"] == "completed"

    assert drain_intake_jobs(
        limit=1, store=store, routing_service=_Routing()
    )["claimed"] == 0


def test_persisted_list_detail_events_and_attempts_states(
    store: Persistence, monkeypatch
) -> None:
    first = _create(store, "LIST-1")
    second = _create(store, "LIST-2")
    drain_intake_jobs(
        limit=2,
        store=store,
        classifier=lambda _: {
            "category": "support_issue",
            "confidence": 0.95,
            "reasoning": "Requires review.",
        },
    )
    monkeypatch.setattr(intake_agent, "get_persistence", lambda: store)
    app = FastAPI()
    app.include_router(intake_agent.router)
    client = TestClient(app)

    page = client.get("/submissions", params={"status": "awaiting_approval"})
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert {item["id"] for item in page.json()["items"]} == {
        first["id"],
        second["id"],
    }
    detail = client.get(f"/submissions/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["classification_category"] == "support_issue"
    assert detail.json()["approval_status"] == "pending"
    events = client.get(f"/submissions/{first['id']}/events").json()["items"]
    attempts = client.get(f"/submissions/{first['id']}/attempts").json()["items"]
    assert [event["event_type"] for event in events] == [
        "received",
        "classification_queued",
        "classification_started",
        "classification_completed",
    ]
    assert attempts[0]["status"] == "succeeded"


def test_webhook_rejects_stale_bad_signature_and_delivery_payload_reuse(
    store: Persistence, monkeypatch
) -> None:
    secret = "secret"
    monkeypatch.setenv("INTAKE_WEBHOOK_SECRET", secret)
    monkeypatch.setattr(intake_webhook, "get_persistence", lambda: store)
    app = FastAPI()
    app.include_router(intake_webhook.router, prefix="/intake")
    client = TestClient(app)
    raw = b'{"submitted_by":"client@example.com","text":"Hello"}'
    source, delivery_id = "website", "delivery-security"

    def headers(body: bytes, timestamp: int) -> dict[str, str]:
        sent = str(timestamp)
        signature = hmac.new(
            secret.encode(),
            f"{sent}\n{source}\n{delivery_id}\n".encode() + body,
            hashlib.sha256,
        ).hexdigest()
        return {
            "X-Webhook-Timestamp": sent,
            "X-Webhook-Source": source,
            "X-Webhook-Delivery-ID": delivery_id,
            "X-Webhook-Signature": f"sha256={signature}",
            "Content-Type": "application/json",
        }

    now = int(time.time())
    stale = client.post("/intake", content=raw, headers=headers(raw, now - 301))
    assert stale.status_code == 401
    bad = headers(raw, now)
    bad["X-Webhook-Signature"] = "sha256=bad"
    assert client.post("/intake", content=raw, headers=bad).status_code == 401
    assert client.post(
        "/intake", content=raw, headers=headers(raw, now)
    ).status_code == 202

    changed = b'{"submitted_by":"client@example.com","text":"Changed"}'
    conflict = client.post(
        "/intake",
        content=changed,
        headers=headers(changed, now),
    )
    assert conflict.status_code == 409
    assert len(store.jobs.list_for_submission(
        client.post("/intake", content=raw, headers=headers(raw, now)).json()[
            "submission_id"
        ]
    )) == 1


def test_dry_run_signed_ingress_to_persisted_completion_uat(
    store: Persistence, monkeypatch
) -> None:
    monkeypatch.setenv("WRITE_BACK_MODE", "dry_run")
    monkeypatch.setenv("INTAKE_WEBHOOK_SECRET", "uat-secret")
    monkeypatch.setenv("NOTIFY_OWNER_EMAIL", "owner@example.com")
    monkeypatch.setattr(intake_webhook, "get_persistence", lambda: store)
    app = FastAPI()
    app.include_router(intake_webhook.router, prefix="/intake")
    raw = b'{"submission_id":"uat-1","submitted_by":"uat@example.com","text":"Please quote a lobby sign."}'
    timestamp = str(int(time.time()))
    signature = hmac.new(
        b"uat-secret",
        f"{timestamp}\nuat\nuat-delivery-1\n".encode() + raw,
        hashlib.sha256,
    ).hexdigest()
    accepted = TestClient(app).post(
        "/intake",
        content=raw,
        headers={
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Source": "uat",
            "X-Webhook-Delivery-ID": "uat-delivery-1",
            "X-Webhook-Signature": f"sha256={signature}",
            "Content-Type": "application/json",
        },
    )
    assert accepted.status_code == 202

    first = drain_intake_jobs(
        limit=1,
        store=store,
        classifier=lambda _: {
            "category": "quote_request",
            "confidence": 0.97,
            "reasoning": "Explicit price request.",
        },
    )
    second = drain_intake_jobs(
        limit=1,
        store=store,
        routing_service=_Routing(),
    )
    current = store.intake.get_submission(accepted.json()["submission_id"])
    assert first["succeeded"] == second["succeeded"] == 1
    assert current["status"] == "completed"
    assert current["monday_result"]["status"] == "SUCCESS"
    assert current["notification_result"]["status"] == "DRY_RUN"
