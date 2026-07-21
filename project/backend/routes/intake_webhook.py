"""Signed webhook ingress for dynamic client intake submissions."""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import ValidationError

# Kept as an import-compatible symbol for callers migrating from the old
# synchronous route. The webhook handler intentionally never invokes it.
from backend.routes.intake_agent import classify_intake_submission  # noqa: F401
from backend.schemas import IntakeAcceptedResponse, IntakeSubmissionRequest
from backend.services.intake_workflow import enqueue_classification
from persistence import Persistence

router = APIRouter()

def _signature_payload(
    timestamp: str,
    source: str,
    delivery_id: str,
    raw_body: bytes,
) -> bytes:
    prefix = f"{timestamp}\n{source}\n{delivery_id}\n".encode("utf-8")
    return prefix + raw_body


def verify_webhook_signature(
    *,
    secret: str,
    timestamp: str,
    source: str,
    delivery_id: str,
    signature: str,
    raw_body: bytes,
    now: float | None = None,
    replay_window_seconds: int = 300,
) -> None:
    """Verify a timestamped HMAC-SHA256 signature over metadata and raw bytes."""
    if not all((secret, timestamp, source, delivery_id, signature)):
        raise HTTPException(status_code=401, detail="Missing webhook authentication")
    try:
        sent_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid webhook timestamp") from exc
    if abs((now if now is not None else time.time()) - sent_at) > replay_window_seconds:
        raise HTTPException(status_code=401, detail="Webhook timestamp outside replay window")

    provided = signature.removeprefix("sha256=").lower()
    expected = hmac.new(
        secret.encode("utf-8"),
        _signature_payload(timestamp, source, delivery_id, raw_body),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")


def get_persistence() -> Persistence:
    return Persistence()


@router.post("", response_model=IntakeAcceptedResponse, status_code=202)
async def webhook_intake(
    request: Request,
    x_webhook_timestamp: Annotated[
        str | None, Header(alias="X-Webhook-Timestamp")
    ] = None,
    x_webhook_source: Annotated[
        str | None, Header(alias="X-Webhook-Source")
    ] = None,
    x_webhook_delivery_id: Annotated[
        str | None, Header(alias="X-Webhook-Delivery-ID")
    ] = None,
    x_webhook_signature: Annotated[
        str | None, Header(alias="X-Webhook-Signature")
    ] = None,
) -> IntakeAcceptedResponse:
    """Verify, deduplicate, persist, and enqueue without calling Claude inline."""
    secret = (os.getenv("INTAKE_WEBHOOK_SECRET") or "").strip()
    if not secret:
        raise HTTPException(status_code=503, detail="Webhook signing is not configured")

    raw_body = await request.body()
    timestamp = (x_webhook_timestamp or "").strip()
    source = (x_webhook_source or "").strip()
    delivery_id = (x_webhook_delivery_id or "").strip()
    verify_webhook_signature(
        secret=secret,
        timestamp=timestamp,
        source=source,
        delivery_id=delivery_id,
        signature=(x_webhook_signature or "").strip(),
        raw_body=raw_body,
        replay_window_seconds=int(os.getenv("WEBHOOK_REPLAY_WINDOW_SECONDS", "300")),
    )

    store = get_persistence()
    try:
        delivery, created = store.webhooks.begin(
            provider=source,
            delivery_id=delivery_id,
            payload=raw_body,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if not created:
        if delivery["status"] == "completed" and delivery.get("response") is not None:
            replay = IntakeAcceptedResponse.model_validate(delivery["response"])
            return replay.model_copy(update={"replay": True})

    try:
        payload = IntakeSubmissionRequest.model_validate_json(raw_body)
        external_id = (
            payload.submission_id.strip()
            if payload.submission_id and payload.submission_id.strip()
            else delivery_id
        )
        submission, submission_created = store.intake.create_submission(
            source=source,
            external_submission_id=external_id,
            submitted_by=payload.submitted_by.strip(),
            body=payload.text.strip(),
            payload=payload.model_dump(mode="json"),
        )
        if submission_created:
            enqueue_classification(store, submission["id"])
            submission = store.intake.transition(
                submission["id"],
                status="classification_queued",
                event_type="accepted",
                data={"source": source, "delivery_id": delivery_id},
            ) or submission
        result = IntakeAcceptedResponse(
            submission_id=submission["id"],
            status=submission["status"],
            status_url=f"/api/intake-agent/submissions/{submission['id']}",
            replay=not created or not submission_created,
        )
        store.webhooks.finish(
            delivery["id"],
            response=result.model_dump(mode="json"),
        )
        return result
    except ValidationError as exc:
        store.webhooks.finish(delivery["id"], error="Invalid intake payload")
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    except Exception as exc:
        store.webhooks.finish(delivery["id"], error=str(exc))
        raise
