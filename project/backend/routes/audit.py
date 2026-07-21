"""REST routes for the supervisor audit log."""

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.auth import Principal, require_roles
from backend.schemas import (
    ApprovalActionRequest,
    AuditLogEntryResponse,
    AuditLogPageResponse,
)
from supervisor.action_executor import execute_approved_action
from supervisor.audit_log import (
    count_audit_log,
    get_audit_entry,
    get_audit_log,
    get_audit_log_counts,
    update_approval_status,
    update_execution_outcome,
)

router = APIRouter()
_reviewer = require_roles("reviewer", "admin")


def _approved_by(principal: Principal, body: ApprovalActionRequest) -> str:
    """Prefer the signed-in operator email; keep local test fallback."""
    if principal.email != "local@localhost":
        return principal.email
    return body.approved_by.strip()


@router.get("", response_model=AuditLogPageResponse)
def read_audit_log(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    status: str = Query(
        default="pending",
        pattern="^(pending|approved|rejected|all)$",
        description="Filter: pending (needs review), approved, rejected, or all",
    ),
) -> AuditLogPageResponse:
    """Return a page of audit entries for the selected review tab."""
    pending_review_only = status == "pending"
    approval_status = None
    if status == "approved":
        approval_status = "APPROVED"
    elif status == "rejected":
        approval_status = "REJECTED"

    total = count_audit_log(
        approval_status=approval_status,
        pending_review_only=pending_review_only,
        dedupe_by_task=pending_review_only,
    )
    items = get_audit_log(
        limit=limit,
        offset=offset,
        approval_status=approval_status,
        pending_review_only=pending_review_only,
        dedupe_by_task=pending_review_only,
        prioritize_pending=status == "all",
    )
    next_offset = offset + limit if offset + limit < total else None
    counts = get_audit_log_counts() if offset == 0 else None
    return AuditLogPageResponse(
        items=[AuditLogEntryResponse.model_validate(entry) for entry in items],
        total=total,
        limit=limit,
        offset=offset,
        next_offset=next_offset,
        counts=counts,
    )


@router.post("/{entry_id}/approve", response_model=AuditLogEntryResponse)
def approve_audit_entry(
    entry_id: str,
    body: ApprovalActionRequest,
    principal: Principal = Depends(_reviewer),
) -> AuditLogEntryResponse:
    """Approve a PENDING audit entry and run post-approval write-back."""
    return _apply_decision(entry_id, "APPROVED", _approved_by(principal, body))


@router.post("/{entry_id}/reject", response_model=AuditLogEntryResponse)
def reject_audit_entry(
    entry_id: str,
    body: ApprovalActionRequest,
    principal: Principal = Depends(_reviewer),
) -> AuditLogEntryResponse:
    """Reject a PENDING audit entry that requires human review."""
    return _apply_decision(entry_id, "REJECTED", _approved_by(principal, body))


def _apply_decision(
    entry_id: str,
    new_status: str,
    approved_by: str,
) -> AuditLogEntryResponse:
    """Shared approve/reject handler with 404 / 409 mapping."""
    existing = get_audit_entry(entry_id)
    if existing is None:
        raise HTTPException(
            status_code=404,
            detail=f"Audit entry '{entry_id}' not found",
        )
    if existing["approval_status"] != "PENDING":
        raise HTTPException(
            status_code=409,
            detail=(
                f"Audit entry '{entry_id}' is already "
                f"{existing['approval_status']} and cannot be changed"
            ),
        )

    updated = update_approval_status(entry_id, new_status, approved_by.strip())
    if updated is None:
        raise HTTPException(
            status_code=409,
            detail=f"Audit entry '{entry_id}' is no longer PENDING",
        )

    if new_status == "APPROVED":
        outcome = execute_approved_action(updated)
        detail = outcome.get("execution_detail")
        updated = update_execution_outcome(
            entry_id,
            str(outcome["execution_status"]),
            detail,
        ) or updated

    return AuditLogEntryResponse.model_validate(updated)
