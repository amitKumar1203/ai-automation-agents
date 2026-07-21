"use client";

import { Fragment, useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Check, ChevronDown, ScrollText, X } from "lucide-react";
import { useSession } from "next-auth/react";

import LoadingCards from "@/components/LoadingCards";
import { approveEntry, fetchAuditLog, rejectEntry } from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type {
  AuditLogEntry,
  AuditLogPage as AuditLogPageData,
  AuditLogTab,
  OperatorRole,
} from "@/lib/types";

const PAGE_SIZE = 20;

const AUDIT_TABS: { id: AuditLogTab; label: string; description: string }[] = [
  {
    id: "pending",
    label: "Needs review",
    description: "One row per task — latest run only. Approve or reject here.",
  },
  {
    id: "approved",
    label: "Approved",
    description: "Decisions you approved and write-back results.",
  },
  {
    id: "rejected",
    label: "Rejected",
    description: "Rejected items and runs superseded by a newer Run.",
  },
  {
    id: "all",
    label: "All history",
    description: "Full audit trail including auto-approved runs.",
  },
];

function formatResultData(data: Record<string, unknown>): string {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

/** Audit log page — single place for approve/reject across all agents. */
export default function AuditLogPage() {
  const { data: session } = useSession();
  const [role, setRole] = useState<OperatorRole | null>(
    session?.user?.role ?? null,
  );
  const [entries, setEntries] = useState<AuditLogEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approvedBy, setApprovedBy] = useState("");
  const [rowLoadingId, setRowLoadingId] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<AuditLogTab>("pending");
  const [tabCounts, setTabCounts] = useState<AuditLogPageData["counts"]>(null);
  const reduceMotion = useReducedMotion();
  const canReview = role === "reviewer" || role === "admin";

  useEffect(() => {
    if (session?.user?.email) {
      setRole(session.user.role ?? "operator");
      setApprovedBy(session.user.email);
      return;
    }

    let cancelled = false;
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as {
          email?: string | null;
          role?: OperatorRole;
        };
      })
      .then((data) => {
        if (cancelled) return;
        if (data?.role) setRole(data.role);
        if (data?.email) setApprovedBy(data.email);
      })
      .catch(() => {
        if (!cancelled) setRole(null);
      });

    return () => {
      cancelled = true;
    };
  }, [session]);

  const loadAuditLog = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    setError(null);

    try {
      const page = await fetchAuditLog({
        limit: PAGE_SIZE,
        offset,
        status: activeTab,
        signal,
      });
      setEntries(page.items);
      setTotal(page.total);
      setNextOffset(page.next_offset);
      if (page.counts) setTabCounts(page.counts);
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") return;
      const message =
        err instanceof Error
          ? err.message
          : "Failed to load audit log. Is the FastAPI backend running on port 8000?";
      setError(message);
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [offset, activeTab]);

  useEffect(() => {
    const controller = new AbortController();
    void loadAuditLog(controller.signal);
    return () => controller.abort();
  }, [loadAuditLog]);

  async function handleDecision(
    entryId: string,
    action: "approve" | "reject",
  ): Promise<void> {
    if (!canReview) {
      setRowErrors((prev) => ({
        ...prev,
        [entryId]: "Only reviewers and admins can approve or reject entries.",
      }));
      return;
    }

    const actor = approvedBy.trim();
    if (!actor) {
      setRowErrors((prev) => ({
        ...prev,
        [entryId]: "Sign in again before approving or rejecting.",
      }));
      return;
    }

    setRowLoadingId(entryId);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[entryId];
      return next;
    });

    try {
      if (action === "approve") {
        await approveEntry(entryId, actor);
      } else {
        await rejectEntry(entryId, actor);
      }
      await loadAuditLog();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Action failed. Please try again.";
      setRowErrors((prev) => ({ ...prev, [entryId]: message }));
    } finally {
      setRowLoadingId(null);
    }
  }

  const rangeLabel =
    total > 0
      ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} of ${total}`
      : "0 results";

  return (
    <div className="page-shell">
      <header className="mb-8">
        <p className="page-eyebrow">Supervisor</p>
        <h1 className="page-title">Audit Log</h1>
        <p className="page-subtitle">
          Review queue, approved decisions, and full history — separated so
          duplicate runs do not clutter what still needs action.
        </p>
        {canReview ? (
          <p className="mt-4 text-sm text-slate-400">
            Acting as{" "}
            <span className="font-medium text-slate-200">
              {approvedBy || "signed-in operator"}
            </span>
          </p>
        ) : (
          <p className="mt-4 text-sm text-amber-200/90">
            You have read-only access. Reviewers and admins can approve or
            reject pending items.
          </p>
        )}
      </header>

      {loading && entries.length === 0 && (
        <LoadingCards />
      )}

      {error && (
        <div className="mb-4 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {!error && (
        <>
          <div className="mb-5 flex flex-wrap gap-2">
            {AUDIT_TABS.map((tab) => {
              const count =
                tab.id === "pending"
                  ? tabCounts?.pending_review
                  : tab.id === "approved"
                    ? tabCounts?.approved
                    : tab.id === "rejected"
                      ? tabCounts?.rejected
                      : tabCounts?.all;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => {
                    setActiveTab(tab.id);
                    setOffset(0);
                    setExpandedId(null);
                  }}
                  className={`button-press rounded-full px-4 py-2 text-sm font-semibold transition ${
                    isActive
                      ? "bg-accent-primary/20 text-accent-primary ring-1 ring-accent-primary/40"
                      : "bg-white/5 text-slate-300 ring-1 ring-white/10 hover:bg-white/10"
                  }`}
                >
                  {tab.label}
                  {typeof count === "number" ? (
                    <span className="ml-2 font-mono text-xs opacity-80">{count}</span>
                  ) : null}
                </button>
              );
            })}
          </div>
          <p className="mb-5 text-sm text-slate-400">
            {AUDIT_TABS.find((tab) => tab.id === activeTab)?.description}
          </p>

          <div className="premium-card overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-surface-border text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Timestamp</th>
                  <th className="px-4 py-3 font-medium">Agent</th>
                  <th className="px-4 py-3 font-medium">Task ID</th>
                  <th className="px-4 py-3 font-medium">Decision</th>
                  <th className="px-4 py-3 font-medium">Execution</th>
                  <th className="px-4 py-3 font-medium">Details</th>
                </tr>
              </thead>
              <tbody>
                {entries.length === 0 && !loading ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-8 text-center text-slate-400">
                      <ScrollText className="mx-auto mb-2 h-5 w-5 text-slate-600" aria-hidden />
                      {activeTab === "pending"
                        ? "Nothing waiting for review. Run an agent, then check back here."
                        : activeTab === "approved"
                          ? "No approved decisions yet."
                          : activeTab === "rejected"
                            ? "No rejected or superseded items."
                            : "No audit entries yet. Agent decisions will appear here."}
                    </td>
                  </tr>
                ) : (
                  entries.map((entry) => {
                    const needsAction =
                      canReview &&
                      entry.final_approval_needed &&
                      entry.approval_status === "PENDING";
                    const isRowLoading = rowLoadingId === entry.id;
                    const isExpanded = expandedId === entry.id;

                    return (
                      <Fragment key={entry.id}>
                        <tr className="border-b border-surface-border/70 last:border-0 align-top">
                          <td className="px-4 py-3 whitespace-nowrap font-mono text-slate-300">
                            {formatTimestamp(entry.timestamp)}
                          </td>
                          <td className="px-4 py-3 text-white">{entry.agent_name}</td>
                          <td className="px-4 py-3 font-mono text-white">{entry.task_id}</td>
                          <td className="px-4 py-3">
                            {needsAction ? (
                              <div className="flex flex-col gap-2">
                                <div className="flex flex-wrap gap-2">
                                  <motion.button
                                    type="button"
                                    disabled={isRowLoading}
                                    onClick={() =>
                                      void handleDecision(entry.id, "approve")
                                    }
                                    whileTap={reduceMotion ? undefined : { scale: 0.98 }}
                                    className="button-press inline-flex items-center gap-1.5 rounded-lg border border-accent-green/30 bg-accent-green/10 px-3 py-1.5 text-xs font-semibold text-accent-green hover:bg-accent-green/15 disabled:opacity-50"
                                  >
                                    {!isRowLoading && <Check className="h-3 w-3" aria-hidden />}
                                    {isRowLoading ? "..." : "Approve"}
                                  </motion.button>
                                  <motion.button
                                    type="button"
                                    disabled={isRowLoading}
                                    onClick={() =>
                                      void handleDecision(entry.id, "reject")
                                    }
                                    whileTap={reduceMotion ? undefined : { scale: 0.98 }}
                                    className="button-press inline-flex items-center gap-1.5 rounded-lg border border-accent-red/30 bg-accent-red/10 px-3 py-1.5 text-xs font-semibold text-accent-red hover:bg-accent-red/15 disabled:opacity-50"
                                  >
                                    {!isRowLoading && <X className="h-3 w-3" aria-hidden />}
                                    {isRowLoading ? "..." : "Reject"}
                                  </motion.button>
                                </div>
                                {rowErrors[entry.id] && (
                                  <p className="max-w-xs text-xs text-red-300">
                                    {rowErrors[entry.id]}
                                  </p>
                                )}
                              </div>
                            ) : entry.approval_status === "APPROVED" ||
                              entry.approval_status === "REJECTED" ? (
                              <div className="space-y-1">
                                <motion.span
                                  key={entry.approval_status}
                                  initial={reduceMotion ? false : { opacity: 0, scale: 0.94 }}
                                  animate={{ opacity: 1, scale: 1 }}
                                  className={`inline-block rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${
                                    entry.approval_status === "APPROVED"
                                      ? "status-success text-accent-green"
                                      : "status-danger text-accent-red"
                                  }`}
                                >
                                  {entry.approval_status}
                                </motion.span>
                                <p className="text-xs text-slate-400">
                                  by {entry.approved_by ?? "unknown"}
                                  {entry.approved_by === "superseded-by-rerun"
                                    ? " · newer run replaced this"
                                    : ""}
                                  {entry.approved_at
                                    ? ` · ${formatTimestamp(entry.approved_at)}`
                                    : ""}
                                </p>
                              </div>
                            ) : (
                              <span className="font-semibold text-accent-green">
                                Auto
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            {entry.execution_status ? (
                              <span
                                className={`inline-block rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide ${
                                  entry.execution_status === "SUCCESS"
                                    ? "status-success text-accent-green"
                                    : entry.execution_status === "FAILED"
                                      ? "status-danger text-accent-red"
                                      : entry.execution_status === "DRY_RUN"
                                        ? "status-warning text-accent-amber"
                                        : "bg-white/10 text-slate-300"
                                }`}
                              >
                                {entry.execution_status}
                              </span>
                            ) : (
                              <span className="text-slate-500">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              type="button"
                              onClick={() =>
                                setExpandedId(isExpanded ? null : entry.id)
                              }
                              className="button-press inline-flex items-center gap-1 text-xs font-medium text-accent-primary hover:underline"
                            >
                              {isExpanded ? "Hide" : "Show"}
                              <ChevronDown className={`h-3 w-3 transition ${isExpanded ? "rotate-180" : ""}`} aria-hidden />
                            </button>
                            <p className="mt-1 max-w-xs text-xs text-slate-400 line-clamp-2">
                              {entry.result.reasoning}
                            </p>
                          </td>
                        </tr>
                        {isExpanded && (
                          <tr className="border-b border-surface-border/70 bg-surface/40">
                            <td colSpan={6} className="px-4 py-3">
                              <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                                Result data
                              </p>
                              <pre className="mb-3 overflow-x-auto rounded-lg bg-black/30 p-3 text-xs text-slate-300">
                                {formatResultData(entry.result.data)}
                              </pre>
                              {entry.execution_detail && (
                                <>
                                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                                    Execution detail
                                  </p>
                                  <pre className="overflow-x-auto rounded-lg bg-black/30 p-3 text-xs text-slate-300">
                                    {entry.execution_detail}
                                  </pre>
                                </>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          <div className="mt-5 flex items-center justify-between">
            <button
              type="button"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              className="button-press rounded-control border border-white/15 px-3 py-2 text-sm text-slate-300 disabled:opacity-40"
            >
              Previous
            </button>
            <span className="font-mono text-xs text-slate-500">{rangeLabel}</span>
            <button
              type="button"
              disabled={nextOffset === null || loading}
              onClick={() => nextOffset !== null && setOffset(nextOffset)}
              className="button-press rounded-control border border-white/15 px-3 py-2 text-sm text-slate-300 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </>
      )}
    </div>
  );
}
