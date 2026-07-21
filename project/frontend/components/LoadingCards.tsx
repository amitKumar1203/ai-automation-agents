import type { ReactNode } from "react";

export default function LoadingCards({
  count = 3,
  compact = false,
}: {
  count?: number;
  compact?: boolean;
}): ReactNode {
  return (
    <div className={`grid gap-3 ${compact ? "sm:grid-cols-2 lg:grid-cols-4" : ""}`} aria-label="Loading">
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          className={`premium-card p-5 ${compact ? "h-28" : "h-36"}`}
          aria-hidden
        >
          <div className="skeleton h-3 w-24 rounded-full" />
          <div className="skeleton mt-5 h-7 w-16 rounded-md" />
          {!compact && <div className="skeleton mt-7 h-3 w-3/4 rounded-full" />}
        </div>
      ))}
    </div>
  );
}
