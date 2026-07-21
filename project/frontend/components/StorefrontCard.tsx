import type { ReactNode } from "react";

import StatusPill from "@/components/StatusPill";
import type { StorefrontCardData } from "@/lib/types";

interface StorefrontCardProps {
  project: StorefrontCardData;
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <strong className="max-w-[60%] truncate text-right font-mono font-semibold text-white">
        {value}
      </strong>
    </div>
  );
}

/** Card for one Storefront Search project result. */
export default function StorefrontCard({ project }: StorefrontCardProps): ReactNode {
  const statusBorder =
    project.status === "FOUND"
      ? "border-l-accent-green"
      : project.status === "LOW_CONFIDENCE"
        ? "border-l-accent-amber"
        : project.status === "NOT_FOUND"
          ? "border-l-slate-500"
          : "border-l-accent-primary";

  return (
    <article
      className={`motion-rise premium-card premium-card-hover border-l-[3px] p-5 ${statusBorder}`}
    >
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-bold text-white">{project.project_name}</h2>
          <p className="mt-1 font-mono text-sm font-semibold text-slate-300">
            {project.project_id}
          </p>
        </div>
        <StatusPill status={project.status} />
      </div>

      <div className="space-y-2 border-t border-surface-border pt-4">
        <DetailRow label="Address" value={project.store_address || "—"} />
        <DetailRow label="Source" value={project.image_source || "—"} />
        <DetailRow
          label="Match confidence"
          value={
            project.match_confidence !== null && project.match_confidence !== undefined
              ? `${Math.round(project.match_confidence * 100)}%`
              : "—"
          }
        />
        <DetailRow label="Requires approval" value={project.requires_approval ? "Yes" : "No"} />
      </div>

      {project.image_url ? (
        <a
          href={project.image_url}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-flex text-sm font-semibold text-accent-primary hover:underline"
        >
          Preview candidate image
        </a>
      ) : null}

      <p className="mt-4 text-sm leading-relaxed text-slate-200">{project.reasoning}</p>
    </article>
  );
}
