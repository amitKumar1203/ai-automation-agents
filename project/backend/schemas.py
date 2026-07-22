"""Pydantic request/response schemas for the REST API."""

from datetime import datetime

from pydantic import BaseModel, Field


class AgentCardResponse(BaseModel):
    """Single thread analysis result formatted for the dashboard UI."""

    thread_id: str
    status: str  # "OK" | "AT_RISK" | "UNANSWERED" | "CRITICAL"
    last_sender: str  # "team" | "internal" | "client"
    last_message_text: str
    last_message_timestamp: str  # ISO format
    hours_pending: float
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    client_email: str = ""
    subject: str = ""
    priority: str = "normal"  # "high" | "normal"
    urgency_keywords: list[str] = Field(default_factory=list)
    draft_reply: str = ""


class AnalysisSummaryResponse(BaseModel):
    """Aggregated analysis across all sample threads."""

    total_threads: int
    unanswered_count: int
    at_risk_count: int = 0
    critical_count: int = 0
    ok_count: int
    results: list[AgentCardResponse]
    owner_notify: dict | None = None
    client_ack: dict | None = None


class GmailProfileResponse(BaseModel):
    """Connected Gmail account identity for the dashboard header."""

    email: str = ""
    name: str = ""
    picture: str | None = None
    picture_source: str = "none"


class VendorCardResponse(BaseModel):
    """Single vendor quote request analysis result for the dashboard UI."""

    vendor_name: str
    project_id: str
    status: str  # "OK" | "WAITING" | "SEND_REMINDER" | "ESCALATE" | "INVALID_DATE"
    hours_pending: float
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str


class VendorAnalysisSummaryResponse(BaseModel):
    """Aggregated analysis across all sample vendor quote requests."""

    total_requests: int
    waiting_count: int
    reminder_count: int
    escalate_count: int
    results: list[VendorCardResponse]


class PODraftResponse(BaseModel):
    """Draft purchase order prepared by the PO automation agent."""

    project_id: str
    client_name: str
    vendor_name: str
    estimated_amount: float
    generated_at: str  # ISO format


class POCardResponse(BaseModel):
    """Single project PO analysis result for the dashboard UI."""

    project_id: str
    client_name: str
    vendor_name: str
    status: str  # "ALREADY_EXISTS" | "PO_READY_FOR_RELEASE"
    estimated_amount: float
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    draft_po: PODraftResponse | None = None


class POAnalysisSummaryResponse(BaseModel):
    """Aggregated analysis across all sample project approvals."""

    total_projects: int
    already_exists_count: int
    ready_for_release_count: int
    results: list[POCardResponse]


class ArtworkCardResponse(BaseModel):
    """Single artwork verification result for the dashboard UI."""

    project_id: str
    status: str  # "MATCH" | "MISMATCH"
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    artwork_width_inches: float
    artwork_height_inches: float
    spec_width_inches: float
    spec_height_inches: float
    width_diff: float
    height_diff: float
    entry_id: str | None = None
    final_approval_needed: bool | None = None


class ArtworkNumericVerifyRequest(BaseModel):
    """User-entered dimensions for rule-based artwork verification."""

    project_id: str = ""
    artwork_width_inches: float = Field(gt=0)
    artwork_height_inches: float = Field(gt=0)
    spec_width_inches: float = Field(gt=0)
    spec_height_inches: float = Field(gt=0)
    submitted_by: str = "dashboard"


class ArtworkAnalysisSummaryResponse(BaseModel):
    """Aggregated analysis across artwork submissions (legacy batch shape)."""

    total_submissions: int
    match_count: int
    mismatch_count: int
    results: list[ArtworkCardResponse]


class ArtworkVisionResultResponse(BaseModel):
    """Single vision-based artwork verification result (AgentResult-shaped)."""

    data: dict
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    entry_id: str | None = None
    final_approval_needed: bool | None = None


class Phase3VisionResultResponse(BaseModel):
    """Phase 3 on-demand vision agent result (AgentResult-shaped)."""

    data: dict
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    entry_id: str | None = None
    final_approval_needed: bool | None = None


class FollowUpCardResponse(BaseModel):
    """Single project activity result for Automated Follow-Up."""

    project_id: str
    project_name: str
    stage: str = ""
    status: str  # OK | SEND_FOLLOWUP | ESCALATE | INVALID_DATE
    days_inactive: float
    owner_email: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    entry_id: str | None = None


class FollowUpAnalysisSummaryResponse(BaseModel):
    """Aggregated Automated Follow-Up batch."""

    total_projects: int
    ok_count: int
    followup_count: int
    escalate_count: int
    results: list[FollowUpCardResponse]


class StorefrontCardResponse(BaseModel):
    """Single Storefront Search result."""

    project_id: str
    project_name: str
    store_address: str
    status: str
    image_url: str = ""
    image_source: str = ""
    place_name: str = ""
    match_confidence: float | None = None
    monday_item_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    entry_id: str | None = None


