"use client";

import { useCallback, useEffect, useState } from "react";

import EmptyState from "@/components/EmptyState";
import LoadingCards from "@/components/LoadingCards";
import RunAnalysisButton from "@/components/RunAnalysisButton";
import StatCard from "@/components/StatCard";
import VendorCard from "@/components/VendorCard";
import { fetchVendorAgentRun } from "@/lib/api";
import type { VendorAnalysisSummary } from "@/lib/types";

/** Vendor Follow-Up dashboard — live Monday.com board only. */
export default function VendorAgentPage() {
  const [data, setData] = useState<VendorAnalysisSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetchVendorAgentRun();
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
          <h1 className="page-title">Vendor Follow-Up</h1>
          <p className="page-subtitle">
            Tracks vendor quote requests and flags overdue responses.
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
            <StatCard label="Total Requests" value={data.total_requests} delayMs={50} />
            <StatCard
              label="Waiting"
              value={data.waiting_count}
              color="blue"
              delayMs={110}
            />
            <StatCard
              label="Needs Reminder"
              value={data.reminder_count}
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
              <EmptyState message="No vendor requests need review right now." />
            ) : data.results.map((vendor, index) => (
              <div
                key={`${vendor.project_id}-${vendor.vendor_name}`}
                style={{ animationDelay: `${Math.min(index * 50, 260)}ms` }}
              >
                <VendorCard vendor={vendor} />
              </div>
            ))}
          </section>
        </>
      )}
    </div>
  );
}
