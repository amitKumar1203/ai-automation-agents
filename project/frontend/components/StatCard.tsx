"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  Activity,
  CheckCircle2,
  Clock3,
  FileCheck2,
  Inbox,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

type StatColor = "default" | "amber" | "green" | "blue" | "red";

interface StatCardProps {
  label: string;
  value: number | string;
  color?: StatColor;
  delayMs?: number;
}

const valueColors: Record<StatColor, string> = {
  default: "text-white",
  amber: "text-accent-amber",
  green: "text-accent-green",
  blue: "text-accent-primary",
  red: "text-accent-red",
};

function iconForLabel(label: string): LucideIcon {
  const normalized = label.toLowerCase();
  if (normalized.includes("waiting") || normalized.includes("pending")) return Clock3;
  if (normalized.includes("escalate") || normalized.includes("reminder")) return TrendingUp;
  if (normalized.includes("clear") || normalized.includes("track") || normalized.includes("already")) return CheckCircle2;
  if (normalized.includes("po") || normalized.includes("release")) return FileCheck2;
  if (normalized.includes("email") || normalized.includes("thread")) return Inbox;
  return Activity;
}

/** Reusable summary stat card for the dashboard header row. */
export default function StatCard({
  label,
  value,
  color = "default",
  delayMs = 0,
}: StatCardProps): ReactNode {
  const reduceMotion = useReducedMotion();
  const Icon = iconForLabel(label);

  return (
    <motion.article
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 320, damping: 28, delay: delayMs / 1000 }}
      whileHover={reduceMotion ? undefined : { y: -2 }}
      className="premium-card premium-card-hover relative overflow-hidden p-5"
    >
      <div className="flex items-start justify-between gap-4">
        <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-500">
          {label}
        </span>
        <Icon className="h-4 w-4 text-slate-600" strokeWidth={1.7} aria-hidden />
      </div>
      <strong
        className={`mt-2 block font-mono text-3xl font-semibold tracking-tight ${valueColors[color]}`}
      >
        {value}
      </strong>
    </motion.article>
  );
}
