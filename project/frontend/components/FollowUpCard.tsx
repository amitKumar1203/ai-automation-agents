import type { ReactNode } from "react";

import StatusPill from "@/components/StatusPill";
import type { FollowUpCardData } from "@/lib/types";

interface FollowUpCardProps {
  project: FollowUpCardData;
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <strong className="font-mono font-semibold text-white">{value}</strong>
    </div>
  );
}

/** Card for one Automated Follow-Up project result. */
export default function FollowUpCard({ project }: FollowUpCardProps): ReactNode {
  const statusBorder =
    project.status === "OK"
      ? "border-l-accent-green"
      : project.status === "ESCALATE"
        ? "border-l-accent-red"
        : "border-l-accent-amber";

  return (
    <article
      className={`motion-rise premium-card premium-card-hover border-l-[3px] p-5 ${statusBorder}`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-bold text-white">{project.project_name}</h2>
          <p className="mt-1 font-mono text-sm font-semibold text-slate-300">
            {project.project_id}
          </p>
        </div>
        <StatusPill status={project.status} />
      </div>

      <div className="space-y-2 border-t border-surface-border pt-4">
        <DetailRow label="Stage" value={project.stage || "—"} />
        <DetailRow label="Days inactive" value={project.days_inactive} />
        <DetailRow label="Notify" value={project.owner_email || "—"} />
        <DetailRow label="Confidence" value={project.confidence} />
        <DetailRow
          label="Requires approval"
          value={project.requires_approval ? "Yes" : "No"}
        />
      </div>

      <p className="mt-4 text-sm leading-relaxed text-slate-200">
        {project.reasoning}
      </p>
    </article>
  );
}
