"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Activity, ArrowUpRight, ClipboardCheck, Settings } from "lucide-react";

import LoadingCards from "@/components/LoadingCards";
import StatCard from "@/components/StatCard";
import { fetchDashboardOverview } from "@/lib/api";
import {
  canReview,
  isAdmin,
  useOperatorRole,
} from "@/lib/useOperatorRole";
import { formatTimestamp } from "@/lib/format";
import type { DashboardOverview, OperatorRole } from "@/lib/types";

const AGENT_LINKS: { key: string; href: string; label: string }[] = [
  { key: "email_reply_monitoring", href: "/email-agent", label: "Email" },
  { key: "vendor_followup", href: "/vendor-agent", label: "Vendor" },
  { key: "po_automation", href: "/po-agent", label: "PO" },
  { key: "artwork_verification", href: "/artwork-agent", label: "Artwork" },
  { key: "intake_classification", href: "/intake-agent", label: "Intake" },
  { key: "automated_followup", href: "/followup-agent", label: "Follow-up" },
  { key: "storefront_search", href: "/storefront-agent", label: "Storefront" },
  { key: "installer_matching", href: "/installer-agent", label: "Installer" },
];

function roleEyebrow(role: OperatorRole | null): string {
  if (role === "admin") return "Management";
  if (role === "reviewer") return "Approvals";
  return "Operations";
}

function roleTitle(role: OperatorRole | null): string {
  if (role === "admin") return "Management Overview";
  if (role === "reviewer") return "Review Queue";
  return "Operator Workspace";
}

function roleSubtitle(role: OperatorRole | null): string {
  if (role === "admin") {
    return "KPIs, write-back mode, and routing health. Manage operators and policy from Admin.";
  }
  if (role === "reviewer") {
    return "Pending approvals that need your decision. Open the audit log to approve or reject.";
  }
  return "Run agents and monitor live inbox, board, and CRM checks. Approvals are handled by reviewers.";
}

