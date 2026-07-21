"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, ExternalLink, RefreshCw } from "lucide-react";

import IntakeStatusBadge from "@/components/intake/IntakeStatusBadge";
import {
  ApiError,
  approveIntakeSubmission,
  correctIntakeCategory,
  fetchIntakeAttempts,
  fetchIntakeEvents,
  fetchIntakeSubmission,
  rejectIntakeSubmission,
  retryIntakeJob,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type {
  IntakeAttempt,
  IntakeCategory,
  IntakeEvent,
  IntakeSubmissionDetail,
  OperatorRole,
} from "@/lib/types";

const REVIEW_CATEGORIES: Exclude<IntakeCategory, "unclassified">[] = [
  "new_project",
  "quote_request",
  "support_issue",
  "general_inquiry",
];
const SETTLED = new Set([
  "completed",
  "rejected",
  "awaiting_approval",
  "classification_dead",
  "routing_dead",
]);

function externalUrls(value: unknown, key = ""): Array<{ label: string; url: string }> {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value).flatMap(([childKey, child]) => {
    if (typeof child === "string" && /^https?:\/\//.test(child)) {
      return [{ label: childKey || key || "Open link", url: child }];
    }
    return externalUrls(child, childKey);
  });
}

function ResultPanel({ title, value }: { title: string; value: Record<string, unknown> | null }) {
  const urls = externalUrls(value);
  return (
    <section className="premium-card p-5">
      <h2 className="text-sm font-bold uppercase tracking-wide text-slate-300">{title}</h2>
      {value ? (
        <>
          {urls.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-2">
              {urls.map((item) => (
                <a
                  key={`${item.label}-${item.url}`}
                  href={item.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-control border border-accent-green/25 px-2.5 py-1.5 text-xs text-accent-green"
                >
                  {item.label.replaceAll("_", " ")} <ExternalLink className="h-3 w-3" aria-hidden />
                </a>
              ))}
            </div>
          )}
          <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-control bg-black/20 p-3 text-xs leading-relaxed text-slate-400">
            {JSON.stringify(value, null, 2)}
          </pre>
        </>
      ) : <p className="mt-3 text-sm text-slate-500">No result recorded yet.</p>}
    </section>
  );
}

