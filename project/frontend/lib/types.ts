/** Status returned for each email thread analysis result. */
export type ThreadStatus = "UNANSWERED" | "OK";

/** Status returned for each vendor quote request analysis result. */
export type VendorStatus =
  | "OK"
  | "WAITING"
  | "SEND_REMINDER"
  | "ESCALATE"
  | "INVALID_DATE";

/** Status returned for each PO automation analysis result. */
export type POStatus = "ALREADY_EXISTS" | "PO_READY_FOR_RELEASE";

/** Status returned for each artwork verification result. */
export type ArtworkStatus = "MATCH" | "MISMATCH" | "UNCERTAIN";

/** Status returned for Automated Follow-Up. */
export type FollowUpStatus =
  | "OK"
  | "SEND_FOLLOWUP"
  | "ESCALATE"
  | "INVALID_DATE";

/** Status returned for Storefront Search. */
export type StorefrontStatus =
  | "FOUND"
  | "LOW_CONFIDENCE"
  | "NOT_FOUND"
  | "ALREADY_ATTACHED"
  | "MISSING_ADDRESS"
  | "SEARCH_FAILED";

/** Status returned for Installer Matching. */
export type InstallerStatus =
  | "MATCHED"
  | "LOW_CONFIDENCE"
  | "NO_MATCH"
  | "ALREADY_ASSIGNED"
  | "MISSING_REGION";

/** Categories returned by the Intake & Classification Agent. */
export type IntakeCategory =
  | "new_project"
  | "quote_request"
  | "support_issue"
  | "general_inquiry"
  | "unclassified";

/** Phase 3 vision agent statuses. */
export type Phase3Status =
  | "READY_FOR_REVIEW"
  | "APPROVED_INTERNAL"
  | "READY_FOR_EXTERNAL_SHARE"
  | "NEEDS_REVISION"
  | "ANALYZED"
  | "ISSUES_FOUND"
  | "PASS"
  | "FAIL"
  | "NEEDS_REVIEW";

/** Union of all agent status values used by StatusPill. */
export type AgentStatus =
  | ThreadStatus
  | VendorStatus
  | POStatus
  | ArtworkStatus
  | FollowUpStatus
  | StorefrontStatus
  | InstallerStatus
  | IntakeCategory
  | Phase3Status
  | "LOW_CONFIDENCE";

/** Sender category from Gmail domain matching. */
export type EmailSenderType = "team" | "internal" | "client";

/** Single thread result from the email agent analysis endpoint. */
export interface ThreadResult {
  thread_id: string;
  status: ThreadStatus;
  /** "team" | "internal" | "client" (empty string for threads with no messages). */
  last_sender: EmailSenderType | string;
  last_message_text: string;
  last_message_timestamp: string;
  hours_pending: number;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  /** Parsed client From address when available. */
  client_email?: string;
  /** Thread subject from Gmail headers. */
  subject?: string;
}

/** Connected Gmail account for the app header avatar. */
export interface GmailProfile {
  email: string;
  name: string;
  picture: string | null;
  picture_source: string;
}

/** Single result from Automated Follow-Up agent. */
export interface FollowUpCardData {
  project_id: string;
  project_name: string;
  stage: string;
  status: FollowUpStatus;
  days_inactive: number;
  owner_email: string;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  entry_id?: string | null;
}

/** Aggregated response from GET /api/followup-agent/run. */
export interface FollowUpAnalysisSummary {
  total_projects: number;
  ok_count: number;
  followup_count: number;
  escalate_count: number;
  results: FollowUpCardData[];
}

/** Single result from Storefront Search agent. */
export interface StorefrontCardData {
  project_id: string;
  project_name: string;
  store_address: string;
  status: StorefrontStatus;
  image_url: string;
  image_source: string;
  place_name: string;
  match_confidence: number | null;
  monday_item_id: string | null;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  entry_id?: string | null;
}

export interface StorefrontAnalysisSummary {
  total_projects: number;
  found_count: number;
  low_confidence_count: number;
  not_found_count: number;
  skipped_count: number;
  results: StorefrontCardData[];
}

/** Single result from Installer Matching agent. */
export interface InstallerCardData {
  project_id: string;
  project_name: string;
  install_region: string;
  install_date: string;
  status: InstallerStatus;
  recommended_installer: string;
  recommended_installer_email: string;
  recommended_installer_region: string;
  match_type: string;
  available_capacity: number | null;
  match_confidence: number | null;
  monday_item_id: string | null;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  entry_id?: string | null;
}

