"use client";

import { useCallback, useEffect, useState } from "react";

import EmptyState from "@/components/EmptyState";
import InstallerCard from "@/components/InstallerCard";
import LoadingCards from "@/components/LoadingCards";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import StatCard from "@/components/StatCard";
import { fetchInstallerAgentRun } from "@/lib/api";
import type { InstallerAnalysisSummary } from "@/lib/types";

/** Installer Matching dashboard — live Monday.com boards only. */
export default function InstallerAgentPage() {
  const [data, setData] = useState<InstallerAnalysisSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchInstallerAgentRun();
      setData(response);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to load installer matching results.";
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
          <h1 className="page-title">Installer Matching</h1>
          <p className="page-subtitle">
            Ranks installers from the live Monday roster by region and spare
            capacity, then drafts outreach after approval.
          </p>
        </div>
        <RunAnalysisButton loading={loading} onClick={() => void loadData()} />
      </header>

      {loading && !data && <LoadingCards />}

      {error && (
        <div className="mb-6 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {data && (
        <>
          <section className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            <StatCard label="Total Projects" value={data.total_projects} delayMs={50} />
            <StatCard label="Matched" value={data.matched_count} color="green" delayMs={110} />
            <StatCard
              label="Low confidence"
              value={data.low_confidence_count}
              color="amber"
              delayMs={170}
            />
            <StatCard label="No match" value={data.no_match_count} delayMs={230} />
            <StatCard label="Skipped" value={data.skipped_count} delayMs={290} />
          </section>

          {data.results.length === 0 ? (
            <EmptyState message="No install projects on the Monday board. Add rows with Project ID and Install Region." />
          ) : (
            <div className="grid gap-4">
              {data.results.map((project) => (
                <InstallerCard key={project.project_id} project={project} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
