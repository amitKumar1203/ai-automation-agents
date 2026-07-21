"use client";

import { useCallback, useEffect, useState } from "react";

import EmptyState from "@/components/EmptyState";
import LoadingCards from "@/components/LoadingCards";
import POCard from "@/components/POCard";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import StatCard from "@/components/StatCard";
import { fetchPOAgentRun } from "@/lib/api";
import type { POAnalysisSummary } from "@/lib/types";

/** Purchase Order Automation dashboard — live Salesforce only.
 *
 * Approve/reject is intentionally NOT wired on this page yet — all decisions
 * go through /audit-log (the single source of truth across agents).
 */
export default function POAgentPage() {
  const [data, setData] = useState<POAnalysisSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchPOAgentRun();
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
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  return (
    <div className="page-shell">
      <header className="mb-8 flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
        <div>
          <p className="page-eyebrow">Supervisor review</p>
          <h1 className="page-title">Purchase Order Automation</h1>
          <p className="page-subtitle">
            Detects approved projects missing a PO and prepares release-ready drafts.
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
          <section className="mb-8 grid gap-4 md:grid-cols-3">
            <StatCard label="Total Projects" value={data.total_projects} delayMs={50} />
            <StatCard
              label="Already Has PO"
              value={data.already_exists_count}
              color="green"
              delayMs={110}
            />
            <StatCard
              label="Ready for Release"
              value={data.ready_for_release_count}
              color="amber"
              delayMs={170}
            />
          </section>

          <section className="grid gap-5">
            {data.results.length === 0 ? (
              <EmptyState message="No purchase orders need review right now." />
            ) : data.results.map((project, index) => (
              <div
                key={project.project_id}
                style={{ animationDelay: `${Math.min(index * 50, 260)}ms` }}
              >
                <POCard project={project} />
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
