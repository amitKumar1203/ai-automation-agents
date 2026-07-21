import type { ReactNode } from "react";

import StatusPill from "@/components/StatusPill";
import type { ArtworkCardData } from "@/lib/types";

interface ArtworkCardProps {
  artwork: ArtworkCardData;
}

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <strong className="font-mono font-semibold text-white">{value}</strong>
    </div>
  );
}

function inches(value: number): string {
  return `${value.toFixed(2)} in`;
}

/** Card displaying one artwork verification analysis result. */
export default function ArtworkCard({ artwork }: ArtworkCardProps): ReactNode {
  const statusBorder =
    artwork.status === "MATCH"
      ? "border-l-accent-green"
      : artwork.status === "MISMATCH"
        ? "border-l-accent-red"
        : "border-l-accent-amber";

  return (
    <article className={`motion-rise premium-card premium-card-hover border-l-[3px] p-5 ${statusBorder}`}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <h2 className="font-mono text-lg font-bold text-white">{artwork.project_id}</h2>
        <StatusPill status={artwork.status} />
      </div>

      <div className="mb-4 rounded-xl border border-white/5 bg-white/[0.03] p-4">
        <div className="mb-3 grid gap-3 sm:grid-cols-2">
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">
              Artwork
            </p>
            <p className="font-mono text-sm text-white">
              {inches(artwork.artwork_width_inches)} ×{" "}
              {inches(artwork.artwork_height_inches)}
            </p>
          </div>
          <div>
            <p className="mb-1 text-xs uppercase tracking-wide text-slate-500">
              Spec
            </p>
            <p className="font-mono text-sm text-white">
              {inches(artwork.spec_width_inches)} ×{" "}
              {inches(artwork.spec_height_inches)}
            </p>
          </div>
        </div>
        <div className="space-y-2 border-t border-surface-border pt-3">
          <DetailRow label="Width diff" value={inches(artwork.width_diff)} />
          <DetailRow label="Height diff" value={inches(artwork.height_diff)} />
        </div>
      </div>

      <div className="space-y-2 border-t border-surface-border pt-4">
        <DetailRow label="Confidence" value={artwork.confidence} />
        <DetailRow
          label="Requires approval"
          value={artwork.requires_approval ? "Yes" : "No"}
        />
      </div>

      <p className="mt-4 text-sm leading-relaxed text-slate-200">
        {artwork.reasoning}
      </p>
    </article>
  );
}
