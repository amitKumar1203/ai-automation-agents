import type { ReactNode } from "react";

import StatusPill from "@/components/StatusPill";
import type { InstallerCardData } from "@/lib/types";

interface InstallerCardProps {
  project: InstallerCardData;
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

/** Card for one Installer Matching project result. */
export default function InstallerCard({ project }: InstallerCardProps): ReactNode {
  const statusBorder =
    project.status === "MATCHED"
      ? "border-l-accent-green"
      : project.status === "LOW_CONFIDENCE"
        ? "border-l-accent-amber"
        : project.status === "NO_MATCH"
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
        <DetailRow label="Region" value={project.install_region || "—"} />
        <DetailRow label="Install date" value={project.install_date || "—"} />
        <DetailRow
          label="Recommended installer"
          value={project.recommended_installer || "—"}
        />
        <DetailRow label="Match type" value={project.match_type || "—"} />
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

      {project.recommended_installer_email ? (
        <p className="mt-4 text-sm text-slate-300">
          Draft outreach:{" "}
          <span className="font-mono text-white">{project.recommended_installer_email}</span>
        </p>
      ) : null}

      <p className="mt-4 text-sm leading-relaxed text-slate-200">{project.reasoning}</p>
    </article>
  );
}
