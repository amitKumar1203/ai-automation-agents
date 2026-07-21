"use client";

import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type DragEvent,
  type ReactNode,
} from "react";
import { motion, useReducedMotion } from "framer-motion";
import { ImageIcon, Ruler, ScanLine } from "lucide-react";

import ArtworkCard from "@/components/ArtworkCard";
import StatusPill from "@/components/StatusPill";
import { verifyArtworkNumeric, verifyArtworkVision } from "@/lib/api";
import type {
  ArtworkCardData,
  ArtworkStatus,
  ArtworkVisionResult,
} from "@/lib/types";

type TabKey = "numeric" | "vision";

const SPEC_EXAMPLES = [
  "Window vinyl 48in × 36in, navy logo centered on white",
  "Storefront banner 72in × 24in, red SALE text only",
  "60in × 40in black text on clear vinyl, no bleed",
] as const;

function DetailRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-sm">
      <span className="text-slate-400">{label}</span>
      <strong className="font-semibold text-white">{value}</strong>
    </div>
  );
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(Math.max(0, Math.min(1, value)) * 100);
  const tone =
    pct >= 75 ? "bg-accent-green" : pct >= 50 ? "bg-accent-amber" : "bg-accent-red";
  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-400">Confidence</span>
        <strong className="font-semibold text-white">{pct}%</strong>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full rounded-full transition-all duration-500 ${tone}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function StepBadge({ n, done }: { n: number; done?: boolean }) {
  return (
    <span
      className={`inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-[11px] font-bold ${
        done
          ? "bg-accent-green/20 text-accent-green"
          : "bg-accent-primary/15 text-accent-primary"
      }`}
    >
      {done ? "✓" : n}
    </span>
  );
}

interface DropZoneProps {
  id: string;
  label: string;
  hint: string;
  file: File | null;
  previewUrl?: string | null;
  required?: boolean;
  invalid?: boolean;
  onFile: (file: File | null) => void;
}

function DropZone({
  id,
  label,
  hint,
  file,
  previewUrl,
  required,
  invalid,
  onFile,
}: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const pick = (next: File | null) => {
    if (next && !next.type.startsWith("image/")) {
      return;
    }
    onFile(next);
  };

  const onDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files?.[0] ?? null;
    pick(dropped);
  };

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <label htmlFor={id} className="text-sm text-slate-300">
          {label}
          {required ? <span className="text-accent-red"> *</span> : null}
        </label>
        {file ? (
          <button
            type="button"
            onClick={() => {
              onFile(null);
              if (inputRef.current) {
                inputRef.current.value = "";
              }
            }}
            className="text-xs font-medium text-slate-400 transition hover:text-accent-red"
          >
            Remove
          </button>
        ) : null}
      </div>

      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`cursor-pointer rounded-2xl border border-dashed px-4 py-5 transition ${
          invalid
            ? "border-accent-red/50 bg-accent-red/5"
            : dragging
              ? "border-accent-primary/60 bg-accent-primary/10"
              : file
                ? "border-accent-primary/35 bg-accent-primary/[0.06]"
                : "border-surface-border bg-black/20 hover:border-white/20 hover:bg-white/[0.03]"
        }`}
      >
        <input
          ref={inputRef}
          id={id}
          type="file"
          accept="image/jpeg,image/png,image/gif,image/webp"
          className="sr-only"
          onChange={(e: ChangeEvent<HTMLInputElement>) => {
            pick(e.target.files?.[0] ?? null);
          }}
        />

        {previewUrl ? (
          <div className="flex items-center gap-4">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewUrl}
              alt=""
              className="h-20 w-20 shrink-0 rounded-xl object-cover ring-1 ring-white/10"
            />
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">{file?.name}</p>
              <p className="mt-0.5 text-xs text-slate-500">
                {file ? `${(file.size / 1024).toFixed(0)} KB · click to replace` : ""}
              </p>
            </div>
          </div>
        ) : (
          <div className="text-center">
            <ImageIcon className="mx-auto mb-2 h-5 w-5 text-slate-600" strokeWidth={1.7} aria-hidden />
            <p className="text-sm font-medium text-slate-200">
              Drop image here, or click to browse
            </p>
            <p className="mt-1 text-xs text-slate-500">{hint}</p>
          </div>
        )}
      </div>
    </div>
  );
}

