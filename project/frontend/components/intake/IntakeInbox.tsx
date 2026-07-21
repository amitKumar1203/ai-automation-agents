"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ExternalLink, RefreshCw, Send } from "lucide-react";

import IntakeStatusBadge from "@/components/intake/IntakeStatusBadge";
import {
  classifyIntakeSubmission,
  fetchIntakeSubmission,
  fetchIntakeSubmissions,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type {
  IntakeAcceptedResponse,
  IntakeCategory,
  IntakeSubmissionDetail,
  IntakeSubmissionPage,
  OperatorRole,
} from "@/lib/types";

const PAGE_SIZE = 20;
const TERMINAL = new Set([
  "completed",
  "rejected",
  "awaiting_approval",
  "classification_dead",
  "routing_dead",
]);
const CATEGORIES: IntakeCategory[] = [
  "new_project",
  "quote_request",
  "support_issue",
  "general_inquiry",
  "unclassified",
];
const STATUSES = [
  "classification_queued",
  "classification_running",
  "classification_retrying",
  "classification_dead",
  "awaiting_approval",
  "routing_queued",
  "routing_running",
  "routing_retrying",
  "routing_dead",
  "completed",
  "rejected",
];

function newExternalId(): string {
  const value = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  return `dashboard-${value}`;
}

function stableDraftId(): string {
  const stored = window.sessionStorage.getItem("intake-draft-id");
  if (stored) return stored;
  const created = newExternalId();
  window.sessionStorage.setItem("intake-draft-id", created);
  return created;
}

function mondayUrl(result: Record<string, unknown> | null): string | null {
  if (!result) return null;
  const board = result.board;
  if (board && typeof board === "object" && "url" in board && typeof board.url === "string") {
    return board.url;
  }
  return typeof result.url === "string" ? result.url : null;
}

export default function IntakeInbox({ role }: { role: OperatorRole }) {
  const [submittedBy, setSubmittedBy] = useState("");
  const [text, setText] = useState("");
  const externalId = useRef<string | null>(null);
  const [page, setPage] = useState<IntakeSubmissionPage | null>(null);
  const [offset, setOffset] = useState(0);
  const [statusFilter, setStatusFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const pollController = useRef<AbortController | null>(null);

  const load = useCallback(async (signal?: AbortSignal) => {
    setLoading(true);
    try {
      const result = await fetchIntakeSubmissions({
        limit: PAGE_SIZE,
        offset,
        status: statusFilter || undefined,
        signal,
      });
      setPage(result);
      setError(null);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === "AbortError")) {
        setError(err instanceof Error ? err.message : "Could not load the Intake inbox.");
      }
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }, [offset, statusFilter]);

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  useEffect(() => () => pollController.current?.abort(), []);

  async function pollSubmission(accepted: IntakeAcceptedResponse) {
    pollController.current?.abort();
    const controller = new AbortController();
    pollController.current = controller;
    const delays = [800, 1_500, 2_500, 4_000, 6_500, 10_000];
    for (const delay of delays) {
      await new Promise<void>((resolve) => {
        const timer = window.setTimeout(resolve, delay);
        controller.signal.addEventListener("abort", () => {
          window.clearTimeout(timer);
          resolve();
        }, { once: true });
      });
      if (controller.signal.aborted) return;
      try {
        const current = await fetchIntakeSubmission(accepted.submission_id, controller.signal);
        setNotice(
          `${accepted.replay ? "Duplicate replay" : "Submission accepted"} · ${current.status.replaceAll("_", " ")}`,
        );
        await load(controller.signal);
        if (TERMINAL.has(current.status)) return;
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          setError(err instanceof Error ? err.message : "Status polling failed.");
        }
        return;
      }
    }
    setNotice("Processing continues in the background. Refresh the inbox for the latest state.");
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const by = submittedBy.trim();
    const body = text.trim();
    if (!by || !body) {
      setError("Client name/email and inquiry are required.");
      return;
    }
    const id = externalId.current ?? stableDraftId();
    externalId.current = id;
    setSubmitting(true);
    setError(null);
    setNotice(null);
    try {
      const accepted = await classifyIntakeSubmission(
        { submitted_by: by, text: body, submission_id: id },
        { idempotencyKey: id },
      );
      setNotice(
        accepted.replay
          ? `Duplicate replay accepted; tracking existing submission ${accepted.submission_id}.`
          : `Accepted for asynchronous processing as ${accepted.submission_id}.`,
      );
      setText("");
      externalId.current = null;
      window.sessionStorage.removeItem("intake-draft-id");
      setOffset(0);
      await load();
      void pollSubmission(accepted);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not submit the inquiry.");
    } finally {
      setSubmitting(false);
    }
  }

  const items = useMemo(
    () => (page?.items ?? []).filter((item) =>
      !categoryFilter || (item.classification_category ?? "unclassified") === categoryFilter),
    [categoryFilter, page],
  );

  return (
    <div className="page-shell">
      <header className="mb-8">
        <p className="page-eyebrow">Durable workflow</p>
        <h1 className="page-title">Intake inbox</h1>
        <p className="page-subtitle">
          Submit client requests, monitor classification and routing, and open review work.
          Signed in as {role}.
        </p>
      </header>

      <form onSubmit={submit} className="premium-card mb-8 grid gap-5 p-5 md:p-6">
        <div>
          <label htmlFor="intake-submitted-by" className="mb-1.5 block text-sm font-medium text-slate-300">
            Client name or email
          </label>
          <input
            id="intake-submitted-by"
            value={submittedBy}
            onChange={(event) => setSubmittedBy(event.target.value)}
            className="control-input px-3 py-2.5 text-sm"
            placeholder="client@example.com"
            maxLength={320}
            required
          />
        </div>
        <div>
          <label htmlFor="intake-text" className="mb-1.5 block text-sm font-medium text-slate-300">
            Inquiry
          </label>
          <textarea
            id="intake-text"
            value={text}
            onChange={(event) => setText(event.target.value)}
            className="control-input min-h-32 resize-y px-3 py-2.5 text-sm leading-relaxed"
            placeholder="Paste the client’s inquiry here…"
            maxLength={10_000}
            required
          />
          <p className="mt-1.5 text-right font-mono text-[11px] text-slate-500">
            {text.length.toLocaleString()} / 10,000
          </p>
        </div>
        <div className="flex justify-end">
          <button
            type="submit"
            disabled={submitting}
            className="button-press inline-flex items-center gap-2 rounded-control bg-accent-primary px-4 py-2.5 text-sm font-bold text-surface disabled:cursor-wait disabled:opacity-60"
          >
            <Send className="h-4 w-4" aria-hidden />
            {submitting ? "Submitting…" : "Submit inquiry"}
          </button>
        </div>
      </form>

      <div aria-live="polite" aria-atomic="true">
        {error && (
          <p className="mb-5 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">
            {error}
          </p>
        )}
        {notice && (
          <p className="mb-5 rounded-control border border-accent-primary/30 bg-accent-primary/10 px-4 py-3 text-sm text-slate-200">
            {notice}
          </p>
        )}
      </div>

      <section aria-labelledby="inbox-heading">
        <div className="mb-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 id="inbox-heading" className="text-xl font-bold text-white">Persisted submissions</h2>
            <p className="mt-1 text-xs text-slate-500">{page?.total ?? 0} matching status filter</p>
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-xs text-slate-400">
              Status
              <select
                value={statusFilter}
                onChange={(event) => { setStatusFilter(event.target.value); setOffset(0); }}
                className="control-input mt-1 block min-w-48 px-3 py-2 text-sm"
              >
                <option value="">All statuses</option>
                {STATUSES.map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}
              </select>
            </label>
            <label className="text-xs text-slate-400">
              Category
              <select
                value={categoryFilter}
                onChange={(event) => setCategoryFilter(event.target.value)}
                className="control-input mt-1 block min-w-44 px-3 py-2 text-sm"
              >
                <option value="">All categories</option>
                {CATEGORIES.map((category) => <option key={category} value={category}>{category.replaceAll("_", " ")}</option>)}
              </select>
            </label>
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className="button-press inline-flex h-10 items-center gap-2 rounded-control border border-white/15 px-3 text-sm text-slate-300 disabled:opacity-50"
            >
              <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} aria-hidden />
              Refresh
            </button>
          </div>
        </div>

        <div className="grid gap-4">
          {loading && !page ? (
            <div className="premium-card p-6 text-sm text-slate-400">Loading persisted inbox…</div>
          ) : items.length === 0 ? (
            <div className="premium-card p-6 text-sm text-slate-400">
              No submissions match the selected filters on this page.
            </div>
          ) : items.map((item) => {
            const url = mondayUrl(item.monday_result);
            return (
              <article key={item.id} className="premium-card premium-card-hover p-5">
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <Link href={`/intake-agent/${item.id}`} className="font-semibold text-white hover:text-accent-primary">
                      {item.submitted_by}
                    </Link>
                    <p className="mt-1 truncate font-mono text-[11px] text-slate-500">
                      {item.external_submission_id} · {formatTimestamp(item.created_at)}
                    </p>
                  </div>
                  <IntakeStatusBadge status={item.status} />
                </div>
                <p className="mt-4 line-clamp-2 text-sm leading-relaxed text-slate-300">{item.body}</p>
                <div className="mt-4 flex flex-wrap items-center gap-3 border-t border-white/10 pt-3 text-xs">
                  <span className="text-slate-400">
                    {(item.classification_category ?? "unclassified").replaceAll("_", " ")}
                    {item.classification_confidence !== null
                      ? ` · ${Math.round(item.classification_confidence * 100)}%`
                      : ""}
                  </span>
                  <Link href={`/intake-agent/${item.id}`} className="ml-auto font-semibold text-accent-primary">
                    View details
                  </Link>
                  {url && (
                    <a href={url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-green">
                      Monday <ExternalLink className="h-3 w-3" aria-hidden />
                    </a>
                  )}
                </div>
              </article>
            );
          })}
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
          <span className="font-mono text-xs text-slate-500">
            {page && page.total > 0 ? `${offset + 1}–${Math.min(offset + PAGE_SIZE, page.total)} of ${page.total}` : "0 results"}
          </span>
          <button
            type="button"
            disabled={!page?.next_offset || loading}
            onClick={() => page?.next_offset !== null && setOffset(page?.next_offset ?? offset)}
            className="button-press rounded-control border border-white/15 px-3 py-2 text-sm text-slate-300 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </section>
    </div>
  );
}
