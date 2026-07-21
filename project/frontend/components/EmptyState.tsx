import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export default function EmptyState({
  message,
}: {
  message: string;
}): ReactNode {
  return (
    <div className="rounded-card border border-dashed border-surface-border bg-surface-card/50 px-5 py-10 text-center">
      <span className="mx-auto flex h-10 w-10 items-center justify-center rounded-full border border-surface-border bg-white/[0.025]">
        <Inbox className="h-4 w-4 text-slate-500" strokeWidth={1.7} aria-hidden />
      </span>
      <p className="mx-auto mt-3 max-w-md text-sm text-slate-400">{message}</p>
    </div>
  );
}
