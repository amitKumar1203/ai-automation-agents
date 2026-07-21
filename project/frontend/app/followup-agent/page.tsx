"use client";

import { useCallback, useEffect, useState } from "react";

import EmptyState from "@/components/EmptyState";
import FollowUpCard from "@/components/FollowUpCard";
import LoadingCards from "@/components/LoadingCards";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import StatCard from "@/components/StatCard";
import { fetchFollowUpAgentRun } from "@/lib/api";
import type { FollowUpAnalysisSummary } from "@/lib/types";

/** Automated Follow-Up dashboard — stalled projects by env SLA. */
export default function FollowUpAgentPage() {
  const [data, setData] = useState<FollowUpAnalysisSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchFollowUpAgentRun();
      setData(response);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to load follow-up analysis.";
      setError(message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <div className="page-shell">
      <header className="mb-8 flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="page-eyebrow">Operational intelligence</p>
          <h1 className="page-title">Automated Follow-Up</h1>
          <p className="page-subtitle">
            Monitors inactive projects, flags stalled work, and escalates when
            activity goes quiet too long.
          </p>
        </div>
        <RunAnalysisButton loading={loading} onClick={() => void loadData()} />
      </header>

      {loading && !data && (
        <LoadingCards />
      )}

      {error && (
        <div className="mb-6 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {data && (
        <>
          <section className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Total Projects" value={data.total_projects} delayMs={50} />
            <StatCard label="On Track" value={data.ok_count} color="green" delayMs={110} />
            <StatCard
              label="Needs Follow-Up"
              value={data.followup_count}
              color="amber"
              delayMs={170}
            />
            <StatCard
              label="Escalate"
              value={data.escalate_count}
              color="red"
              delayMs={230}
            />
          </section>

          <section className="grid gap-5">
            {data.results.length === 0 ? (
              <EmptyState message="No stalled projects need follow-up right now." />
            ) : data.results.map((project, index) => (
              <div
                key={project.project_id}
                style={{ animationDelay: `${Math.min(index * 50, 260)}ms` }}
              >
                <FollowUpCard project={project} />
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
