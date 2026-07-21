import type { IntakeStatus } from "@/lib/types";

function presentation(status: IntakeStatus): { label: string; style: string } {
  if (status === "completed") {
    return { label: "Completed", style: "status-success text-accent-green ring-accent-green/30" };
  }
  if (status === "awaiting_approval") {
    return { label: "Awaiting review", style: "status-warning text-accent-amber ring-accent-amber/35" };
  }
  if (status === "rejected") {
    return { label: "Rejected", style: "status-danger text-accent-red ring-accent-red/35" };
  }
  if (status.endsWith("_dead")) {
    return { label: `${status.split("_")[0]} dead`, style: "status-danger text-accent-red ring-accent-red/35" };
  }
  if (status.endsWith("_retrying")) {
    return { label: `${status.split("_")[0]} retrying`, style: "status-warning text-accent-amber ring-accent-amber/35" };
  }
  if (status.endsWith("_queued") || status === "received") {
    return { label: status === "received" ? "Received" : `${status.split("_")[0]} queued`, style: "status-accent text-accent-primary ring-accent-primary/35" };
  }
  if (status.endsWith("_running")) {
    return { label: `${status.split("_")[0]} running`, style: "bg-white/5 text-slate-300 ring-white/15" };
  }
  return { label: status.replaceAll("_", " "), style: "bg-white/5 text-slate-300 ring-white/15" };
}

export default function IntakeStatusBadge({ status }: { status: IntakeStatus }) {
  const item = presentation(status);
  return (
    <span
      title={status}
      className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] ring-1 ${item.style}`}
    >
      {item.label}
    </span>
  );
}