/** Role-aware home dashboard (operator / reviewer / admin). */
export default function OverviewPage() {
  const { role, loading: roleLoading } = useOperatorRole();
  const [overview, setOverview] = useState<DashboardOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setOverview(await fetchDashboardOverview());
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Failed to load overview. Is the API running on port 8000?",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const reviewer = canReview(role);
  const admin = isAdmin(role);

  return (
    <div className="page-shell">
      <header className="mb-8">
        <p className="page-eyebrow">{roleEyebrow(role)}</p>
        <h1 className="page-title">{roleTitle(role)}</h1>
        <p className="page-subtitle">{roleSubtitle(role)}</p>
        {admin && overview && (
          <p className="mt-2 text-xs text-slate-500">
            Write-back mode:{" "}
            <span className="font-semibold text-slate-300">
              {overview.write_back_mode}
            </span>
          </p>
        )}
      </header>

      {(loading || roleLoading) && !overview && (
        <LoadingCards count={4} compact />
      )}

      {error && (
        <div className="mb-4 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {overview && (
        <>
          {reviewer && overview.pending_approval_count > 0 && (
            <Link
              href="/audit-log"
              className="mb-6 flex items-center justify-between gap-4 rounded-card border border-accent-amber/30 bg-accent-amber/10 px-4 py-3 transition hover:border-accent-amber/50"
            >
              <div className="flex items-center gap-3">
                <ClipboardCheck
                  className="h-5 w-5 text-accent-amber"
                  aria-hidden
                />
                <div>
                  <p className="text-sm font-semibold text-amber-100">
                    {overview.pending_approval_count} item
                    {overview.pending_approval_count === 1 ? "" : "s"} awaiting
                    approval
                  </p>
                  <p className="text-xs text-amber-200/70">
                    Review and decide in the audit log
                  </p>
                </div>
              </div>
              <ArrowUpRight className="h-4 w-4 text-accent-amber" aria-hidden />
            </Link>
          )}

          {!reviewer && (
            <div className="mb-6 rounded-card border border-white/10 bg-white/[0.02] px-4 py-3 text-sm text-slate-400">
              You have operator access — run agents below. Approvals are
              handled by reviewers and admins.
            </div>
          )}

          <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label={reviewer ? "Pending approvals" : "Items in review"}
              value={overview.pending_approval_count}
              color={overview.pending_approval_count > 0 ? "amber" : "green"}
              delayMs={40}
            />
            <StatCard
              label="Unanswered emails"
              value={(overview.kpis?.email?.unanswered_count as number) ?? "—"}
              color={
                Number(overview.kpis?.email?.unanswered_count ?? 0) > 0
                  ? "amber"
                  : "default"
              }
              delayMs={90}
            />
            <StatCard
              label="Vendor escalate"
              value={(overview.kpis?.vendor?.escalate_count as number) ?? "—"}
              color={
                Number(overview.kpis?.vendor?.escalate_count ?? 0) > 0
                  ? "red"
                  : "default"
              }
              delayMs={140}
            />
            <StatCard
              label="POs ready"
              value={
                (overview.kpis?.po?.ready_for_release_count as number) ?? "—"
              }
              color={
                Number(overview.kpis?.po?.ready_for_release_count ?? 0) > 0
                  ? "amber"
                  : "default"
              }
              delayMs={190}
            />
          </div>

          {admin && (
            <p className="mb-6 text-xs text-slate-500">
              KPI counts come from the last agent / webhook / cron run (cached).
              Write-back:{" "}
              <span className="font-semibold text-slate-300">
                {overview.write_back_mode}
              </span>
              {overview.recent_failures.length > 0
                ? ` · ${overview.recent_failures.length} recent execution failure(s)`
                : ""}
              {(overview.open_escalations?.length ?? 0) > 0
                ? ` · ${overview.open_escalations!.length} escalation(s)`
                : ""}
              {overview.queue?.totals
                ? ` · queue pending ${overview.queue.totals.pending ?? 0} / dead ${overview.queue.totals.dead ?? 0}`
                : ""}
              {" · "}
              <Link href="/admin" className="text-accent-primary hover:underline">
                Admin settings
              </Link>
            </p>
          )}

          {admin && overview.recent_failures.length > 0 && (
            <section className="mb-8">
              <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
                Recent failures
              </h2>
              <div className="premium-card overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-surface-border text-slate-400">
                    <tr>
                      <th className="px-4 py-3 font-medium">When</th>
                      <th className="px-4 py-3 font-medium">Agent</th>
                      <th className="px-4 py-3 font-medium">Task</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {overview.recent_failures.slice(0, 5).map((entry) => (
                      <tr
                        key={entry.id}
                        className="border-b border-surface-border/70 last:border-0"
                      >
                        <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-300">
                          {formatTimestamp(entry.timestamp)}
                        </td>
                        <td className="px-4 py-3 text-white">{entry.agent_name}</td>
                        <td className="px-4 py-3 font-mono text-white">
                          {entry.task_id}
                        </td>
                        <td className="px-4 py-3 text-accent-red">
                          {entry.execution_status ?? "FAILED"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section className="mb-8">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
              {reviewer && !admin ? "Agents with pending work" : "Agent shortcuts"}
            </h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(reviewer && !admin
                ? AGENT_LINKS.filter(
                    (a) => (overview.pending_by_agent[a.key] ?? 0) > 0,
                  )
                : AGENT_LINKS
              ).map((agent, index) => (
                <Link
                  key={agent.key}
                  href={agent.href}
                  className="motion-rise premium-card premium-card-hover group p-4"
                  style={{
                    animationDelay: `${Math.min((index + 1) * 45, 220)}ms`,
                  }}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-white">{agent.label}</p>
                    <ArrowUpRight
                      className="h-4 w-4 text-slate-600 transition group-hover:text-accent-primary"
                      aria-hidden
                    />
                  </div>
                  <p className="mt-1 text-xs text-slate-400">
                    Pending: {overview.pending_by_agent[agent.key] ?? 0}
                  </p>
                  <p className="mt-1 font-mono text-xs text-slate-500">
                    Last run:{" "}
                    {overview.last_run_by_agent[agent.key]
                      ? formatTimestamp(overview.last_run_by_agent[agent.key])
                      : "—"}
                  </p>
                </Link>
              ))}
              {reviewer &&
                !admin &&
                AGENT_LINKS.every(
                  (a) => (overview.pending_by_agent[a.key] ?? 0) === 0,
                ) && (
                  <p className="col-span-full text-sm text-slate-500">
                    No agents have pending approvals right now. Open any agent
                    to run a fresh analysis.
                  </p>
                )}
            </div>
          </section>

          {admin && (
            <section className="mb-8">
              <Link
                href="/admin"
                className="premium-card premium-card-hover flex items-center gap-3 p-4"
              >
                <Settings className="h-5 w-5 text-accent-primary" aria-hidden />
                <div>
                  <p className="font-medium text-white">Admin settings</p>
                  <p className="text-xs text-slate-400">
                    Operators, owners, write-back mode, approval rules
                  </p>
                </div>
              </Link>
            </section>
          )}

          <section className="mb-6 flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-400">
              {reviewer ? "Recent decisions" : "Recent activity"}
            </h2>
            <Link
              href="/audit-log"
              className="text-sm font-medium text-accent-primary hover:underline"
            >
              Open audit log
            </Link>
          </section>

          <div className="premium-card overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="border-b border-surface-border text-slate-400">
                <tr>
                  <th className="px-4 py-3 font-medium">When</th>
                  <th className="px-4 py-3 font-medium">Agent</th>
                  <th className="px-4 py-3 font-medium">Task</th>
                  <th className="px-4 py-3 font-medium">Decision</th>
                  <th className="px-4 py-3 font-medium">Execution</th>
                </tr>
              </thead>
              <tbody>
                {overview.recent_entries.length === 0 ? (
                  <tr>
                    <td
                      colSpan={5}
                      className="px-4 py-8 text-center text-slate-400"
                    >
                      <Activity
                        className="mx-auto mb-2 h-5 w-5 text-slate-600"
                        aria-hidden
                      />
                      No activity yet. Run an agent analysis to start the audit
                      trail.
                    </td>
                  </tr>
                ) : (
                  overview.recent_entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="border-b border-surface-border/70 last:border-0"
                    >
                      <td className="whitespace-nowrap px-4 py-3 font-mono text-slate-300">
                        {formatTimestamp(entry.timestamp)}
                      </td>
                      <td className="px-4 py-3 text-white">{entry.agent_name}</td>
                      <td className="px-4 py-3 font-mono text-white">
                        {entry.task_id}
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        {entry.final_approval_needed
                          ? entry.approval_status
                          : "Auto"}
                      </td>
                      <td className="px-4 py-3 text-slate-400">
                        {entry.execution_status ?? "—"}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