class StorefrontAnalysisSummaryResponse(BaseModel):
    """Aggregated Storefront Search batch."""

    total_projects: int
    found_count: int
    low_confidence_count: int
    not_found_count: int
    skipped_count: int
    results: list[StorefrontCardResponse]


class InstallerCardResponse(BaseModel):
    """Single Installer Matching result."""

    project_id: str
    project_name: str
    install_region: str
    install_date: str = ""
    status: str
    recommended_installer: str = ""
    recommended_installer_email: str = ""
    recommended_installer_region: str = ""
    match_type: str = ""
    available_capacity: int | None = None
    match_confidence: float | None = None
    monday_item_id: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str
    entry_id: str | None = None


class InstallerAnalysisSummaryResponse(BaseModel):
    """Aggregated Installer Matching batch."""

    total_projects: int
    matched_count: int
    low_confidence_count: int
    no_match_count: int
    skipped_count: int
    results: list[InstallerCardResponse]


class IntakeCardResponse(BaseModel):
    """Single LLM-classified client inquiry for the dashboard."""

    submission_id: str
    submitted_by: str
    submitted_at: str
    text: str
    category: str
    confidence: float = Field(ge=0.0, le=1.0)
    requires_approval: bool
    reasoning: str


class IntakeSubmissionRequest(BaseModel):
    """Dynamic intake payload accepted from the dashboard or a webhook."""

    submitted_by: str = Field(min_length=1, max_length=320)
    text: str = Field(min_length=1, max_length=10_000)
    submission_id: str | None = Field(default=None, max_length=120)
    submitted_at: datetime | None = None


class IntakeAcceptedResponse(BaseModel):
    """Durable asynchronous acceptance response."""

    submission_id: str
    status: str
    status_url: str
    replay: bool = False


class IntakeDecisionRequest(BaseModel):
    """Optimistic-lock input for reviewer/admin Intake decisions."""

    version: int = Field(ge=1)


class IntakeCorrectionRequest(IntakeDecisionRequest):
    category: str


class IntakeSubmissionDetailResponse(BaseModel):
    """Current durable state for one Intake submission."""

    id: str
    source: str
    external_submission_id: str
    submitted_by: str
    body: str
    payload: dict
    status: str
    classification_category: str | None = None
    classification_confidence: float | None = None
    classification_reasoning: str | None = None
    classification_model: str | None = None
    approval_status: str
    approval_actor: str | None = None
    approval_at: str | datetime | None = None
    execution_status: str
    monday_result: dict | None = None
    notification_result: dict | None = None
    version: int
    created_at: str | datetime
    updated_at: str | datetime
    completed_at: str | datetime | None = None


class IntakeSubmissionPageResponse(BaseModel):
    items: list[IntakeSubmissionDetailResponse]
    total: int
    limit: int
    offset: int
    next_offset: int | None = None


class IntakeRecordsPageResponse(BaseModel):
    items: list[dict]
    limit: int
    offset: int
    next_offset: int | None = None


class IntakeAnalysisSummaryResponse(BaseModel):
    """Aggregated intake classifications and review counts."""

    total_submissions: int
    category_counts: dict[str, int]
    needs_review_count: int
    results: list[IntakeCardResponse]


class AuditResultSnapshot(BaseModel):
    """Nested agent result fields stored on an audit log entry."""

    data: dict
    confidence: float
    reasoning: str


class AuditLogEntryResponse(BaseModel):
    """Single persisted audit log entry returned by GET /api/audit-log."""

    id: str
    agent_name: str
    task_id: str
    timestamp: str
    input: dict | None = None
    result: AuditResultSnapshot
    final_approval_needed: bool
    approval_status: str
    approved_by: str | None = None
    approved_at: str | None = None
    execution_status: str | None = None
    execution_detail: str | None = None


class AuditLogPageResponse(BaseModel):
    """Paginated audit log returned by GET /api/audit-log."""

    items: list[AuditLogEntryResponse]
    total: int
    limit: int
    offset: int
    next_offset: int | None = None
    counts: dict[str, int] | None = None


class ApprovalActionRequest(BaseModel):
    """Request body for approve/reject actions on an audit entry."""

    approved_by: str = Field(min_length=1, description="Who is approving or rejecting")


class DashboardOverviewResponse(BaseModel):
    """Lightweight management overview for the home dashboard."""

    pending_approval_count: int
    pending_by_agent: dict[str, int]
    last_run_by_agent: dict[str, str]
    recent_entries: list[AuditLogEntryResponse]
    recent_failures: list[AuditLogEntryResponse]
    open_escalations: list[AuditLogEntryResponse] = Field(default_factory=list)
    queue: dict = Field(default_factory=dict)
    write_back_mode: str
    kpis: dict = Field(default_factory=dict)
