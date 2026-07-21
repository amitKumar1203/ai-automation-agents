import type {
  AdminConfig,
  AnalysisSummaryResponse,
  ArtworkCardData,
  ArtworkVisionResult,
  AuditLogEntry,
  AuditLogPage,
  DashboardOverview,
  FollowUpAnalysisSummary,
  GmailProfile,
  IntakeAcceptedResponse,
  IntakeAnalysisSummary,
  IntakeAttempt,
  IntakeCardData,
  IntakeCategory,
  IntakeEvent,
  IntakeRecordsPage,
  IntakeSubmissionDetail,
  IntakeSubmissionInput,
  IntakeSubmissionPage,
  OperatorAccount,
  OperatorRole,
  POAnalysisSummary,
  InstallerAnalysisSummary,
  StorefrontAnalysisSummary,
  VendorAnalysisSummary,
} from "./types";

/**
 * Browser calls the Next.js BFF proxy (server attaches API_KEY).
 * Set NEXT_PUBLIC_USE_DIRECT_API=1 only for local debugging against :8000.
 */
const USE_DIRECT =
  process.env.NODE_ENV === "development" &&
  (process.env.NEXT_PUBLIC_USE_DIRECT_API === "1" ||
    process.env.NEXT_PUBLIC_USE_DIRECT_API === "true");

const API_BASE_URL = USE_DIRECT
  ? (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
  : "";

function apiPath(path: string): string {
  if (USE_DIRECT) {
    return `${API_BASE_URL}${path}`;
  }
  // /api/email-agent/run → /api/backend/email-agent/run
  return path.replace(/^\/api\//, "/api/backend/");
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function requestId(): string {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
}

async function fetchJson<T>(
  path: string,
  options: { signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(apiPath(path), {
    cache: "no-store",
    signal: options.signal,
    headers: { "X-Correlation-ID": requestId() },
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, `API ${response.status}: ${detail}`);
  }

  return response.json() as Promise<T>;
}

async function postJson<T>(
  path: string,
  body: unknown,
  options: { idempotencyKey?: string; signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(apiPath(path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": requestId(),
      ...(options.idempotencyKey
        ? { "Idempotency-Key": options.idempotencyKey }
        : {}),
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, `API ${response.status}: ${detail}`);
  }

  return response.json() as Promise<T>;
}

async function patchJson<T>(
  path: string,
  body: unknown,
  options: { signal?: AbortSignal } = {},
): Promise<T> {
  const response = await fetch(apiPath(path), {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": requestId(),
    },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: options.signal,
  });

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") {
        detail = payload.detail;
      }
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, `API ${response.status}: ${detail}`);
  }

  return response.json() as Promise<T>;
}

/** Optional filters for live Gmail demo scoping. */
export type EmailAgentRunOptions = {
  senderFilter?: string;
  keywordFilter?: string;
};

/** Fetch email agent analysis from live Gmail. */
export async function fetchEmailAgentRun(
  options: EmailAgentRunOptions = {},
): Promise<AnalysisSummaryResponse> {
  const params = new URLSearchParams({ source: "gmail" });
  const senderFilter = options.senderFilter?.trim();
  const keywordFilter = options.keywordFilter?.trim();
  if (senderFilter) {
    params.set("sender_filter", senderFilter);
  }
  if (keywordFilter) {
    params.set("keyword_filter", keywordFilter);
  }
  return fetchJson<AnalysisSummaryResponse>(
    `/api/email-agent/run?${params.toString()}`,
  );
}

/** Connected Gmail account (email / name / Google profile photo when scoped). */
export async function fetchGmailProfile(): Promise<GmailProfile> {
  return fetchJson<GmailProfile>("/api/email-agent/profile");
}

/** Fetch vendor follow-up agent analysis from live Monday.com. */
export async function fetchVendorAgentRun(): Promise<VendorAnalysisSummary> {
  return fetchJson<VendorAnalysisSummary>(
    "/api/vendor-agent/run?source=monday",
  );
}

/** Fetch PO automation agent analysis from live Salesforce. */
export async function fetchPOAgentRun(): Promise<POAnalysisSummary> {
  return fetchJson<POAnalysisSummary>(
    "/api/po-agent/run?source=salesforce",
  );
}

/** Fetch Automated Follow-Up analysis from live Salesforce projects. */
export async function fetchFollowUpAgentRun(): Promise<FollowUpAnalysisSummary> {
  return fetchJson<FollowUpAnalysisSummary>(
    "/api/followup-agent/run?source=salesforce",
  );
}

/** Fetch Storefront Search results from the live Monday board. */
export async function fetchStorefrontAgentRun(): Promise<StorefrontAnalysisSummary> {
  return fetchJson<StorefrontAnalysisSummary>("/api/storefront-agent/run");
}

/** Fetch Installer Matching results from live Monday boards. */
export async function fetchInstallerAgentRun(): Promise<InstallerAnalysisSummary> {
  return fetchJson<InstallerAnalysisSummary>("/api/installer-agent/run");
}

/** Fetch mock client inquiries classified by Claude through the Supervisor. */
export async function fetchIntakeAgentRun(): Promise<IntakeAnalysisSummary> {
  return fetchJson<IntakeAnalysisSummary>("/api/intake-agent/run");
}

/** Classify one dynamic inquiry submitted from the dashboard. */
export async function classifyIntakeSubmission(
  body: IntakeSubmissionInput,
  options: { idempotencyKey?: string; signal?: AbortSignal } = {},
): Promise<IntakeAcceptedResponse> {
  return postJson<IntakeAcceptedResponse>(
    "/api/intake-agent/classify",
    body,
    options,
  );
}

export async function fetchIntakeSubmissions(options: {
  limit?: number;
  offset?: number;
  status?: string;
  signal?: AbortSignal;
} = {}): Promise<IntakeSubmissionPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
  });
  if (options.status) params.set("status", options.status);
  return fetchJson<IntakeSubmissionPage>(
    `/api/intake-agent/submissions?${params.toString()}`,
    { signal: options.signal },
  );
}

