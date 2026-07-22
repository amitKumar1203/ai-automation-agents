"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

import type { AgentStatus } from "@/lib/types";

interface StatusPillProps {
  status: AgentStatus;
}

const pillStyles: Record<AgentStatus, string> = {
  UNANSWERED: "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  OK: "status-success text-accent-green ring-1 ring-accent-green/30",
  WAITING: "status-accent text-accent-primary ring-1 ring-accent-primary/35",
  SEND_REMINDER:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  ESCALATE: "status-danger text-accent-red ring-1 ring-accent-red/35",
  INVALID_DATE: "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  ALREADY_EXISTS:
    "status-success text-accent-green ring-1 ring-accent-green/30",
  PO_READY_FOR_RELEASE:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  MATCH: "status-success text-accent-green ring-1 ring-accent-green/30",
  MISMATCH: "status-danger text-accent-red ring-1 ring-accent-red/35",
  UNCERTAIN: "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  SEND_FOLLOWUP:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  FOUND: "status-success text-accent-green ring-1 ring-accent-green/30",
  LOW_CONFIDENCE:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  NOT_FOUND: "bg-white/5 text-slate-300 ring-1 ring-white/15",
  ALREADY_ATTACHED:
    "status-success text-accent-green ring-1 ring-accent-green/30",
  MISSING_ADDRESS: "bg-white/5 text-slate-300 ring-1 ring-white/15",
  SEARCH_FAILED: "status-danger text-accent-red ring-1 ring-accent-red/35",
  MATCHED: "status-success text-accent-green ring-1 ring-accent-green/30",
  NO_MATCH: "bg-white/5 text-slate-300 ring-1 ring-white/15",
  ALREADY_ASSIGNED:
    "status-success text-accent-green ring-1 ring-accent-green/30",
  MISSING_REGION: "bg-white/5 text-slate-300 ring-1 ring-white/15",
  new_project:
    "status-accent text-accent-blue ring-1 ring-accent-blue/35",
  quote_request:
    "status-success text-accent-green ring-1 ring-accent-green/30",
  support_issue:
    "status-danger text-accent-red ring-1 ring-accent-red/35",
  general_inquiry: "bg-white/5 text-slate-300 ring-1 ring-white/15",
  unclassified:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  READY_FOR_REVIEW:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
  APPROVED_INTERNAL:
    "status-success text-accent-green ring-1 ring-accent-green/30",
  READY_FOR_EXTERNAL_SHARE:
    "status-accent text-accent-primary ring-1 ring-accent-primary/35",
  NEEDS_REVISION: "status-danger text-accent-red ring-1 ring-accent-red/35",
  ANALYZED: "status-success text-accent-green ring-1 ring-accent-green/30",
  ISSUES_FOUND: "status-danger text-accent-red ring-1 ring-accent-red/35",
  PASS: "status-success text-accent-green ring-1 ring-accent-green/30",
  FAIL: "status-danger text-accent-red ring-1 ring-accent-red/35",
  NEEDS_REVIEW:
    "status-warning text-accent-amber ring-1 ring-accent-amber/35",
};

const pillLabels: Partial<Record<AgentStatus, string>> = {
  UNANSWERED: "Needs reply",
  OK: "All clear",
  WAITING: "Waiting",
  SEND_REMINDER: "Send reminder",
  ESCALATE: "Escalate",
  INVALID_DATE: "Invalid date",
  ALREADY_EXISTS: "Already exists",
  PO_READY_FOR_RELEASE: "Ready to release",
  MATCH: "Match",
  MISMATCH: "Mismatch",
  UNCERTAIN: "Uncertain",
  SEND_FOLLOWUP: "Send follow-up",
  FOUND: "Found",
  LOW_CONFIDENCE: "Low confidence",
  NOT_FOUND: "Not found",
  ALREADY_ATTACHED: "Already attached",
  MISSING_ADDRESS: "Missing address",
  SEARCH_FAILED: "Search failed",
  MATCHED: "Matched",
  NO_MATCH: "No match",
  ALREADY_ASSIGNED: "Already assigned",
  MISSING_REGION: "Missing region",
  new_project: "New project",
  quote_request: "Quote request",
  support_issue: "Support issue",
  general_inquiry: "General inquiry",
  unclassified: "Unclassified",
  READY_FOR_REVIEW: "Ready for review",
  APPROVED_INTERNAL: "Internal OK",
  READY_FOR_EXTERNAL_SHARE: "External share",
  NEEDS_REVISION: "Needs revision",
  ANALYZED: "Analyzed",
  ISSUES_FOUND: "Issues found",
  PASS: "Pass",
  FAIL: "Fail",
  NEEDS_REVIEW: "Needs review",
};

/** Status badge pill for agent result cards. */
export default function StatusPill({ status }: StatusPillProps): ReactNode {
  const reduceMotion = useReducedMotion();

  return (
    <motion.span
      key={status}
      initial={reduceMotion ? false : { opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ type: "spring", stiffness: 420, damping: 28 }}
      title={status}
      className={`inline-flex rounded-full px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${pillStyles[status]}`}
    >
      {pillLabels[status] ?? status}
    </motion.span>
  );
}
