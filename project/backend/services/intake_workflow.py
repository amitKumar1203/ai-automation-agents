"""Durable Intake classification, approval, routing, and notification workers."""

from __future__ import annotations

import json
import os
import random
import socket
import uuid
from typing import Any, Callable

import requests

from backend.services.monday_routing import MondayIntakeRoutingService
from integrations.classification_client import (
    ClassificationConfigError,
    ClassificationError,
    classify_intake_text,
)
from integrations.email_templates import build_intake_owner_email
from integrations.gmail_client import GmailFetchError, get_gmail_service, send_email
from integrations.monday_intake_client import MondayIntakeConfigError
from persistence import Persistence
from persistence.repositories import Job
from supervisor.write_back import get_write_back_mode

CLASSIFICATION_QUEUE = "intake-classification"
ROUTING_QUEUE = "intake-routing"
CLASSIFICATION_JOB = "classify_intake"
ROUTING_JOB = "route_intake"
SAFE_AUTO_CATEGORIES = frozenset(
    {"new_project", "quote_request", "general_inquiry"}
)
ALL_CATEGORIES = frozenset((*SAFE_AUTO_CATEGORIES, "support_issue", "unclassified"))


def enqueue_classification(
    store: Persistence, submission_id: str
) -> tuple[Job, bool]:
    job, created = store.jobs.enqueue(
        queue=CLASSIFICATION_QUEUE,
        job_type=CLASSIFICATION_JOB,
        payload={"submission_id": submission_id},
        max_attempts=_int_env("INTAKE_CLASSIFICATION_MAX_ATTEMPTS", 5),
        idempotency_key=f"classify:{submission_id}",
    )
    if created:
        store.intake.append_event(
            submission_id, "classification_queued", {"job_id": job.id}
        )
    return job, created


def enqueue_routing(
    store: Persistence, submission_id: str, *, version: int
) -> tuple[Job, bool]:
    job, created = store.jobs.enqueue(
        queue=ROUTING_QUEUE,
        job_type=ROUTING_JOB,
        payload={"submission_id": submission_id, "version": version},
        max_attempts=_int_env("INTAKE_ROUTING_MAX_ATTEMPTS", 5),
        idempotency_key=f"route:{submission_id}:v{version}",
    )
    if created:
        store.intake.append_event(
            submission_id,
            "routing_queued",
            {"job_id": job.id, "version": version},
        )
    return job, created


def drain_intake_jobs(
    *,
    limit: int = 10,
    store: Persistence | None = None,
    worker_id: str | None = None,
    classifier: Callable[[str], dict[str, Any]] = classify_intake_text,
    routing_service: MondayIntakeRoutingService | None = None,
) -> dict[str, Any]:
    """Drain a bounded number of jobs, alternating queues to avoid starvation."""
    persistence = store or Persistence()
    bounded = min(max(int(limit), 1), _int_env("INTAKE_CRON_MAX_JOBS", 50))
    identity = worker_id or f"intake-{uuid.uuid4()}"
    counts = {"claimed": 0, "succeeded": 0, "retried": 0, "dead": 0}
    queues = (CLASSIFICATION_QUEUE, ROUTING_QUEUE)
    for index in range(bounded):
        job = None
        for queue in (queues[index % 2], queues[(index + 1) % 2]):
            job = persistence.jobs.claim(
                queue=queue,
                worker_id=identity,
                lease_seconds=_int_env("INTAKE_JOB_LEASE_SECONDS", 90),
            )
            if job is not None:
                break
        if job is None:
            break
        counts["claimed"] += 1
        outcome = (
            _run_classification(persistence, job, identity, classifier)
            if job.queue == CLASSIFICATION_QUEUE
            else _run_routing(persistence, job, identity, routing_service)
        )
        counts[outcome] += 1
    return {"worker_id": identity, "limit": bounded, **counts}


