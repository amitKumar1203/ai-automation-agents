import type { ReactNode } from "react";

import StatusPill from "@/components/StatusPill";
import type { VendorCardData } from "@/lib/types";

interface VendorCardProps {
  vendor: VendorCardData;
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <strong className="font-mono font-semibold text-white">{value}</strong>
    </div>
  );
}

/** Card displaying one vendor quote request analysis result. */
export default function VendorCard({ vendor }: VendorCardProps): ReactNode {
  const isDataIssue = vendor.status === "INVALID_DATE";
  const statusBorder =
    vendor.status === "OK"
      ? "border-l-accent-green"
      : vendor.status === "WAITING"
        ? "border-l-accent-primary"
        : vendor.status === "ESCALATE"
          ? "border-l-accent-red"
          : "border-l-accent-amber";

  return (
    <article
      className={`motion-rise premium-card premium-card-hover border-l-[3px] p-5 ${statusBorder}`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-white">{vendor.vendor_name}</h2>
          <p className="mt-1 font-mono text-sm font-semibold text-slate-300">
            {vendor.project_id}
          </p>
        </div>
        <StatusPill status={vendor.status} />
      </div>

      <div className="space-y-2 border-t border-surface-border pt-4">
        <DetailRow
          label="Hours pending"
          value={
            <span className={isDataIssue ? "text-slate-400" : undefined}>
              {vendor.hours_pending}
            </span>
          }
        />
        <DetailRow label="Confidence" value={vendor.confidence} />
        <DetailRow
          label="Requires approval"
          value={vendor.requires_approval ? "Yes" : "No"}
        />
      </div>

      <p
        className={`mt-4 text-sm leading-relaxed ${
          isDataIssue ? "text-slate-400" : "text-slate-200"
        }`}
      >
        {vendor.reasoning}
      </p>
    </article>
  );
}