export function fetchIntakeSubmission(
  submissionId: string,
  signal?: AbortSignal,
): Promise<IntakeSubmissionDetail> {
  return fetchJson<IntakeSubmissionDetail>(
    `/api/intake-agent/submissions/${encodeURIComponent(submissionId)}`,
    { signal },
  );
}

export function fetchIntakeEvents(
  submissionId: string,
  signal?: AbortSignal,
): Promise<IntakeRecordsPage<IntakeEvent>> {
  return fetchJson<IntakeRecordsPage<IntakeEvent>>(
    `/api/intake-agent/submissions/${encodeURIComponent(submissionId)}/events?limit=100`,
    { signal },
  );
}

export function fetchIntakeAttempts(
  submissionId: string,
  signal?: AbortSignal,
): Promise<IntakeRecordsPage<IntakeAttempt>> {
  return fetchJson<IntakeRecordsPage<IntakeAttempt>>(
    `/api/intake-agent/submissions/${encodeURIComponent(submissionId)}/attempts?limit=100`,
    { signal },
  );
}

export function approveIntakeSubmission(
  submissionId: string,
  version: number,
): Promise<IntakeSubmissionDetail> {
  return postJson<IntakeSubmissionDetail>(
    `/api/intake-agent/submissions/${encodeURIComponent(submissionId)}/approve`,
    { version },
  );
}

export function rejectIntakeSubmission(
  submissionId: string,
  version: number,
): Promise<IntakeSubmissionDetail> {
  return postJson<IntakeSubmissionDetail>(
    `/api/intake-agent/submissions/${encodeURIComponent(submissionId)}/reject`,
    { version },
  );
}

export function correctIntakeCategory(
  submissionId: string,
  version: number,
  category: Exclude<IntakeCategory, "unclassified">,
): Promise<IntakeSubmissionDetail> {
  return postJson<IntakeSubmissionDetail>(
    `/api/intake-agent/submissions/${encodeURIComponent(submissionId)}/correct-category`,
    { version, category },
  );
}

export function retryIntakeJob(
  jobId: string,
): Promise<IntakeAcceptedResponse> {
  return postJson<IntakeAcceptedResponse>(
    `/api/intake-agent/jobs/${encodeURIComponent(jobId)}/retry`,
    {},
  );
}

/** Rule-based numeric dimension check (user-entered sizes). */
export async function verifyArtworkNumeric(body: {
  project_id?: string;
  artwork_width_inches: number;
  artwork_height_inches: number;
  spec_width_inches: number;
  spec_height_inches: number;
  submitted_by?: string;
}): Promise<ArtworkCardData> {
  return postJson<ArtworkCardData>("/api/artwork-agent/verify-numeric", body);
}