def _run_classification(
    store: Persistence,
    job: Job,
    worker_id: str,
    classifier: Callable[[str], dict[str, Any]],
) -> str:
    submission_id = str(job.payload.get("submission_id") or "")
    submission = store.intake.get_submission(submission_id)
    if submission is None:
        store.jobs.dead_letter(job.id, worker_id=worker_id, error="submission not found")
        return "dead"
    if submission["status"] in {
        "awaiting_approval",
        "routing_queued",
        "routing_running",
        "routing_retrying",
        "routing_dead",
        "completed",
        "rejected",
    }:
        store.jobs.complete(job.id, worker_id=worker_id)
        return "succeeded"
    store.intake.transition(
        submission_id,
        status="classification_running",
        event_type="classification_started",
        data={"job_id": job.id, "attempt": job.attempts},
    )
    attempt = store.classifications.start(
        submission_id, model=os.getenv("INTAKE_CLASSIFICATION_MODEL", "claude-sonnet-4-5")
    )
    try:
        result = classifier(submission["body"])
        category = str(result.get("category") or "").strip().lower()
        confidence = float(result.get("confidence"))
        reasoning = str(result.get("reasoning") or "").strip()
        if category not in ALL_CATEGORIES or not 0 <= confidence <= 1 or not reasoning:
            raise ValueError("classifier returned invalid category, confidence, or reasoning")
    except Exception as exc:  # provider exceptions are classified below
        store.classifications.finish(attempt["id"], error=str(exc))
        return _handle_failure(
            store, job, worker_id, submission_id, "classification", exc
        )

    store.classifications.finish(
        attempt["id"],
        category=category,
        confidence=confidence,
        reasoning=reasoning,
    )
    threshold = _float_env("INTAKE_AUTO_ROUTE_CONFIDENCE", 0.75)
    auto_route = category in SAFE_AUTO_CATEGORIES and confidence >= threshold
    state = store.intake.transition(
        submission_id,
        status="routing_queued" if auto_route else "awaiting_approval",
        event_type="classification_completed",
        data={"category": category, "confidence": confidence, "auto_route": auto_route},
        fields={
            "classification_category": category,
            "classification_confidence": confidence,
            "classification_reasoning": reasoning,
            "classification_model": attempt.get("model"),
            "approval_status": "not_required" if auto_route else "pending",
        },
    )
    if auto_route and state is not None:
        enqueue_routing(store, submission_id, version=int(state["version"]))
    store.jobs.complete(job.id, worker_id=worker_id)
    return "succeeded"


def _run_routing(
    store: Persistence,
    job: Job,
    worker_id: str,
    routing_service: MondayIntakeRoutingService | None,
) -> str:
    submission_id = str(job.payload.get("submission_id") or "")
    submission = store.intake.get_submission(submission_id)
    if submission is None:
        store.jobs.dead_letter(job.id, worker_id=worker_id, error="submission not found")
        return "dead"
    if submission["status"] == "completed":
        store.jobs.complete(job.id, worker_id=worker_id)
        return "succeeded"
    category = str(submission.get("classification_category") or "")
    if category not in ALL_CATEGORIES:
        return _handle_failure(
            store,
            job,
            worker_id,
            submission_id,
            "routing",
            ValueError("submission has no valid approved category"),
        )
    store.intake.transition(
        submission_id,
        status="routing_running",
        event_type="routing_started",
        data={"job_id": job.id, "attempt": job.attempts},
        fields={"execution_status": "running"},
    )
    try:
        service = routing_service or MondayIntakeRoutingService(
            effects=store.effects
        )
        monday = service.route(
            external_submission_id=submission["external_submission_id"],
            category=category,
            submitted_by=submission["submitted_by"],
            submission_text=submission["body"],
            idempotency_key=f"intake:{submission_id}:monday:{category}",
        )
        notification = _notify_category_owner(store, submission, category, monday)
    except Exception as exc:
        return _handle_failure(store, job, worker_id, submission_id, "routing", exc)

    store.intake.transition(
        submission_id,
        status="completed",
        event_type="routing_completed",
        data={"job_id": job.id},
        fields={
            "execution_status": "succeeded",
            "monday_result_json": monday,
            "notification_result_json": notification,
        },
        completed=True,
    )
    store.jobs.complete(job.id, worker_id=worker_id)
    return "succeeded"