export interface InstallerAnalysisSummary {
  total_projects: number;
  matched_count: number;
  low_confidence_count: number;
  no_match_count: number;
  skipped_count: number;
  results: InstallerCardData[];
}

/** Single LLM-classified client inquiry. */
export interface IntakeCardData {
  submission_id: string;
  submitted_by: string;
  submitted_at: string;
  text: string;
  category: IntakeCategory;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
}

/** Dynamic inquiry payload submitted from the dashboard. */
export interface IntakeSubmissionInput {
  submitted_by: string;
  text: string;
  submission_id?: string;
  submitted_at?: string;
}

/** Durable Intake workflow states returned by the asynchronous API. */
export type IntakeStatus =
  | "received"
  | "classification_queued"
  | "classification_running"
  | "classification_retrying"
  | "classification_dead"
  | "awaiting_approval"
  | "routing_queued"
  | "routing_running"
  | "routing_retrying"
  | "routing_dead"
  | "completed"
  | "rejected"
  | string;

export type OperatorRole = "operator" | "reviewer" | "admin";

export interface OperatorAccount {
  email: string;
  display_name: string | null;
  role: OperatorRole;
  active: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface CategoryOwner {
  category: string;
  email: string;
  source: string;
}

export interface ApprovalRule {
  agent_name: string;
  risky_statuses: string[];
  confidence_threshold: number;
}

export interface AdminConfig {
  write_back_mode: string;
  notify_owner_email: string;
  followup_notify_email: string;
  category_owners: CategoryOwner[];
  approval_rules: ApprovalRule[];
}

export interface ConfigAuditEntry {
  id: string;
  config_key: string;
  old_value: string | null;
  new_value: string;
  changed_by: string;
  changed_at: string;
}

export interface IntakeAcceptedResponse {
  submission_id: string;
  status: IntakeStatus;
  status_url: string;
  replay: boolean;
}

export interface IntakeSubmissionDetail {
  id: string;
  source: string;
  external_submission_id: string;
  submitted_by: string;
  body: string;
  payload: Record<string, unknown>;
  status: IntakeStatus;
  classification_category: IntakeCategory | null;
  classification_confidence: number | null;
  classification_reasoning: string | null;
  classification_model: string | null;
  approval_status: string;
  approval_actor: string | null;
  approval_at: string | null;
  execution_status: string;
  monday_result: Record<string, unknown> | null;
  notification_result: Record<string, unknown> | null;
  version: number;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
}

export interface IntakeSubmissionPage {
  items: IntakeSubmissionDetail[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
}

export interface IntakeEvent {
  id: string;
  submission_id: string;
  event_type: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface IntakeAttempt {
  id: string;
  submission_id: string;
  attempt_number: number;
  model: string;
  status: string;
  category: IntakeCategory | null;
  confidence: number | null;
  reasoning: string | null;
  error: string | null;
  started_at: string;
  completed_at: string | null;
}

export interface IntakeRecordsPage<T> {
  items: T[];
  limit: number;
  offset: number;
  next_offset: number | null;
}

/** Aggregated response from GET /api/intake-agent/run. */
export interface IntakeAnalysisSummary {
  total_submissions: number;
  category_counts: Record<string, number>;
  needs_review_count: number;
  results: IntakeCardData[];
}

/** Aggregated response from GET /api/email-agent/run. */
export interface AnalysisSummaryResponse {
  total_threads: number;
  unanswered_count: number;
  ok_count: number;
  results: ThreadResult[];
}

/** Single vendor result from GET /api/vendor-agent/run. */
export interface VendorCardData {
  vendor_name: string;
  project_id: string;
  status: VendorStatus;
  hours_pending: number;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
}

/** Aggregated response from GET /api/vendor-agent/run. */
export interface VendorAnalysisSummary {
  total_requests: number;
  waiting_count: number;
  reminder_count: number;
  escalate_count: number;
  results: VendorCardData[];
}

/** Nested draft PO payload from the PO automation agent. */
export interface DraftPO {
  project_id: string;
  client_name: string;
  vendor_name: string;
  estimated_amount: number;
  generated_at: string;
}

/** Single PO result from GET /api/po-agent/run. */
export interface POCardData {
  project_id: string;
  client_name: string;
  status: POStatus;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  draft_po: DraftPO | null;
}

/** Aggregated response from GET /api/po-agent/run. */
export interface POAnalysisSummary {
  total_projects: number;
  already_exists_count: number;
  ready_for_release_count: number;
  results: POCardData[];
}

/** Single artwork result from GET /api/artwork-agent/run. */
export interface ArtworkCardData {
  project_id: string;
  status: ArtworkStatus;
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  artwork_width_inches: number;
  artwork_height_inches: number;
  spec_width_inches: number;
  spec_height_inches: number;
  width_diff: number;
  height_diff: number;
}

/** Aggregated response from GET /api/artwork-agent/run. */
export interface ArtworkAnalysisSummary {
  total_submissions: number;
  match_count: number;
  mismatch_count: number;
  results: ArtworkCardData[];
}

/** Response from POST /api/artwork-agent/verify-vision. */
export interface ArtworkVisionResult {
  data: {
    project_id?: string;
    status?: ArtworkStatus | string;
    vision_reasoning?: string;
    dimensions_visible?: boolean;
    [key: string]: unknown;
  };
  confidence: number;
  requires_approval: boolean;
  reasoning: string;
  entry_id?: string | null;
  final_approval_needed?: boolean | null;
}

/** Response from Phase 3 vision agent endpoints. */
export type Phase3VisionResult = ArtworkVisionResult;

/** Agent result snapshot stored in the audit log. */
export interface AuditLogResult {
  data: Record<string, unknown>;
  confidence: number;
  reasoning: string;
  requires_approval?: boolean;
}

/** Single audit log entry from GET /api/audit-log. */
export interface AuditLogEntry {
  id: string;
  timestamp: string;
  agent_name: string;
  task_id: string;
  result: AuditLogResult;
  final_approval_needed: boolean;
  approval_status: string;
  approved_by: string | null;
  approved_at: string | null;
  execution_status: string | null;
  execution_detail: string | null;
}

/** Paginated audit log from GET /api/audit-log. */
export interface AuditLogPage {
  items: AuditLogEntry[];
  total: number;
  limit: number;
  offset: number;
  next_offset: number | null;
  counts?: {
    pending_review: number;
    approved: number;
    rejected: number;
    all: number;
  } | null;
}

export type AuditLogTab = "pending" | "approved" | "rejected" | "all";

/** Overview payload from GET /api/dashboard/overview. */
export interface DashboardOverview {
  pending_approval_count: number;
  pending_by_agent: Record<string, number>;
  last_run_by_agent: Record<string, string>;
  recent_entries: AuditLogEntry[];
  recent_failures: AuditLogEntry[];
  open_escalations?: AuditLogEntry[];
  queue?: {
    totals?: Record<string, number>;
    by_queue?: Record<string, Record<string, number>>;
  };
  write_back_mode: string;
  kpis: Record<string, Record<string, unknown>>;
}

/** Live supervisor status from GET /api/supervisor/status. */
export interface SupervisorStatus {
  ok: boolean;
  pending_approval_count: number;
  pending_by_agent: Record<string, number>;
  last_run_by_agent: Record<string, string>;
  recent_failures: AuditLogEntry[];
  open_escalations: AuditLogEntry[];
  queue: {
    totals?: Record<string, number>;
    by_queue?: Record<string, Record<string, number>>;
  };
  write_back_mode: string;
  kpis: Record<string, Record<string, unknown>>;
  event_sources: string[];
}

/** Background job row from GET /api/supervisor/jobs. */
export interface SupervisorJob {
  id: string;
  queue: string;
  job_type: string;
  status: string;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  agent_name?: string | null;
  entry_id?: string | null;
  payload?: Record<string, unknown>;
}

export interface SupervisorJobsResponse {
  ok: boolean;
  total: number;
  jobs: SupervisorJob[];
}

/** End-to-end task view from GET /api/supervisor/tasks/{task_id}. */
export interface SupervisorTaskStatus {
  task_id: string;
  found: boolean;
  latest: AuditLogEntry | null;
  audit_entries: AuditLogEntry[];
  jobs: SupervisorJob[];
  has_escalation: boolean;
  pending_approval: boolean;
  execution_status: string | null;
  approval_status: string | null;
}
