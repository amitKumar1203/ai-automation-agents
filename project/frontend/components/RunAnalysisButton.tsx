"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { Play } from "lucide-react";

interface RunAnalysisButtonProps {
  loading: boolean;
  onClick: () => void;
  idleLabel?: string;
  loadingLabel?: string;
}

/** Primary action button that triggers a fresh API fetch. */
export default function RunAnalysisButton({
  loading,
  onClick,
  idleLabel = "Run Analysis",
  loadingLabel = "Running...",
}: RunAnalysisButtonProps): ReactNode {
  const reduceMotion = useReducedMotion();

  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={loading}
      whileTap={reduceMotion ? undefined : { scale: 0.98 }}
      transition={{ type: "spring", stiffness: 500, damping: 32 }}
      className={`button-press inline-flex items-center justify-center gap-2 rounded-control border border-accent-primary bg-accent-primary px-5 py-2.5 text-sm font-semibold text-background shadow-[0_8px_24px_rgb(var(--color-accent)/0.16)] hover:bg-accent-primary/90 disabled:cursor-not-allowed disabled:opacity-60 ${
        loading ? "motion-button-pulse" : ""
      }`}
    >
      {loading ? (
        <span
          className="h-4 w-4 animate-spin rounded-full border-2 border-background/30 border-t-background"
          aria-hidden="true"
        />
      ) : (
        <Play className="h-3.5 w-3.5 fill-current" aria-hidden />
      )}
      {loading ? loadingLabel : idleLabel}
    </motion.button>
  );
}