/** Artwork Verification dashboard — numeric comparison + vision upload. */
export default function ArtworkAgentPage() {
  const artworkInputId = useId();
  const specInputId = useId();

  const [tab, setTab] = useState<TabKey>("numeric");
  const reduceMotion = useReducedMotion();

  // Numeric form
  const [numProjectId, setNumProjectId] = useState("");
  const [artW, setArtW] = useState("");
  const [artH, setArtH] = useState("");
  const [specW, setSpecW] = useState("");
  const [specH, setSpecH] = useState("");
  const [numericLoading, setNumericLoading] = useState(false);
  const [numericError, setNumericError] = useState<string | null>(null);
  const [numericResult, setNumericResult] = useState<ArtworkCardData | null>(null);

  // Vision form
  const [artworkFile, setArtworkFile] = useState<File | null>(null);
  const [artworkPreviewUrl, setArtworkPreviewUrl] = useState<string | null>(null);
  const [specImageFile, setSpecImageFile] = useState<File | null>(null);
  const [specPreviewUrl, setSpecPreviewUrl] = useState<string | null>(null);
  const [specDescription, setSpecDescription] = useState("");
  const [projectId, setProjectId] = useState("");
  const [visionLoading, setVisionLoading] = useState(false);
  const [visionError, setVisionError] = useState<string | null>(null);
  const [visionResult, setVisionResult] = useState<ArtworkVisionResult | null>(null);
  const [artworkInvalid, setArtworkInvalid] = useState(false);
  const [specFieldInvalid, setSpecFieldInvalid] = useState(false);

  useEffect(() => {
    if (!artworkFile) {
      setArtworkPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(artworkFile);
    setArtworkPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [artworkFile]);

  useEffect(() => {
    if (!specImageFile) {
      setSpecPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(specImageFile);
    setSpecPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [specImageFile]);

  const canVerifyNumeric = useMemo(() => {
    const vals = [artW, artH, specW, specH].map((v) => Number(v));
    return vals.every((n) => Number.isFinite(n) && n > 0);
  }, [artW, artH, specW, specH]);

  const canVerify = useMemo(
    () => Boolean(artworkFile && (specDescription.trim() || specImageFile)),
    [artworkFile, specDescription, specImageFile],
  );

  const setArtwork = (file: File | null) => {
    setArtworkFile(file);
    setArtworkInvalid(false);
    setVisionResult(null);
    setVisionError(null);
  };

  const setSpecImage = (file: File | null) => {
    setSpecImageFile(file);
    if (file) {
      setSpecFieldInvalid(false);
    }
    setVisionResult(null);
    setVisionError(null);
  };

  const runNumericCheck = async () => {
    if (!canVerifyNumeric) {
      setNumericError("Enter all four dimensions as positive numbers (inches).");
      return;
    }
    setNumericLoading(true);
    setNumericError(null);
    setNumericResult(null);
    try {
      const result = await verifyArtworkNumeric({
        project_id: numProjectId.trim(),
        artwork_width_inches: Number(artW),
        artwork_height_inches: Number(artH),
        spec_width_inches: Number(specW),
        spec_height_inches: Number(specH),
      });
      setNumericResult(result);
    } catch (err) {
      setNumericError(
        err instanceof Error ? err.message : "Numeric verification failed.",
      );
    } finally {
      setNumericLoading(false);
    }
  };

  const runVisionCheck = async () => {
    let blocked = false;
    if (!artworkFile) {
      setArtworkInvalid(true);
      setVisionError("Upload an artwork image first.");
      blocked = true;
    }
    if (!specDescription.trim() && !specImageFile) {
      setSpecFieldInvalid(true);
      setVisionError(
        blocked
          ? "Upload artwork, then add a spec description or reference image."
          : "Add what the artwork should match — type a description or upload a reference image.",
      );
      blocked = true;
    }
    if (blocked) {
      return;
    }

    setArtworkInvalid(false);
    setSpecFieldInvalid(false);
    setVisionLoading(true);
    setVisionError(null);
    setVisionResult(null);

    try {
      const formData = new FormData();
      formData.append("artwork_image", artworkFile!);
      formData.append("spec_description", specDescription.trim());
      formData.append("project_id", projectId.trim());
      if (specImageFile) {
        formData.append("spec_image", specImageFile);
      }
      const response = await verifyArtworkVision(formData);
      setVisionResult(response);
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : "Vision verification failed. Check ANTHROPIC_API_KEY and the API.";
      setVisionError(message);
    } finally {
      setVisionLoading(false);
    }
  };

  const visionStatus = (visionResult?.data?.status ?? "UNCERTAIN") as ArtworkStatus;
  const requiresApproval =
    visionResult?.final_approval_needed ?? visionResult?.requires_approval ?? false;
  const visionBorder =
    visionStatus === "MATCH"
      ? "border-l-accent-green"
      : visionStatus === "MISMATCH"
        ? "border-l-accent-red"
        : "border-l-accent-amber";

  const approvalHint =
    visionStatus === "MATCH" && !requiresApproval
      ? "Looks clear — no human review required by policy."
      : visionStatus === "UNCERTAIN"
        ? "AI isn’t sure — a human should review before clearing."
        : "Flagged for human approval before any write-back.";

  const dimInputClass =
    "control-input px-3.5 py-2.5 text-sm placeholder:text-slate-600";

  return (
    <div className="page-shell">
      <header className="mb-8">
        <div className="max-w-2xl">
          <p className="page-eyebrow">Spec match before production</p>
          <h1 className="page-title">Artwork Verification</h1>
          <p className="page-subtitle">
            Enter known dimensions for a ±0.25 in check, or upload a proof for
            vision analysis — no mock sample data.
          </p>
        </div>
      </header>

      {/* Segmented mode switch */}
      <div
        role="tablist"
        aria-label="Verification mode"
        className="mb-8 inline-flex w-full max-w-md rounded-control border border-surface-border bg-surface-card p-1 sm:w-auto"
      >
        {(
          [
            { key: "numeric" as const, label: "Numeric", sub: "±0.25 in" },
            { key: "vision" as const, label: "Vision", sub: "Image upload" },
          ] as const
        ).map((item) => {
          const active = tab === item.key;
          return (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(item.key)}
              className={`button-press relative flex flex-1 flex-col items-start rounded-lg px-4 py-2.5 text-left sm:min-w-[140px] sm:flex-none ${
                active
                  ? "text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {active && (
                <motion.span
                  layoutId="artwork-mode-active"
                  transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 430, damping: 34 }}
                  className="absolute inset-0 rounded-lg border border-accent-primary/25 bg-accent-primary/12"
                />
              )}
              <span className="relative text-sm font-semibold">{item.label}</span>
              <span className="relative text-[11px] text-slate-500">{item.sub}</span>
            </button>
          );
        })}
      </div>

      {tab === "numeric" && (
        <section className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          <div className="motion-rise premium-card p-5 md:p-6">
            <div className="mb-6">
              <h2 className="font-display text-lg font-semibold text-white">
                Dimension check
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-400">
                Compare submitted artwork size to the project window spec.
                Match within ±0.25 in; anything wider needs approval.
              </p>
            </div>

            <div className="space-y-5">
              <label className="block text-sm">
                <span className="mb-1.5 block text-slate-300">
                  Project ID{" "}
                  <span className="font-normal text-slate-500">(optional)</span>
                </span>
                <input
                  type="text"
                  value={numProjectId}
                  onChange={(e) => setNumProjectId(e.target.value)}
                  placeholder="PRJ-123"
                  className={dimInputClass}
                />
              </label>

              <div>
                <p className="mb-2 text-sm font-medium text-slate-200">
                  Artwork size <span className="text-accent-red">*</span>
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-xs text-slate-400">
                    Width (in)
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={artW}
                      onChange={(e) => {
                        setArtW(e.target.value);
                        setNumericError(null);
                      }}
                      placeholder="48"
                      className={`mt-1.5 ${dimInputClass}`}
                    />
                  </label>
                  <label className="block text-xs text-slate-400">
                    Height (in)
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={artH}
                      onChange={(e) => {
                        setArtH(e.target.value);
                        setNumericError(null);
                      }}
                      placeholder="36"
                      className={`mt-1.5 ${dimInputClass}`}
                    />
                  </label>
                </div>
              </div>

              <div>
                <p className="mb-2 text-sm font-medium text-slate-200">
                  Spec size <span className="text-accent-red">*</span>
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <label className="block text-xs text-slate-400">
                    Width (in)
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={specW}
                      onChange={(e) => {
                        setSpecW(e.target.value);
                        setNumericError(null);
                      }}
                      placeholder="48"
                      className={`mt-1.5 ${dimInputClass}`}
                    />
                  </label>
                  <label className="block text-xs text-slate-400">
                    Height (in)
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      step="0.01"
                      value={specH}
                      onChange={(e) => {
                        setSpecH(e.target.value);
                        setNumericError(null);
                      }}
                      placeholder="36"
                      className={`mt-1.5 ${dimInputClass}`}
                    />
                  </label>
                </div>
              </div>

              <button
                type="button"
                disabled={numericLoading}
                onClick={() => void runNumericCheck()}
                className={`button-press inline-flex w-full items-center justify-center gap-2 rounded-control px-4 py-3 text-sm font-semibold disabled:cursor-not-allowed ${
                  canVerifyNumeric && !numericLoading
                    ? "bg-accent-primary text-background hover:bg-accent-primary/90"
                    : "bg-white/10 text-slate-400"
                } ${numericLoading ? "motion-button-pulse" : ""}`}
              >
                {numericLoading && (
                  <span
                    className="h-4 w-4 animate-spin rounded-full border-2 border-background/30 border-t-background"
                    aria-hidden
                  />
                )}
                {numericLoading ? "Checking…" : "Compare dimensions"}
              </button>

              {!canVerifyNumeric && !numericError ? (
                <p className="text-center text-xs text-slate-500">
                  Enter artwork + spec width and height to enable compare.
                </p>
              ) : null}

              {numericError ? (
                <div
                  role="alert"
                  className="rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm text-red-200"
                >
                  {numericError}
                </div>
              ) : null}
            </div>
          </div>

          <div className="lg:sticky lg:top-6">
            {numericResult ? (
              <ArtworkCard artwork={numericResult} />
            ) : (
              <div className="rounded-card border border-dashed border-surface-border bg-surface-card/40 px-6 py-14 text-center">
                <Ruler className="mx-auto mb-3 h-5 w-5 text-slate-600" aria-hidden />
                <p className="text-sm font-medium text-slate-300">
                  Result appears here
                </p>
                <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-slate-500">
                  Enter sizes and run Compare. MATCH stays within ±0.25 in;
                  MISMATCH is sent for human approval.
                </p>
              </div>
            )}
          </div>
        </section>
      )}

      {tab === "vision" && (
        <section className="grid items-start gap-6 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,0.95fr)]">
          {/* Form panel */}
          <div className="motion-rise premium-card p-5 md:p-6">
            <div className="mb-6">
              <h2 className="font-display text-lg font-semibold text-white">
                Vision check
              </h2>
              <p className="mt-1 text-sm leading-relaxed text-slate-400">
                Upload a proof, describe the expected spec, then run analysis.
                MISMATCH and UNCERTAIN always go to human review.
              </p>
            </div>

            <ol className="space-y-6">
              <li className="space-y-3">
                <div className="flex items-center gap-2">
                  <StepBadge n={1} done={Boolean(artworkFile)} />
                  <span className="text-sm font-medium text-slate-200">
                    Artwork to verify
                  </span>
                </div>
                <DropZone
                  id={artworkInputId}
                  label="Artwork image"
                  hint="PNG, JPG, WebP · clear photo or export works best"
                  file={artworkFile}
                  previewUrl={artworkPreviewUrl}
                  required
                  invalid={artworkInvalid}
                  onFile={setArtwork}
                />
              </li>

              <li className="space-y-3">
                <div className="flex items-center gap-2">
                  <StepBadge
                    n={2}
                    done={Boolean(specDescription.trim() || specImageFile)}
                  />
                  <span className="text-sm font-medium text-slate-200">
                    What should it match?
                  </span>
                </div>

                <div>
                  <label
                    htmlFor="spec-description"
                    className="mb-1.5 block text-sm text-slate-300"
                  >
                    Spec description
                    <span className="text-accent-red"> *</span>
                    <span className="ml-1 font-normal text-slate-500">
                      (or reference image)
                    </span>
                  </label>
                  <textarea
                    id="spec-description"
                    value={specDescription}
                    onChange={(e) => {
                      setSpecDescription(e.target.value);
                      if (e.target.value.trim()) {
                        setSpecFieldInvalid(false);
                        setVisionError(null);
                      }
                    }}
                    rows={3}
                    placeholder="Size, colors, layout — e.g. 48in × 36in navy logo on white"
                    className={`control-input w-full resize-y px-3.5 py-2.5 text-sm leading-relaxed placeholder:text-slate-600 ${
                      specFieldInvalid
                        ? "border border-accent-red/60 focus:border-accent-red"
                        : "border border-surface-border focus:border-accent-primary/50"
                    }`}
                  />
                  <div className="mt-2 flex flex-wrap gap-2">
                    {SPEC_EXAMPLES.map((example) => (
                      <button
                        key={example}
                        type="button"
                        onClick={() => {
                          setSpecDescription(example);
                          setSpecFieldInvalid(false);
                          setVisionError(null);
                        }}
                        className="rounded-lg border border-surface-border bg-white/[0.03] px-2.5 py-1 text-left text-[11px] leading-snug text-slate-400 transition hover:border-accent-primary/35 hover:text-slate-200"
                      >
                        {example.length > 42 ? `${example.slice(0, 42)}…` : example}
                      </button>
                    ))}
                  </div>
                </div>

                <DropZone
                  id={specInputId}
                  label="Reference spec image"
                  hint="Optional approved mockup or marked-up drawing"
                  file={specImageFile}
                  previewUrl={specPreviewUrl}
                  invalid={specFieldInvalid && !specDescription.trim()}
                  onFile={setSpecImage}
                />
              </li>

              <li className="space-y-3">
                <div className="flex items-center gap-2">
                  <StepBadge n={3} />
                  <span className="text-sm font-medium text-slate-200">
                    Context & run
                  </span>
                </div>

                <label className="block text-sm">
                  <span className="mb-1.5 block text-slate-300">
                    Project ID{" "}
                    <span className="font-normal text-slate-500">(optional)</span>
                  </span>
                  <input
                    type="text"
                    value={projectId}
                    onChange={(e) => setProjectId(e.target.value)}
                    placeholder="PRJ-123"
                    className="control-input px-3.5 py-2.5 text-sm placeholder:text-slate-600"
                  />
                </label>

                <button
                  type="button"
                  disabled={visionLoading}
                  onClick={() => void runVisionCheck()}
                  className={`button-press inline-flex w-full items-center justify-center gap-2 rounded-control px-4 py-3 text-sm font-semibold disabled:cursor-not-allowed ${
                    canVerify && !visionLoading
                      ? "bg-accent-primary text-background hover:bg-accent-primary/90"
                      : "bg-white/10 text-slate-400"
                  } ${visionLoading ? "motion-button-pulse" : ""}`}
                >
                  {visionLoading && (
                    <span
                      className="h-4 w-4 animate-spin rounded-full border-2 border-background/30 border-t-background"
                      aria-hidden
                    />
                  )}
                  {visionLoading ? "Analyzing image…" : "Verify with vision"}
                </button>

                {!canVerify && !visionError ? (
                  <p className="text-center text-xs text-slate-500">
                    Add artwork + a spec (text or image) to enable Verify.
                  </p>
                ) : null}
              </li>
            </ol>

            {visionError ? (
              <div
                role="alert"
                className="mt-5 rounded-control border border-accent-red/30 bg-accent-red/10 px-4 py-3 text-sm leading-relaxed text-red-200"
              >
                {visionError}
              </div>
            ) : null}
          </div>

          {/* Results panel */}
          <div className="lg:sticky lg:top-6">
            {visionLoading ? (
              <div className="motion-analyze rounded-2xl border border-accent-primary/25 px-6 py-14 text-center">
                <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2 border-accent-primary/25 border-t-accent-primary" />
                <p className="text-sm font-medium text-white">Analyzing image…</p>
                <p className="mx-auto mt-2 max-w-xs text-xs leading-relaxed text-slate-400">
                  Claude is reading the proof against your spec. This usually
                  takes a few seconds.
                </p>
              </div>
            ) : null}

            {visionResult && !visionLoading ? (
              <article className={`motion-rise premium-card border-l-[3px] p-5 md:p-6 ${visionBorder}`}>
                <div className="mb-5 flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                      Vision result
                    </p>
                    <h2 className="mt-1 font-mono text-lg font-bold text-white">
                      {String(visionResult.data.project_id || "vision-upload")}
                    </h2>
                  </div>
                  <StatusPill status={visionStatus} />
                </div>

                <div className="mb-5 grid gap-4 sm:grid-cols-[120px_1fr]">
                  {artworkPreviewUrl ? (
                    <div className="overflow-hidden rounded-xl border border-white/10 bg-black/30">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={artworkPreviewUrl}
                        alt="Verified artwork"
                        className="aspect-square h-full w-full object-cover"
                      />
                    </div>
                  ) : null}
                  <div className="space-y-3 rounded-xl border border-white/5 bg-white/[0.03] p-4">
                    <ConfidenceBar value={visionResult.confidence} />
                    <DetailRow
                      label="Requires approval"
                      value={requiresApproval ? "Yes" : "No"}
                    />
                    <DetailRow
                      label="Dimensions visible"
                      value={visionResult.data.dimensions_visible ? "Yes" : "No"}
                    />
                  </div>
                </div>

                <p className="mb-4 rounded-xl border border-white/5 bg-black/20 px-3.5 py-3 text-sm leading-relaxed text-slate-200">
                  {visionResult.reasoning}
                </p>

                <p className="text-xs leading-relaxed text-slate-500">
                  {approvalHint} Review decisions live in{" "}
                  <a
                    href="/audit-log"
                    className="text-accent-primary underline-offset-2 hover:underline"
                  >
                    Audit Log
                  </a>
                  .
                </p>
              </article>
            ) : null}

            {!visionLoading && !visionResult ? (
              <div className="rounded-card border border-dashed border-surface-border bg-surface-card/40 px-6 py-14 text-center">
                <ScanLine className="mx-auto mb-3 h-5 w-5 text-slate-600" aria-hidden />
                <p className="text-sm font-medium text-slate-300">
                  Results show up here
                </p>
                <p className="mx-auto mt-2 max-w-sm text-xs leading-relaxed text-slate-500">
                  After Verify, you’ll see match status, confidence, and
                  reasoning next to your artwork thumbnail.
                </p>
                <ul className="mx-auto mt-5 max-w-xs space-y-2 text-left text-xs text-slate-500">
                  <li className="flex gap-2">
                    <span className="text-accent-green">●</span>
                    MATCH — clear fit to the spec
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent-red">●</span>
                    MISMATCH — size/design issue found
                  </li>
                  <li className="flex gap-2">
                    <span className="text-accent-amber">●</span>
                    UNCERTAIN — needs a human look
                  </li>
                </ul>
              </div>
            ) : null}
          </div>
        </section>
      )}
    </div>
  );
}