/** Vision-based artwork verification (multipart: image + optional spec image). */
export async function verifyArtworkVision(
  formData: FormData,
): Promise<ArtworkVisionResult> {
  const response = await fetch(apiPath("/api/artwork-agent/verify-vision"), {
    method: "POST",
    body: formData,
    cache: "no-store",
    credentials: "same-origin",
    redirect: "manual",
  });

  // Middleware / proxy may return a redirect to the HTML login page.
  if (response.status >= 300 && response.status < 400) {
    throw new Error("Session expired — refresh and log in, then try again.");
  }

  const contentType = response.headers.get("content-type") ?? "";
  const raw = await response.text();

  if (!contentType.includes("application/json")) {
    if (raw.trimStart().startsWith("<!DOCTYPE") || raw.trimStart().startsWith("<html")) {
      throw new Error(
        "Got an HTML page instead of JSON (often login redirect or wrong API port). " +
          "Open http://localhost:3002, log in, and retry Image Upload.",
      );
    }
    throw new Error(
      `API ${response.status}: unexpected response (${contentType || "no content-type"})`,
    );
  }

  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch {
    throw new Error(`API ${response.status}: response was not valid JSON`);
  }

  if (!response.ok) {
    const detail =
      typeof payload === "object" &&
      payload !== null &&
      "detail" in payload &&
      typeof (payload as { detail?: unknown }).detail === "string"
        ? (payload as { detail: string }).detail
        : response.statusText;
    throw new Error(`API ${response.status}: ${detail}`);
  }

  return payload as ArtworkVisionResult;
}

/** Fetch a page of the supervisor audit log from the backend. */
export async function fetchAuditLog(options: {
  limit?: number;
  offset?: number;
  status?: "pending" | "approved" | "rejected" | "all";
  signal?: AbortSignal;
} = {}): Promise<AuditLogPage> {
  const params = new URLSearchParams({
    limit: String(options.limit ?? 20),
    offset: String(options.offset ?? 0),
    status: options.status ?? "pending",
  });
  return fetchJson<AuditLogPage>(
    `/api/audit-log?${params.toString()}`,
    { signal: options.signal },
  );
}

/** Fetch management overview KPIs from the audit log (no live agent runs). */
export async function fetchDashboardOverview(): Promise<DashboardOverview> {
  return fetchJson<DashboardOverview>("/api/dashboard/overview");
}

/** List operator accounts (admin only). */
export async function fetchAdminOperators(): Promise<OperatorAccount[]> {
  return fetchJson<OperatorAccount[]>("/api/admin/operators");
}

/** Update operator role or active flag (admin only). */
export function updateAdminOperator(
  email: string,
  body: { role?: OperatorRole; active?: boolean },
): Promise<OperatorAccount> {
  return patchJson<OperatorAccount>(
    `/api/admin/operators/${encodeURIComponent(email)}`,
    body,
  );
}

/** Read routing owners and approval policy (admin only). */
export async function fetchAdminConfig(): Promise<AdminConfig> {
  return fetchJson<AdminConfig>("/api/admin/config");
}

/** Update a system config key (admin only). */
export async function updateAdminConfig(
  key: string,
  value: string,
): Promise<{ key: string; value: string; source: string }> {
  const response = await fetch(apiPath(`/api/admin/config/${encodeURIComponent(key)}`), {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
      "X-Correlation-ID": requestId(),
    },
    body: JSON.stringify({ value }),
    cache: "no-store",
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch { /* keep */ }
    throw new ApiError(response.status, `API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<{ key: string; value: string; source: string }>;
}

/** Update risky statuses for one agent (admin only). */
export async function updateAdminApprovalRule(
  agentName: string,
  riskyStatuses: string[],
): Promise<{ agent_name: string; risky_statuses: string[]; confidence_threshold: number }> {
  const response = await fetch(
    apiPath(`/api/admin/approval-rules/${encodeURIComponent(agentName)}`),
    {
      method: "PUT",
      headers: {
        "Content-Type": "application/json",
        "X-Correlation-ID": requestId(),
      },
      body: JSON.stringify({ risky_statuses: riskyStatuses }),
      cache: "no-store",
    },
  );
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (typeof payload.detail === "string") detail = payload.detail;
    } catch { /* keep */ }
    throw new ApiError(response.status, `API ${response.status}: ${detail}`);
  }
  return response.json() as Promise<{
    agent_name: string;
    risky_statuses: string[];
    confidence_threshold: number;
  }>;
}

/** Approve a PENDING audit log entry. */
export async function approveEntry(
  entryId: string,
  approvedBy: string,
): Promise<AuditLogEntry> {
  return postJson<AuditLogEntry>(`/api/audit-log/${entryId}/approve`, {
    approved_by: approvedBy,
  });
}

/** Reject a PENDING audit log entry. */
export async function rejectEntry(
  entryId: string,
  approvedBy: string,
): Promise<AuditLogEntry> {
  return postJson<AuditLogEntry>(`/api/audit-log/${entryId}/reject`, {
    approved_by: approvedBy,
  });
}

export { API_BASE_URL };
