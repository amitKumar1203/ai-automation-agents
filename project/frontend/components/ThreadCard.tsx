"use client";

import type { ReactNode } from "react";
import { useCallback, useId, useState } from "react";
import { Check, ChevronRight, Copy } from "lucide-react";

import StatusPill from "@/components/StatusPill";
import ProfileAvatar from "@/components/ProfileAvatar";
import {
  formatRelativeTime,
  formatTimestamp,
  previewMessage,
  shortId,
  toPlainMessageText,
} from "@/lib/format";
import type { ThreadResult } from "@/lib/types";

interface ThreadCardProps {
  thread: ThreadResult;
  open: boolean;
  onToggle: () => void;
}

function MetaChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/5 bg-white/[0.03] px-3 py-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className="mt-0.5 font-mono text-sm font-semibold tabular-nums text-slate-100">
        {value}
      </p>
    </div>
  );
}

/** Render normalized email body as Gmail-like paragraphs (URLs become links). */
function EmailBody({ text }: { text: string }): ReactNode {
  if (!text) {
    return <p className="text-sm italic text-slate-500">(no text)</p>;
  }

  const paragraphs = text.split(/\n{2,}/);
  const urlRe = /(https?:\/\/[^\s<>"']+)/g;

  return (
    <div className="space-y-3 text-[15px] leading-relaxed text-slate-100">
      {paragraphs.map((paragraph, pIdx) => {
        const lines = paragraph.split("\n");
        return (
          <p key={`p-${pIdx}`} className="whitespace-pre-wrap break-words">
            {lines.map((line, lIdx) => {
              const parts = line.split(urlRe);
              return (
                <span key={`l-${pIdx}-${lIdx}`}>
                  {lIdx > 0 ? <br /> : null}
                  {parts.map((part, i) =>
                    /^https?:\/\//.test(part) ? (
                      <a
                        key={`u-${pIdx}-${lIdx}-${i}`}
                        href={part}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="break-all text-accent-primary underline decoration-accent-primary/40 underline-offset-2 hover:decoration-accent-primary"
                      >
                        {part.length > 64 ? `${part.slice(0, 61)}…` : part}
                      </a>
                    ) : (
                      <span key={`t-${pIdx}-${lIdx}-${i}`}>{part}</span>
                    ),
                  )}
                </span>
              );
            })}
          </p>
        );
      })}
    </div>
  );
}

function borderClass(status: ThreadResult["status"]): string {
  if (status === "CRITICAL") return "border-l-accent-red";
  if (status === "UNANSWERED") return "border-l-accent-amber";
  if (status === "AT_RISK") return "border-l-accent-primary";
  return "border-l-accent-green";
}

/** Collapsible card for one analyzed Gmail thread. */
export default function ThreadCard({
  thread,
  open,
  onToggle,
}: ThreadCardProps): ReactNode {
  const panelId = useId();
  const [copied, setCopied] = useState(false);

  const hours =
    typeof thread.hours_pending === "number"
      ? `${thread.hours_pending.toFixed(1)}h`
      : "—";
  const confidence =
    typeof thread.confidence === "number"
      ? `${Math.round(thread.confidence * 100)}%`
      : "—";
  const body = toPlainMessageText(thread.last_message_text);
  const subject = (thread.subject || "").trim();
  const fromEmail = (thread.client_email || "").trim();
  const draft = (thread.draft_reply || "").trim();
  const priority = (thread.priority || "normal").toLowerCase();
  const keywords = thread.urgency_keywords ?? [];
  const senderLabel =
    thread.last_sender === "client"
      ? "Client"
      : thread.last_sender === "internal"
        ? "Internal"
        : thread.last_sender === "team"
          ? "Team"
          : thread.last_sender || "Unknown";
  const senderChipClass =
    thread.last_sender === "client"
      ? "bg-accent-primary/15 text-accent-primary"
      : thread.last_sender === "internal"
        ? "bg-slate-500/15 text-slate-400"
        : "bg-white/5 text-slate-300";
  const needsAttention =
    thread.status === "UNANSWERED" ||
    thread.status === "CRITICAL" ||
    thread.status === "AT_RISK";
  const headline = subject || previewMessage(body);

  const copyDraft = useCallback(async () => {
    if (!draft) return;
    try {
      await navigator.clipboard.writeText(draft);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  }, [draft]);

  return (
    <article
      className={`motion-rise premium-card premium-card-hover overflow-hidden border-l-[3px] ${borderClass(thread.status)}`}
    >
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={onToggle}
        className="button-press flex w-full items-start gap-3 px-4 py-4 text-left hover:bg-white/[0.02] sm:px-5"
      >
        <span
          className={`mt-1 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-surface-border text-slate-400 transition ${
            open ? "rotate-90 bg-white/5 text-white" : ""
          }`}
          aria-hidden="true"
        >
          <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill status={thread.status} />
            {priority === "high" && (
              <span className="rounded-full bg-accent-red/15 px-2 py-0.5 text-[11px] font-semibold text-accent-red">
                High priority
              </span>
            )}
            <span
              className={`rounded-full px-2 py-0.5 text-[11px] font-semibold ${senderChipClass}`}
            >
              {senderLabel}
            </span>
            <span className="font-mono text-[11px] text-slate-500" title={thread.thread_id}>
              {shortId(thread.thread_id)}
            </span>
          </div>

          <p className="mt-2 truncate text-sm font-medium text-slate-100">
            {headline}
          </p>
          {subject ? (
            <p className="mt-1 line-clamp-1 text-sm leading-relaxed text-slate-400">
              {previewMessage(body)}
            </p>
          ) : null}

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span className="font-mono" title={formatTimestamp(thread.last_message_timestamp)}>
              {formatRelativeTime(thread.last_message_timestamp)}
            </span>
            <span aria-hidden="true">·</span>
            <span className="font-mono">{hours} pending</span>
            {!open && needsAttention && (
              <>
                <span aria-hidden="true">·</span>
                <span
                  className={`font-medium ${
                    thread.status === "CRITICAL"
                      ? "text-accent-red"
                      : thread.status === "AT_RISK"
                        ? "text-accent-primary"
                        : "text-accent-amber"
                  }`}
                >
                  Needs attention
                </span>
              </>
            )}
          </div>
        </div>
      </button>

      <div id={panelId} hidden={!open} className="border-t border-surface-border px-4 pb-5 pt-4 sm:px-5">
        <div className="overflow-hidden rounded-xl border border-white/5 bg-background">
          <div className="border-b border-white/5 px-4 py-3 sm:px-5">
            <h3 className="text-base font-semibold leading-snug text-white">
              {subject || "(No subject)"}
            </h3>
            <div className="mt-3 flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 items-start gap-3">
                <ProfileAvatar
                  name={senderLabel}
                  email={fromEmail}
                  size="md"
                />
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-100">
                    {senderLabel}
                    {fromEmail ? (
                      <span className="ml-1.5 font-normal text-slate-400">
                        &lt;{fromEmail}&gt;
                      </span>
                    ) : null}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">to me</p>
                </div>
              </div>
              <time
                className="shrink-0 font-mono text-xs text-slate-500"
                title={thread.last_message_timestamp}
              >
                {formatTimestamp(thread.last_message_timestamp)}
              </time>
            </div>
          </div>
          <div className="px-4 py-4 sm:px-5">
            <EmailBody text={body} />
          </div>
        </div>

        {keywords.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {keywords.map((kw) => (
              <span
                key={kw}
                className="rounded-md bg-accent-red/10 px-2 py-0.5 text-[11px] font-medium text-accent-red"
              >
                {kw}
              </span>
            ))}
          </div>
        )}

        {draft ? (
          <div className="mt-4 overflow-hidden rounded-xl border border-accent-primary/20 bg-accent-primary/5">
            <div className="flex items-center justify-between gap-2 border-b border-accent-primary/15 px-3 py-2">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-accent-primary">
                Suggested reply
              </p>
              <button
                type="button"
                onClick={() => void copyDraft()}
                className="button-press inline-flex items-center gap-1.5 rounded-lg border border-surface-border bg-surface-card px-2.5 py-1 text-[11px] font-semibold text-slate-300 hover:text-white"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-accent-green" aria-hidden />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" aria-hidden />
                    Copy
                  </>
                )}
              </button>
            </div>
            <pre className="whitespace-pre-wrap break-words px-3 py-3 font-sans text-sm leading-relaxed text-slate-200">
              {draft}
            </pre>
          </div>
        ) : null}

        <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetaChip label="Pending" value={hours} />
          <MetaChip label="Priority" value={priority === "high" ? "High" : "Normal"} />
          <MetaChip label="Confidence" value={confidence} />
          <MetaChip
            label="Approval"
            value={thread.requires_approval ? "Yes" : "No"}
          />
        </div>

        <p className="mt-4 rounded-xl border border-surface-border bg-white/[0.02] px-3 py-3 text-sm leading-relaxed text-slate-300">
          {thread.reasoning}
        </p>
      </div>
    </article>
  );
}
