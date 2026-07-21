import type { ReactNode } from "react";

import StatusPill from "@/components/StatusPill";
import { formatCurrency, formatTimestamp } from "@/lib/format";
import type { POCardData } from "@/lib/types";

interface POCardProps {
  project: POCardData;
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <strong className="font-mono font-semibold text-white">{value}</strong>
    </div>
  );
}

/** Card displaying one purchase-order automation analysis result. */
export default function POCard({ project }: POCardProps): ReactNode {
  const statusBorder =
    project.status === "ALREADY_EXISTS"
      ? "border-l-accent-green"
      : "border-l-accent-amber";

  return (
    <article className={`motion-rise premium-card premium-card-hover border-l-[3px] p-5 ${statusBorder}`}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="font-mono text-lg font-bold text-white">{project.project_id}</h2>
          <p className="mt-1 text-sm font-semibold text-slate-300">
            {project.client_name}
          </p>
        </div>
        <StatusPill status={project.status} />
      </div>

      <div className="space-y-2 border-t border-surface-border pt-4">
        <DetailRow label="Confidence" value={project.confidence} />
        <DetailRow
          label="Requires approval"
          value={project.requires_approval ? "Yes" : "No"}
        />
      </div>

      {project.draft_po && (
        <div className="mt-4 rounded-xl border border-accent-amber/35 bg-accent-amber/10 p-4">
          <div className="mb-3 flex items-center justify-between gap-3">
            <span className="text-xs font-semibold uppercase tracking-wide text-slate-300">
              Draft PO
            </span>
            <span className="status-warning rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-accent-amber ring-1 ring-accent-amber/35">
              Awaiting Approval
            </span>
          </div>
          <div className="space-y-2 text-sm">
            <DetailRow label="Vendor" value={project.draft_po.vendor_name} />
            <DetailRow
              label="Estimated Amount"
              value={formatCurrency(project.draft_po.estimated_amount)}
            />
            <DetailRow
              label="Generated"
              value={formatTimestamp(project.draft_po.generated_at)}
            />
          </div>
        </div>
      )}

      <p className="mt-4 text-sm leading-relaxed text-slate-200">
        {project.reasoning}
      </p>
    </article>
  );
}
