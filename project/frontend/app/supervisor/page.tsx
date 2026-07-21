"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Activity, RefreshCw, RotateCcw, Search } from "lucide-react";
import { useSession } from "next-auth/react";

import LoadingCards from "@/components/LoadingCards";
import StatCard from "@/components/StatCard";
import {
  fetchSupervisorJobs,
  fetchSupervisorStatus,
  fetchSupervisorTaskStatus,
  retrySupervisorJob,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type {
  OperatorRole,
  SupervisorJob,
  SupervisorStatus,
  SupervisorTaskStatus,
} from "@/lib/types";

function queueTotal(status: SupervisorStatus, key: string): number {
  return status.queue?.totals?.[key] ?? 0;
}

/** Supervisor monitoring — queue depth, escalations, task lookup, dead job retry. */
export default function SupervisorPage() {
  const { data: session } = useSession();
  const [role, setRole] = useState<OperatorRole | null>(
    session?.user?.role ?? null,
  );
  const [status, setStatus] = useState<SupervisorStatus | null>(null);
  const [deadJobs, setDeadJobs] = useState<SupervisorJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskQuery, setTaskQuery] = useState("");
  const [taskStatus, setTaskStatus] = useState<SupervisorTaskStatus | null>(
    null,
  );
  const [taskLoading, setTaskLoading] = useState(false);
  const [taskError, setTaskError] = useState<string | null>(null);
  const [retryingId, setRetryingId] = useState<string | null>(null);

  const canReview = role === "reviewer" || role === "admin";

  useEffect(() => {
    if (session?.user?.role) {
      setRole(session.user.role);
      return;
    }
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.role) setRole(data.role);
      })
      .catch(() => setRole(null));
  }, [session]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [live, dead] = await Promise.all([
        fetchSupervisorStatus(),
        fetchSupervisorJobs({ status: "dead" }),
      ]);
      setStatus(live);
      setDeadJobs(dead.jobs);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load supervisor status",
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function lookupTask(event: React.FormEvent) {
    event.preventDefault();
    const id = taskQuery.trim();
    if (!id) return;
    setTaskLoading(true);
    setTaskError(null);
    setTaskStatus(null);
    try {
      setTaskStatus(await fetchSupervisorTaskStatus(id));
    } catch (err) {
      setTaskError(
        err instanceof Error ? err.message : "Task lookup failed",
      );
    } finally {
      setTaskLoading(false);
    }
  }

  async function retryJob(jobId: string) {
    if (!canReview) return;
    setRetryingId(jobId);
    try {
      await retrySupervisorJob(jobId);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Retry failed");
    } finally {
      setRetryingId(null);
    }
  }

  if (loading && !status) {
    return (
      <div className="page-shell">
        <LoadingCards count={3} />
      </div>
    );
  }

  return (
    <div className="page-shell motion-rise">
      <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="page-eyebrow">Supervisor</p>
          <h1 className="page-title">Live monitoring</h1>
          <p className="page-subtitle">
            Queue depth, escalations, and end-to-end task status. Dead jobs can
            be retried by reviewers.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          className="button-press inline-flex items-center gap-2 rounded-control border border-surface-border bg-surface-card px-3 py-2 text-sm text-slate-300 hover:border-accent-primary/30"
        >
          <RefreshCw className="h-4 w-4" aria-hidden />
          Refresh
        </button>
      </div>

      {error && (
        <div className="mb-6 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {status && (
        <>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Pending approval"
              value={status.pending_approval_count}
              color="amber"
              delayMs={0}
            />
            <StatCard
              label="Queue pending"
              value={queueTotal(status, "pending")}
              color="blue"
              delayMs={60}
            />
            <StatCard
              label="Queue dead"
              value={queueTotal(status, "dead")}
              color="red"
              delayMs={120}
            />
            <StatCard
              label="Write-back"
              value={status.write_back_mode}
              color="default"
              delayMs={180}
            />
          </div>

          <section className="premium-card mb-6 p-5">
            <h2 className="text-sm font-semibold text-white">Event sources</h2>
            <p className="mt-1 text-xs text-slate-500">
              Routed via <code className="font-mono">route_event()</code>
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {status.event_sources.map((source) => (
                <span
                  key={source}
                  className="rounded-full border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-xs text-slate-300"
                >
                  {source}
                </span>
              ))}
            </div>
          </section>

          {(status.open_escalations.length > 0 ||
            status.recent_failures.length > 0) && (
            <section className="premium-card mb-6 p-5">
              <h2 className="mb-3 text-sm font-semibold text-white">
                Alerts
              </h2>
              <ul className="space-y-2 text-sm">
                {status.open_escalations.map((entry) => (
                  <li key={entry.id}>
                    <Link
                      href="/audit-log"
                      className="text-accent-primary hover:underline"
                    >
                      Escalation: {entry.agent_name} · {entry.task_id}
                    </Link>
                  </li>
                ))}
                {status.recent_failures.map((entry) => (
                  <li key={entry.id}>
                    <Link
                      href="/audit-log"
                      className="text-accent-red hover:underline"
                    >
                      Failed write-back: {entry.agent_name} · {entry.task_id}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <section className="premium-card mb-6 p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <Search className="h-4 w-4 text-accent-primary" aria-hidden />
          Task / project lookup
        </h2>
        <form onSubmit={lookupTask} className="flex flex-wrap gap-2">
          <input
            value={taskQuery}
            onChange={(e) => setTaskQuery(e.target.value)}
            placeholder="e.g. PRJ-201, thread id, submission id"
            className="control-input min-w-[16rem] flex-1 px-3 py-2 text-sm"
          />
          <button
            type="submit"
            disabled={taskLoading || !taskQuery.trim()}
            className="button-press rounded-control border border-accent-primary bg-accent-primary px-4 py-2 text-sm font-semibold text-background disabled:opacity-50"
          >
            {taskLoading ? "Looking up…" : "Lookup"}
          </button>
        </form>
        {taskError && (
          <p className="mt-3 text-sm text-red-200">{taskError}</p>
        )}
        {taskStatus && (
          <div className="mt-4 space-y-3 rounded-control border border-white/10 bg-black/15 p-4 text-sm">
            <p>
              <span className="text-slate-500">Task:</span>{" "}
              <span className="font-mono text-white">{taskStatus.task_id}</span>
            </p>
            {!taskStatus.found ? (
              <p className="text-slate-400">No audit entries for this id.</p>
            ) : (
              <>
                <p>
                  Approval:{" "}
                  <strong className="text-white">
                    {taskStatus.approval_status ?? "—"}
                  </strong>
                  {taskStatus.pending_approval && (
                    <span className="ml-2 text-accent-amber">needs review</span>
                  )}
                </p>
                <p>
                  Execution:{" "}
                  <strong className="text-white">
                    {taskStatus.execution_status ?? "—"}
                  </strong>
                </p>
                {taskStatus.latest && (
                  <Link
                    href="/audit-log"
                    className="inline-flex text-accent-primary hover:underline"
                  >
                    Open in audit log →
                  </Link>
                )}
                {taskStatus.audit_entries.length > 1 && (
                  <p className="text-xs text-slate-500">
                    {taskStatus.audit_entries.length} audit entries for this
                    task
                  </p>
                )}
              </>
            )}
          </div>
        )}
      </section>

      <section className="premium-card p-5">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-white">
          <Activity className="h-4 w-4 text-accent-primary" aria-hidden />
          Dead-letter jobs
        </h2>
        {deadJobs.length === 0 ? (
          <p className="text-sm text-slate-400">No dead jobs in the queue.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[32rem] text-left text-sm">
              <thead>
                <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-2 py-2">Type</th>
                  <th className="px-2 py-2">Agent</th>
                  <th className="px-2 py-2">Attempts</th>
                  <th className="px-2 py-2">Error</th>
                  {canReview && <th className="px-2 py-2">Action</th>}
                </tr>
              </thead>
              <tbody>
                {deadJobs.map((job) => (
                  <tr
                    key={job.id}
                    className="border-b border-white/5 text-slate-300"
                  >
                    <td className="px-2 py-2 font-mono text-xs">{job.job_type}</td>
                    <td className="px-2 py-2">{job.agent_name ?? "—"}</td>
                    <td className="px-2 py-2">
                      {job.attempts}/{job.max_attempts}
                    </td>
                    <td className="max-w-xs truncate px-2 py-2 text-xs text-slate-500">
                      {job.last_error ?? "—"}
                    </td>
                    {canReview && (
                      <td className="px-2 py-2">
                        <button
                          type="button"
                          disabled={retryingId === job.id}
                          onClick={() => void retryJob(job.id)}
                          className="button-press inline-flex items-center gap-1 rounded-lg border border-accent-green/30 bg-accent-green/10 px-2 py-1 text-xs font-semibold text-accent-green disabled:opacity-50"
                        >
                          <RotateCcw className="h-3 w-3" aria-hidden />
                          Retry
                        </button>
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {!canReview && deadJobs.length > 0 && (
          <p className="mt-3 text-xs text-slate-500">
            Retry requires reviewer or admin role.
          </p>
        )}
      </section>

      {status && Object.keys(status.last_run_by_agent).length > 0 && (
        <section className="premium-card mt-6 p-5">
          <h2 className="mb-3 text-sm font-semibold text-white">
            Last run by agent
          </h2>
          <ul className="space-y-1 text-sm text-slate-300">
            {Object.entries(status.last_run_by_agent).map(([agent, ts]) => (
              <li key={agent} className="flex justify-between gap-4">
                <span className="font-mono text-xs">{agent}</span>
                <span className="text-slate-500">{formatTimestamp(ts)}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
