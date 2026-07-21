"use client";

import { useCallback, useEffect, useState } from "react";

import EmptyState from "@/components/EmptyState";
import LoadingCards from "@/components/LoadingCards";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import StatCard from "@/components/StatCard";
import StorefrontCard from "@/components/StorefrontCard";
import { fetchStorefrontAgentRun } from "@/lib/api";
import type { StorefrontAnalysisSummary } from "@/lib/types";

/** Storefront Search dashboard — live Monday.com board only. */
export default function StorefrontAgentPage() {
  const [data, setData] = useState<StorefrontAnalysisSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchStorefrontAgentRun();
      setData(response);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to load storefront search results.";
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
          <h1 className="page-title">Storefront Search</h1>
          <p className="page-subtitle">
            Finds storefront imagery for store addresses on the live Monday
            Storefront Projects board and attaches results after approval.
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
            <StatCard label="Found" value={data.found_count} color="green" delayMs={110} />
            <StatCard
              label="Low confidence"
              value={data.low_confidence_count}
              color="amber"
              delayMs={170}
            />
            <StatCard label="Not found" value={data.not_found_count} delayMs={230} />
            <StatCard label="Skipped" value={data.skipped_count} delayMs={290} />
          </section>

          {data.results.length === 0 ? (
            <EmptyState message="No storefront projects on the Monday board. Add rows with Project ID and Store Address." />
          ) : (
            <div className="grid gap-4">
              {data.results.map((project) => (
                <StorefrontCard key={project.project_id} project={project} />
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
