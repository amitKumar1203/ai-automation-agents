"""Focused tests for durable Intake persistence and queue semantics."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from persistence import Database, Persistence


@pytest.fixture
def store(tmp_path) -> Persistence:
    return Persistence(Database("", sqlite_path=tmp_path / "intake.db"))


def _submission(store: Persistence, external_id: str = "FORM-1") -> dict:
    submission, created = store.intake.create_submission(
        source="website",
        external_submission_id=external_id,
        submitted_by="client@example.com",
        body="Please quote a lobby sign.",
        payload={"campaign": "summer"},
    )
    assert created is True
    return submission


def test_persists_intake_events_webhooks_and_classification_attempts(
    store: Persistence,
) -> None:
    submission = _submission(store)
    assert store.intake.get_submission(submission["id"])["payload"] == {
        "campaign": "summer"
    }

    store.intake.append_event(submission["id"], "queued", {"queue": "classification"})
    events = store.intake.list_events(submission["id"])
    assert [event["event_type"] for event in events] == ["received", "queued"]
    with store.database.connect() as conn:
        with pytest.raises(sqlite3.DatabaseError, match="append-only"):
            conn.execute("DELETE FROM intake_events")

    delivery, first = store.webhooks.begin(
        provider="typeform", delivery_id="delivery-1", payload='{"answer": 1}'
    )
    duplicate, second = store.webhooks.begin(
        provider="typeform", delivery_id="delivery-1", payload='{"answer": 1}'
    )
    assert first is True and second is False
    assert delivery["id"] == duplicate["id"]

    attempt = store.classifications.start(submission["id"], model="test-model")
    assert attempt["attempt_number"] == 1
    assert store.classifications.finish(
        attempt["id"],
        category="quote_request",
        confidence=0.92,
        reasoning="Explicit quote request.",
    )
    next_attempt = store.classifications.start(submission["id"], model="test-model")
    assert next_attempt["attempt_number"] == 2


def test_duplicate_submission_is_returned_not_inserted(store: Persistence) -> None:
    first = _submission(store)
    duplicate, created = store.intake.create_submission(
        source="website",
        external_submission_id="FORM-1",
        submitted_by="different@example.com",
        body="A replay must not overwrite the original.",
    )

    assert created is False
    assert duplicate["id"] == first["id"]
    assert duplicate["body"] == first["body"]
    assert len(store.intake.list_events(first["id"])) == 1


def test_job_claim_retry_expired_lease_and_dead_letter(store: Persistence) -> None:
    start = datetime(2026, 7, 17, tzinfo=timezone.utc)
    job, created = store.jobs.enqueue(
        queue="intake",
        job_type="classify",
        payload={"submission_id": "S-1"},
        available_at=start,
        max_attempts=2,
        idempotency_key="classify:S-1",
    )
    duplicate, duplicate_created = store.jobs.enqueue(
        queue="intake",
        job_type="classify",
        payload={"submission_id": "S-1"},
        max_attempts=2,
        idempotency_key="classify:S-1",
    )
    assert created is True and duplicate_created is False
    assert duplicate.id == job.id

    claimed = store.jobs.claim(queue="intake", worker_id="worker-a", now=start)
    assert claimed is not None
    assert claimed.attempts == 1
    assert store.jobs.claim(queue="intake", worker_id="worker-b", now=start) is None

    retry = store.jobs.fail(
        job.id,
        worker_id="worker-a",
        error="temporary model failure",
        retry_delay_seconds=60,
        now=start,
    )
    assert retry is not None
    assert retry.status == "pending"
    assert store.jobs.claim(
        queue="intake",
        worker_id="worker-b",
        now=start + timedelta(seconds=59),
    ) is None
    reclaimed = store.jobs.claim(
        queue="intake",
        worker_id="worker-b",
        now=start + timedelta(seconds=60),
    )
    assert reclaimed is not None
    assert reclaimed.attempts == 2
    dead = store.jobs.fail(
        job.id,
        worker_id="worker-b",
        error="model unavailable",
        now=start + timedelta(seconds=61),
    )
    assert dead is not None
    assert dead.status == "dead"
    assert dead.dead_lettered_at is not None
    assert store.jobs.claim(
        queue="intake",
        worker_id="worker-c",
        now=start + timedelta(days=1),
    ) is None


def test_effect_idempotency_allows_only_one_executor(store: Persistence) -> None:
    first, acquired = store.effects.begin(
        effect_type="send_ack",
        idempotency_key="submission:S-1",
        request={"recipient": "client@example.com"},
    )
    replay, replay_acquired = store.effects.begin(
        effect_type="send_ack",
        idempotency_key="submission:S-1",
        request={"recipient": "client@example.com"},
    )

    assert acquired is True and replay_acquired is False
    assert replay["id"] == first["id"]
    assert store.effects.complete(first["id"], result={"message_id": "M-1"})
    assert not store.effects.complete(first["id"], result={"message_id": "M-2"})
    completed, acquired_again = store.effects.begin(
        effect_type="send_ack",
        idempotency_key="submission:S-1",
    )
    assert acquired_again is False
    assert completed["status"] == "completed"
    assert completed["result"] == {"message_id": "M-1"}


def test_submission_and_job_idempotency_survive_concurrency(
    store: Persistence,
) -> None:
    def create_and_enqueue(_: int) -> tuple[str, str, bool]:
        submission, created = store.intake.create_submission(
            source="website",
            external_submission_id="CONCURRENT-1",
            submitted_by="client@example.com",
            body="Create this only once.",
        )
        job, _ = store.jobs.enqueue(
            queue="intake-classification",
            job_type="classify_intake",
            payload={"submission_id": submission["id"]},
            idempotency_key=f"classify:{submission['id']}",
        )
        return submission["id"], job.id, created

    with ThreadPoolExecutor(max_workers=8) as executor:
        outcomes = list(executor.map(create_and_enqueue, range(16)))

    assert len({submission_id for submission_id, _, _ in outcomes}) == 1
    assert len({job_id for _, job_id, _ in outcomes}) == 1
    assert sum(created for _, _, created in outcomes) == 1
    submission_id = outcomes[0][0]
    assert len(store.intake.list_events(submission_id)) == 1
    assert len(store.jobs.list_for_submission(submission_id)) == 1


def test_running_job_is_reclaimed_only_after_lease_expiry(
    store: Persistence,
) -> None:
    start = datetime(2026, 7, 17, tzinfo=timezone.utc)
    job, _ = store.jobs.enqueue(
        queue="intake",
        job_type="classify",
        payload={"submission_id": "S-LEASE"},
        available_at=start,
        idempotency_key="classify:S-LEASE",
    )
    first = store.jobs.claim(
        queue="intake",
        worker_id="worker-a",
        lease_seconds=30,
        now=start,
    )
    assert first is not None
    assert store.jobs.claim(
        queue="intake",
        worker_id="worker-b",
        now=start + timedelta(seconds=29),
    ) is None

    reclaimed = store.jobs.claim(
        queue="intake",
        worker_id="worker-b",
        now=start + timedelta(seconds=30),
    )
    assert reclaimed is not None
    assert reclaimed.id == job.id
    assert reclaimed.attempts == 2
    assert reclaimed.lease_owner == "worker-b"
    assert store.jobs.complete(job.id, worker_id="worker-a") is False
    assert store.jobs.complete(job.id, worker_id="worker-b") is True


def test_failed_effect_can_retry_but_completed_effect_cannot(
    store: Persistence,
) -> None:
    first, acquired = store.effects.begin(
        effect_type="send_email",
        idempotency_key="submission:S-RETRY",
        request={"attempt": 1},
    )
    assert acquired is True
    assert store.effects.complete(first["id"], error="Gmail timed out")

    retry, retry_acquired = store.effects.begin(
        effect_type="send_email",
        idempotency_key="submission:S-RETRY",
        request={"attempt": 2},
    )
    assert retry_acquired is True
    assert retry["id"] == first["id"]
    assert retry["status"] == "started"
    assert retry["request"] == {"attempt": 2}
    assert store.effects.complete(retry["id"], result={"message_id": "M-2"})

    completed, acquired_again = store.effects.begin(
        effect_type="send_email",
        idempotency_key="submission:S-RETRY",
        request={"attempt": 3},
    )
    assert acquired_again is False
    assert completed["result"] == {"message_id": "M-2"}