def _notify_category_owner(
    store: Persistence,
    submission: dict[str, Any],
    category: str,
    monday: dict[str, Any],
) -> dict[str, Any]:
    recipient = _category_owner(category)
    if not recipient:
        raise ValueError(f"no category owner email configured for {category}")
    request = {
        "to": recipient,
        "submission_id": submission["id"],
        "category": category,
        "monday": monday,
    }
    effect, acquired = store.effects.begin(
        effect_type="intake_category_owner_email",
        idempotency_key=f"{submission['id']}:{category}",
        request=request,
    )
    if not acquired:
        if effect["status"] == "completed" and isinstance(effect.get("result"), dict):
            return effect["result"]
        raise RuntimeError("category owner notification is already in progress")
    try:
        if get_write_back_mode() != "live":
            subject, body_text, body_html = build_intake_owner_email(
                category=category,
                submitted_by=submission["submitted_by"],
                request_text=submission["body"],
                external_submission_id=submission["external_submission_id"],
                submission_id=submission["id"],
                monday=monday,
            )
            result = {
                "status": "DRY_RUN",
                **request,
                "subject": subject,
                "body_text": body_text,
                "body_html": body_html,
            }
        else:
            subject, body_text, body_html = build_intake_owner_email(
                category=category,
                submitted_by=submission["submitted_by"],
                request_text=submission["body"],
                external_submission_id=submission["external_submission_id"],
                submission_id=submission["id"],
                monday=monday,
            )
            result = {
                "status": "SUCCESS",
                "to": recipient,
                "message": send_email(
                    get_gmail_service(),
                    to=recipient,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                ),
            }
    except Exception as exc:
        store.effects.complete(effect["id"], error=str(exc))
        raise
    store.effects.complete(effect["id"], result=result)
    return result


def _handle_failure(
    store: Persistence,
    job: Job,
    worker_id: str,
    submission_id: str,
    stage: str,
    exc: Exception,
) -> str:
    error = str(exc)[:2000]
    retryable = _is_retryable(exc)
    if retryable:
        failed = store.jobs.fail(
            job.id,
            worker_id=worker_id,
            error=error,
            retry_delay_seconds=_retry_delay(job.attempts),
        )
        dead = failed is not None and failed.status == "dead"
    else:
        failed = store.jobs.dead_letter(job.id, worker_id=worker_id, error=error)
        dead = True
    store.intake.transition(
        submission_id,
        status=f"{stage}_{'dead' if dead else 'retrying'}",
        event_type=f"{stage}_{'dead_lettered' if dead else 'retry_scheduled'}",
        data={
            "job_id": job.id,
            "attempt": job.attempts,
            "retryable": retryable,
            "error": error,
        },
        fields={"execution_status": "failed"} if stage == "routing" else None,
        completed=dead,
    )
    return "dead" if dead else "retried"


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, (ClassificationConfigError, MondayIntakeConfigError, ValueError)):
        return False
    current: BaseException | None = exc
    while current is not None:
        status = getattr(current, "status_code", None)
        response = getattr(current, "response", None)
        status = status or getattr(response, "status_code", None) or getattr(
            getattr(current, "resp", None), "status", None
        )
        if status == 429 or (isinstance(status, int) and status >= 500):
            return True
        name = type(current).__name__.lower()
        if any(token in name for token in ("ratelimit", "timeout", "connection")):
            return True
        if isinstance(
            current,
            (
                requests.RequestException,
                TimeoutError,
                ConnectionError,
                socket.timeout,
            ),
        ):
            return True
        current = current.__cause__ or current.__context__
    # Wrapped provider failures without a transport/status cause are validation
    # or configuration failures and should not burn retries.
    return not isinstance(exc, (ClassificationError, GmailFetchError))


def _retry_delay(attempt: int) -> float:
    base = _float_env("INTAKE_RETRY_BASE_SECONDS", 2.0)
    maximum = _float_env("INTAKE_RETRY_MAX_SECONDS", 300.0)
    return min(maximum, base * (2 ** max(attempt - 1, 0))) + random.uniform(0, base)


def _config_get(key: str) -> str | None:
    try:
        from persistence import Persistence
        return Persistence().config.get(key)
    except Exception:
        return None


def _category_owner(category: str) -> str:
    # 1. DB config per-category key
    db_key = f"intake_{category}_owner_email"
    db_val = (_config_get(db_key) or "").strip()
    if db_val:
        return db_val
    # 2. Env per-category
    direct = (os.getenv(f"INTAKE_{category.upper()}_OWNER_EMAIL") or "").strip()
    if direct:
        return direct
    # 3. Env JSON mapping
    raw = (os.getenv("INTAKE_CATEGORY_OWNER_EMAILS") or "").strip()
    if raw:
        try:
            mapping = json.loads(raw)
            candidate = str(mapping.get(category) or "").strip()
            if candidate:
                return candidate
        except (ValueError, AttributeError):
            raise ValueError("INTAKE_CATEGORY_OWNER_EMAILS must be a JSON object")
    # 4. DB / env default owner
    from supervisor.write_back import get_notify_owner_email
    return get_notify_owner_email() or ""


def _int_env(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float_env(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))
