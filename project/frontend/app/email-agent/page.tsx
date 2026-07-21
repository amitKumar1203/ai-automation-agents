"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { SlidersHorizontal } from "lucide-react";

import EmptyState from "@/components/EmptyState";
import LoadingCards from "@/components/LoadingCards";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import StatCard from "@/components/StatCard";
import ThreadCard from "@/components/ThreadCard";
import { fetchEmailAgentRun } from "@/lib/api";
import type { AnalysisSummaryResponse, ThreadStatus } from "@/lib/types";

type FilterKey = "all" | ThreadStatus;

/** Email Reply Monitoring dashboard — live Gmail inbox only. */
export default function EmailAgentPage() {
  const [data, setData] = useState<AnalysisSummaryResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<FilterKey>("all");
  const [openThreadId, setOpenThreadId] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [senderFilter, setSenderFilter] = useState("");
  const [keywordFilter, setKeywordFilter] = useState("");
  const reduceMotion = useReducedMotion();

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchEmailAgentRun({
        senderFilter: senderFilter.trim() || undefined,
        keywordFilter: keywordFilter.trim() || undefined,
      });
      setData(response);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to load analysis. Is the FastAPI backend running on port 8000?";
      setError(message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [senderFilter, keywordFilter]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const threads = useMemo(() => {
    if (!data) {
      return [];
    }
    if (filter === "all") {
      return data.results;
    }
    return data.results.filter((thread) => thread.status === filter);
  }, [data, filter]);

  const orderedThreads = useMemo(() => {
    return [...threads].sort((a, b) => {
      const aTime = new Date(a.last_message_timestamp).getTime() || 0;
      const bTime = new Date(b.last_message_timestamp).getTime() || 0;
      return bTime - aTime;
    });
  }, [threads]);

  // Keep exactly one thread open: the newest (first) in the current list.
  useEffect(() => {
    setOpenThreadId(orderedThreads[0]?.thread_id ?? null);
  }, [orderedThreads]);

  return (
    <div className="page-shell">
      <header className="mb-8 flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
        <div className="max-w-2xl">
          <p className="page-eyebrow">No client email left unanswered</p>
          <h1 className="page-title">Email Reply Monitoring</h1>
          <p className="page-subtitle">
            Monitors client email threads, detects unanswered conversations,
            measures response time, notifies owners
          </p>
        </div>
        <RunAnalysisButton loading={loading} onClick={() => void loadData()} />
      </header>

      <div className="mb-6">
        <button
          type="button"
          onClick={() => setFiltersOpen((open) => !open)}
          className="button-press inline-flex items-center gap-2 rounded-control border border-surface-border bg-surface-card px-3 py-2 text-xs font-semibold text-slate-300 hover:border-accent-primary/25 hover:text-white"
          aria-expanded={filtersOpen}
        >
          <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden />
          Filters
          <span className="text-slate-500">{filtersOpen ? "▾" : "▸"}</span>
          {(senderFilter.trim() || keywordFilter.trim()) && (
            <span className="rounded-md bg-accent-primary/20 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-accent-primary">
              Active
            </span>
          )}
        </button>

        {filtersOpen && (
          <div className="premium-card mt-3 grid gap-3 p-4 sm:grid-cols-2">
            <label className="block text-xs text-slate-400">
              Filter by sender
              <input
                type="text"
                value={senderFilter}
                onChange={(event) => setSenderFilter(event.target.value)}
                placeholder="e.g. nirmal or @gmail.com"
                className="control-input mt-1.5 px-3 py-2 text-sm placeholder:text-slate-500"
              />
            </label>
            <label className="block text-xs text-slate-400">
              Filter by keyword
              <input
                type="text"
                value={keywordFilter}
                onChange={(event) => setKeywordFilter(event.target.value)}
                placeholder="e.g. order status"
                className="control-input mt-1.5 px-3 py-2 text-sm placeholder:text-slate-500"
              />
            </label>
            <p className="sm:col-span-2 text-xs leading-relaxed text-slate-500">
              Optional demo filters for live Gmail. Leave blank to fetch recent
              threads as usual. Filters apply when you click Run Analysis.
            </p>
          </div>
        )}
      </div>

      {loading && !data && (
        <LoadingCards />
      )}

      {error && (
        <div className="mb-6 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm leading-relaxed text-red-200">
          {error}
        </div>
      )}

      {data && (
        <>
          <section className="mb-6 grid gap-3 sm:grid-cols-3">
            <StatCard label="Total threads" value={data.total_threads} delayMs={60} />
            <StatCard
              label="Needs reply"
              value={data.unanswered_count}
              color="amber"
              delayMs={120}
            />
            <StatCard
              label="All clear"
              value={data.ok_count}
              color="green"
              delayMs={180}
            />
          </section>

          <div className="mb-4">
            <div
              className="inline-flex rounded-control border border-surface-border bg-surface-card p-1"
              role="tablist"
              aria-label="Filter threads"
            >
              {(
                [
                  ["all", "All", data.total_threads],
                  ["UNANSWERED", "Needs reply", data.unanswered_count],
                  ["OK", "All clear", data.ok_count],
                ] as const
              ).map(([key, label, count]) => {
                const active = filter === key;
                return (
                  <button
                    key={key}
                    type="button"
                    role="tab"
                    aria-selected={active}
                    onClick={() => setFilter(key)}
                    className={`button-press relative rounded-lg px-3 py-1.5 text-xs font-semibold ${
                      active
                        ? "text-white"
                        : "text-slate-400 hover:text-white"
                    }`}
                  >
                    {active && (
                      <motion.span
                        layoutId="email-filter-active"
                        transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 430, damping: 34 }}
                        className="absolute inset-0 rounded-lg bg-accent-primary"
                      />
                    )}
                    <span className="relative">{label}</span>
                    <span className="relative ml-1.5 font-mono tabular-nums opacity-80">
                      {count}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          <section className="grid gap-3">
            {orderedThreads.length === 0 ? (
              <EmptyState message="No email threads match this filter." />
            ) : (
              orderedThreads.map((thread, index) => (
                <div
                  key={thread.thread_id}
                  className="motion-rise"
                  style={{ animationDelay: `${Math.min(index * 55, 280)}ms` }}
                >
                  <ThreadCard
                    thread={thread}
                    open={openThreadId === thread.thread_id}
                    onToggle={() =>
                      setOpenThreadId((current) =>
                        current === thread.thread_id ? null : thread.thread_id,
                      )
                    }
                  />
                </div>
              ))
            )}
          </section>
        </>
      )}
    </div>
  );
}