export default function IntakeDetail({
  submissionId,
  role,
}: {
  submissionId: string;
  role: OperatorRole;
}) {
  const [submission, setSubmission] = useState<IntakeSubmissionDetail | null>(null);
  const [events, setEvents] = useState<IntakeEvent[]>([]);
  const [attempts, setAttempts] = useState<IntakeAttempt[]>([]);
  const [category, setCategory] = useState<Exclude<IntakeCategory, "unclassified">>("general_inquiry");
  const [loading, setLoading] = useState(true);
  const [acting, setActing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const canReview = role === "reviewer" || role === "admin";

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const [detail, eventPage, attemptPage] = await Promise.all([
        fetchIntakeSubmission(submissionId, signal),
        fetchIntakeEvents(submissionId, signal),
        fetchIntakeAttempts(submissionId, signal),
      ]);
      setSubmission(detail);
      setEvents(eventPage.items);
      setAttempts(attemptPage.items);
      if (detail.classification_category && detail.classification_category !== "unclassified") {
        setCategory(detail.classification_category);
      }
      setError(null);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "Could not load Intake details.");
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [submissionId]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => {
    if (!submission || SETTLED.has(submission.status)) return;
    const controller = new AbortController();
    const delays = [1_500, 2_500, 4_000, 6_500, 10_000];
    let index = 0;
    let timer: number | undefined;
    const poll = async () => {
      if (controller.signal.aborted || index >= delays.length) return;
      timer = window.setTimeout(async () => {
        await load(controller.signal);
        index += 1;
        void poll();
      }, delays[index]);
    };
    void poll();
    return () => {
      controller.abort();
      if (timer) window.clearTimeout(timer);
    };
  }, [load, submission?.status]);

  async function runAction(action: () => Promise<unknown>, success: string) {
    setActing(true);
    setError(null);
    setNotice(null);
    try {
      await action();
      setNotice(success);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("This submission changed before your action was saved. The latest version has been loaded.");
        await load();
      } else {
        setError(err instanceof Error ? err.message : "The action failed.");
      }
    } finally {
      setActing(false);
    }
  }

  const deadJobs = useMemo(() => {
    const seen = new Set<string>();
    return [...events].reverse().flatMap((event) => {
      if (!event.event_type.endsWith("dead_lettered") || typeof event.data.job_id !== "string") return [];
      if (seen.has(event.data.job_id)) return [];
      seen.add(event.data.job_id);
      return [{ jobId: event.data.job_id, stage: event.event_type.replace("_dead_lettered", "") }];
    });
  }, [events]);

  if (loading && !submission) {
    return <div className="page-shell text-sm text-slate-400">Loading Intake submission…</div>;
  }

  if (!submission) {
    return (
      <div className="page-shell">
        <Link href="/intake-agent" className="text-sm text-accent-primary">← Back to Intake inbox</Link>
        <p role="alert" className="mt-6 text-red-200">{error ?? "Submission not found."}</p>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <Link href="/intake-agent" className="mb-5 inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white">
        <ArrowLeft className="h-4 w-4" aria-hidden /> Intake inbox
      </Link>
      <header className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="page-eyebrow">{submission.external_submission_id}</p>
          <h1 className="page-title">Submission detail</h1>
          <p className="page-subtitle">
            Received from {submission.submitted_by} via {submission.source} · version {submission.version}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <IntakeStatusBadge status={submission.status} />
          <button
            type="button"
            onClick={() => void load()}
            aria-label="Refresh details"
            className="button-press rounded-control border border-white/15 p-2 text-slate-400"
          >
            <RefreshCw className="h-4 w-4" aria-hidden />
          </button>
        </div>
      </header>

      <div aria-live="polite" aria-atomic="true">
        {error && <p className="mb-5 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">{error}</p>}
        {notice && <p className="mb-5 rounded-control border border-accent-green/30 bg-accent-green/10 px-4 py-3 text-sm text-accent-green">{notice}</p>}
      </div>

      <section className="premium-card mb-5 p-5 md:p-6">
        <h2 className="text-xs font-bold uppercase tracking-[0.16em] text-slate-500">Original inquiry</h2>
        <blockquote className="mt-3 whitespace-pre-wrap text-sm leading-7 text-slate-200">{submission.body}</blockquote>
      </section>

      <div className="mb-5 grid gap-5 lg:grid-cols-2">
        <section className="premium-card p-5">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-300">Classification</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-slate-500">Category</dt><dd className="mt-1 text-white">{(submission.classification_category ?? "Pending").replaceAll("_", " ")}</dd></div>
            <div><dt className="text-slate-500">Confidence</dt><dd className="mt-1 font-mono text-white">{submission.classification_confidence === null ? "—" : `${Math.round(submission.classification_confidence * 100)}%`}</dd></div>
            <div className="col-span-2"><dt className="text-slate-500">Reasoning</dt><dd className="mt-1 leading-relaxed text-slate-300">{submission.classification_reasoning ?? "Not classified yet."}</dd></div>
            <div><dt className="text-slate-500">Model</dt><dd className="mt-1 text-slate-300">{submission.classification_model ?? "—"}</dd></div>
          </dl>
        </section>
        <section className="premium-card p-5">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-300">Approval &amp; execution</h2>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-slate-500">Approval</dt><dd className="mt-1 text-white">{submission.approval_status.replaceAll("_", " ")}</dd></div>
            <div><dt className="text-slate-500">Execution</dt><dd className="mt-1 text-white">{submission.execution_status.replaceAll("_", " ")}</dd></div>
            <div><dt className="text-slate-500">Actor</dt><dd className="mt-1 text-slate-300">{submission.approval_actor ?? "—"}</dd></div>
            <div><dt className="text-slate-500">Updated</dt><dd className="mt-1 text-slate-300">{formatTimestamp(submission.updated_at)}</dd></div>
          </dl>
        </section>
      </div>

      {canReview && submission.status === "awaiting_approval" && (
        <section className="premium-card mb-5 p-5">
          <h2 className="text-sm font-bold text-white">Reviewer actions</h2>
          <p className="mt-1 text-xs text-slate-500">Actions use optimistic locking against version {submission.version}.</p>
          <div className="mt-4 flex flex-wrap items-end gap-2">
            <button disabled={acting} onClick={() => void runAction(() => approveIntakeSubmission(submission.id, submission.version), "Submission approved and queued for routing.")} className="button-press rounded-control bg-accent-green px-3 py-2 text-sm font-bold text-surface disabled:opacity-50">Approve</button>
            <button disabled={acting} onClick={() => void runAction(() => rejectIntakeSubmission(submission.id, submission.version), "Submission rejected.")} className="button-press rounded-control bg-accent-red px-3 py-2 text-sm font-bold text-white disabled:opacity-50">Reject</button>
            <label className="text-xs text-slate-400">
              Correct category
              <select value={category} onChange={(event) => setCategory(event.target.value as typeof category)} className="control-input mt-1 block px-3 py-2 text-sm">
                {REVIEW_CATEGORIES.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
              </select>
            </label>
            <button disabled={acting} onClick={() => void runAction(() => correctIntakeCategory(submission.id, submission.version, category), "Category corrected and routing queued.")} className="button-press rounded-control border border-accent-primary/40 px-3 py-2 text-sm font-bold text-accent-primary disabled:opacity-50">Correct &amp; approve</button>
          </div>
        </section>
      )}

      {canReview && deadJobs.length > 0 && (submission.status === "classification_dead" || submission.status === "routing_dead") && (
        <section className="premium-card mb-5 border-accent-red/25 p-5">
          <h2 className="text-sm font-bold text-red-200">Dead job recovery</h2>
          <div className="mt-3 flex flex-wrap gap-2">
            {deadJobs.map((job) => (
              <button
                key={job.jobId}
                disabled={acting}
                onClick={() => void runAction(() => retryIntakeJob(job.jobId), `${job.stage} job queued for retry.`)}
                className="button-press rounded-control border border-accent-red/35 px-3 py-2 text-xs text-red-200 disabled:opacity-50"
              >
                Retry {job.stage} · {job.jobId.slice(0, 8)}
              </button>
            ))}
          </div>
        </section>
      )}

      <div className="mb-5 grid gap-5 lg:grid-cols-2">
        <ResultPanel title="Monday result" value={submission.monday_result} />
        <ResultPanel title="Notification result" value={submission.notification_result} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <section className="premium-card p-5">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-300">Classification attempts</h2>
          <div className="mt-4 space-y-3">
            {attempts.length === 0 ? <p className="text-sm text-slate-500">No attempts recorded.</p> : attempts.map((attempt) => (
              <article key={attempt.id} className="rounded-control border border-white/10 bg-black/15 p-3 text-sm">
                <div className="flex justify-between gap-3"><strong className="text-white">Attempt {attempt.attempt_number}</strong><span className={attempt.status === "failed" ? "text-accent-red" : "text-accent-green"}>{attempt.status}</span></div>
                <p className="mt-1 text-xs text-slate-500">{attempt.model} · {formatTimestamp(attempt.started_at)}</p>
                {(attempt.reasoning || attempt.error) && <p className="mt-2 text-xs leading-relaxed text-slate-300">{attempt.error ?? attempt.reasoning}</p>}
              </article>
            ))}
          </div>
        </section>

        <section className="premium-card p-5">
          <h2 className="text-sm font-bold uppercase tracking-wide text-slate-300">Append-only timeline</h2>
          <ol className="mt-4 border-l border-white/15 pl-5">
            {events.map((event) => (
              <li key={event.id} className="relative pb-5 last:pb-0">
                <span className="absolute -left-[1.45rem] top-1 h-2 w-2 rounded-full bg-accent-primary ring-4 ring-surface-card" aria-hidden />
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <strong className="text-sm text-white">{event.event_type.replaceAll("_", " ")}</strong>
                  <time className="font-mono text-[10px] text-slate-500">{formatTimestamp(event.created_at)}</time>
                </div>
                {Object.keys(event.data).length > 0 && <pre className="mt-2 overflow-auto whitespace-pre-wrap break-words text-[11px] leading-relaxed text-slate-400">{JSON.stringify(event.data, null, 2)}</pre>}
              </li>
            ))}
          </ol>
        </section>
      </div>
    </div>
  );
}
