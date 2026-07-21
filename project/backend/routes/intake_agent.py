"""REST routes for the LLM-powered Intake & Classification Agent."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status

from backend.auth import Principal, require_roles
from backend.mock_data import get_sample_intake_submissions
from backend.schemas import (
    IntakeAnalysisSummaryResponse,
    IntakeAcceptedResponse,
    IntakeCardResponse,
    IntakeCorrectionRequest,
    IntakeDecisionRequest,
    IntakeRecordsPageResponse,
    IntakeSubmissionDetailResponse,
    IntakeSubmissionPageResponse,
    IntakeSubmissionRequest,
)
from backend.services.intake_workflow import (
    ALL_CATEGORIES,
    enqueue_classification,
    enqueue_routing,
)
from models.task import IntakeSubmission
from persistence import Persistence
from supervisor.supervisor import Supervisor

router = APIRouter()
_supervisor = Supervisor()
_CATEGORIES = (
    "new_project",
    "quote_request",
    "support_issue",
    "general_inquiry",
)


def _card_from_entry(
    submission: IntakeSubmission,
    entry: dict,
) -> IntakeCardResponse:
    """Map a Supervisor execution entry to the public intake card schema."""
    result = entry["result"]
    return IntakeCardResponse(
        submission_id=submission.submission_id,
        submitted_by=submission.submitted_by,
        submitted_at=submission.submitted_at.isoformat(),
        text=submission.text,
        category=str(result.data.get("category") or "unclassified"),
        confidence=result.confidence,
        requires_approval=entry["final_approval_needed"],
        reasoning=result.reasoning,
    )


def classify_intake_submission(
    payload: IntakeSubmissionRequest,
) -> IntakeCardResponse:
    """Classify one dynamic dashboard/webhook submission via the Supervisor."""
    submitted_at = payload.submitted_at or datetime.now(timezone.utc)
    if submitted_at.tzinfo is None:
        submitted_at = submitted_at.replace(tzinfo=timezone.utc)
    submission = IntakeSubmission(
        submission_id=(
            payload.submission_id.strip()
            if payload.submission_id and payload.submission_id.strip()
            else f"INT-{uuid4().hex[:12].upper()}"
        ),
        submitted_by=payload.submitted_by.strip(),
        text=payload.text.strip(),
        submitted_at=submitted_at,
    )
    entry = _supervisor.execute_task(
        "intake_classification",
        submission,
        submission.submission_id,
    )
    return _card_from_entry(submission, entry)


def get_persistence() -> Persistence:
    return Persistence()


@router.post(
    "/classify",
    response_model=IntakeAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def classify_intake_agent(
    payload: IntakeSubmissionRequest,
) -> IntakeAcceptedResponse:
    """Persist and enqueue a dashboard inquiry without calling Claude inline."""
    external_id = (
        payload.submission_id.strip()
        if payload.submission_id and payload.submission_id.strip()
        else f"INT-{uuid4().hex[:12].upper()}"
    )
    store = get_persistence()
    submission, created = store.intake.create_submission(
        source="dashboard",
        external_submission_id=external_id,
        submitted_by=payload.submitted_by.strip(),
        body=payload.text.strip(),
        payload=payload.model_dump(mode="json"),
    )
    if created:
        enqueue_classification(store, submission["id"])
        submission = store.intake.transition(
            submission["id"],
            status="classification_queued",
            event_type="accepted",
            data={"source": "dashboard"},
        ) or submission
    return _accepted(submission, replay=not created)


@router.get("/run", response_model=IntakeAnalysisSummaryResponse)
def run_intake_agent() -> IntakeAnalysisSummaryResponse:
    """Classify sample inquiries through the Supervisor and summarize results."""
    submissions = get_sample_intake_submissions()
    batch = _supervisor.run_batch(
        "intake_classification",
        submissions,
        [submission.submission_id for submission in submissions],
    )

    category_counts = {category: 0 for category in _CATEGORIES}
    cards: list[IntakeCardResponse] = []
    for submission, entry in zip(submissions, batch["results"]):
        card = _card_from_entry(submission, entry)
        category = card.category
        category_counts[category] = category_counts.get(category, 0) + 1
        cards.append(card)

    return IntakeAnalysisSummaryResponse(
        total_submissions=batch["total"],
        category_counts=category_counts,
        needs_review_count=batch["needs_approval_count"],
        results=cards,
    )


@router.get("/submissions", response_model=IntakeSubmissionPageResponse)
def list_intake_submissions(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    intake_status: str | None = Query(default=None, alias="status"),
) -> IntakeSubmissionPageResponse:
    store = get_persistence()
    items, total = store.intake.list_submissions(
        limit=limit, offset=offset, status=intake_status
    )
    return IntakeSubmissionPageResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
        next_offset=offset + limit if offset + limit < total else None,
    )


@router.get(
    "/submissions/{submission_id}",
    response_model=IntakeSubmissionDetailResponse,
)
def get_intake_submission(submission_id: str) -> dict:
    submission = get_persistence().intake.get_submission(submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Intake submission not found")
    return submission


@router.get(
    "/submissions/{submission_id}/events",
    response_model=IntakeRecordsPageResponse,
)
def list_intake_events(
    submission_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IntakeRecordsPageResponse:
    store = get_persistence()
    _require_submission(store, submission_id)
    items = store.intake.list_events(submission_id, limit=limit, offset=offset)
    return _records_page(items, limit, offset)


@router.get(
    "/submissions/{submission_id}/attempts",
    response_model=IntakeRecordsPageResponse,
)
def list_intake_attempts(
    submission_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> IntakeRecordsPageResponse:
    store = get_persistence()
    _require_submission(store, submission_id)
    items = store.classifications.list(submission_id, limit=limit, offset=offset)
    return _records_page(items, limit, offset)


_reviewer = require_roles("reviewer", "admin")


@router.post(
    "/submissions/{submission_id}/approve",
    response_model=IntakeSubmissionDetailResponse,
)
def approve_intake(
    submission_id: str,
    payload: IntakeDecisionRequest,
    principal: Principal = Depends(_reviewer),
) -> dict:
    return _review_and_enqueue(
        submission_id, payload.version, principal, event_type="approved"
    )


@router.post(
    "/submissions/{submission_id}/reject",
    response_model=IntakeSubmissionDetailResponse,
)
def reject_intake(
    submission_id: str,
    payload: IntakeDecisionRequest,
    principal: Principal = Depends(_reviewer),
) -> dict:
    store = get_persistence()
    _require_submission(store, submission_id)
    updated = store.intake.transition(
        submission_id,
        status="rejected",
        event_type="rejected",
        data={"actor": principal.email},
        expected_version=payload.version,
        expected_statuses=("awaiting_approval",),
        fields={
            "approval_status": "rejected",
            "approval_actor": principal.email,
            "approval_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "not_started",
        },
        completed=True,
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="Intake version or state conflict")
    return updated


@router.post(
    "/submissions/{submission_id}/correct-category",
    response_model=IntakeSubmissionDetailResponse,
)
def correct_intake_category(
    submission_id: str,
    payload: IntakeCorrectionRequest,
    principal: Principal = Depends(_reviewer),
) -> dict:
    category = payload.category.strip().lower()
    if category not in ALL_CATEGORIES - {"unclassified"}:
        raise HTTPException(status_code=422, detail="Invalid Intake category")
    return _review_and_enqueue(
        submission_id,
        payload.version,
        principal,
        event_type="category_corrected",
        category=category,
    )


@router.post(
    "/jobs/{job_id}/retry",
    response_model=IntakeAcceptedResponse,
)
def retry_intake_job(
    job_id: str,
    principal: Principal = Depends(_reviewer),
) -> IntakeAcceptedResponse:
    store = get_persistence()
    original = store.jobs.get(job_id)
    if original is None or original.queue not in {
        "intake-classification",
        "intake-routing",
    }:
        raise HTTPException(status_code=404, detail="Intake job not found")
    retried = store.jobs.retry_dead(job_id)
    if retried is None:
        raise HTTPException(status_code=409, detail="Only dead Intake jobs can be retried")
    submission_id = str(retried.payload.get("submission_id") or "")
    submission = _require_submission(store, submission_id)
    updated = store.intake.transition(
        submission_id,
        status=(
            "classification_queued"
            if retried.queue == "intake-classification"
            else "routing_queued"
        ),
        event_type="job_retried",
        data={"job_id": job_id, "actor": principal.email},
        fields={"execution_status": "not_started"}
        if retried.queue == "intake-routing"
        else None,
    )
    return _accepted(updated or submission, replay=False)


def _review_and_enqueue(
    submission_id: str,
    version: int,
    principal: Principal,
    *,
    event_type: str,
    category: str | None = None,
) -> dict:
    store = get_persistence()
    current = _require_submission(store, submission_id)
    chosen = category or current.get("classification_category")
    if chosen not in ALL_CATEGORIES - {"unclassified"}:
        raise HTTPException(status_code=422, detail="A routable category is required")
    updated = store.intake.transition(
        submission_id,
        status="routing_queued",
        event_type=event_type,
        data={"actor": principal.email, "category": chosen},
        expected_version=version,
        expected_statuses=("awaiting_approval",),
        fields={
            "classification_category": chosen,
            "approval_status": "approved",
            "approval_actor": principal.email,
            "approval_at": datetime.now(timezone.utc).isoformat(),
            "execution_status": "not_started",
        },
    )
    if updated is None:
        raise HTTPException(status_code=409, detail="Intake version or state conflict")
    enqueue_routing(store, submission_id, version=int(updated["version"]))
    return updated


def _require_submission(store: Persistence, submission_id: str) -> dict:
    submission = store.intake.get_submission(submission_id)
    if submission is None:
        raise HTTPException(status_code=404, detail="Intake submission not found")
    return submission


def _accepted(submission: dict, *, replay: bool) -> IntakeAcceptedResponse:
    return IntakeAcceptedResponse(
        submission_id=submission["id"],
        status=submission["status"],
        status_url=f"/api/intake-agent/submissions/{submission['id']}",
        replay=replay,
    )


def _records_page(items: list[dict], limit: int, offset: int) -> IntakeRecordsPageResponse:
    return IntakeRecordsPageResponse(
        items=items,
        limit=limit,
        offset=offset,
        next_offset=offset + limit if len(items) == limit else None,
    )
