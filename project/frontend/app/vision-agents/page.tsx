"use client";

import Link from "next/link";
import { useId, useRef, useState, type FormEvent } from "react";
import { Camera, Layers, ScanLine, Sparkles } from "lucide-react";

import StatusPill from "@/components/StatusPill";
import {
  analyzeInstallationQcVision,
  analyzeMockupVision,
  analyzePhotoVision,
  analyzeRenderingVision,
} from "@/lib/api";
import type { AgentStatus, Phase3VisionResult } from "@/lib/types";

type TabKey = "rendering" | "mockup" | "photo" | "qc";

const TABS: { key: TabKey; label: string; icon: typeof Sparkles }[] = [
  { key: "rendering", label: "AI Rendering", icon: Sparkles },
  { key: "mockup", label: "AI Mock-up", icon: Layers },
  { key: "photo", label: "Photo Analysis", icon: Camera },
  { key: "qc", label: "Installation QC", icon: ScanLine },
];

function ResultPanel({ result }: { result: Phase3VisionResult | null }) {
  if (!result) return null;
  const status = String(result.data.status ?? "—") as AgentStatus;
  return (
    <div className="mt-6 space-y-4 rounded-xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex flex-wrap items-center gap-3">
        <StatusPill status={status} />
        <span className="text-sm text-slate-400">
          Confidence {Math.round(result.confidence * 100)}%
        </span>
        {result.final_approval_needed ? (
          <span className="rounded-full bg-accent-amber/15 px-2.5 py-0.5 text-xs font-semibold text-accent-amber">
            Needs review
          </span>
        ) : null}
      </div>
      <p className="text-sm leading-relaxed text-slate-300">{result.reasoning}</p>
      {result.entry_id ? (
        <Link
          href="/audit-log"
          className="inline-flex text-sm font-medium text-accent-primary hover:underline"
        >
          View in audit log →
        </Link>
      ) : null}
    </div>
  );
}

function FileField({
  label,
  required,
  onChange,
}: {
  label: string;
  required?: boolean;
  onChange: (file: File | null) => void;
}) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id} className="mb-1.5 block text-sm text-slate-300">
        {label}
        {required ? <span className="text-accent-red"> *</span> : null}
      </label>
      <input
        id={id}
        type="file"
        accept="image/*"
        required={required}
        className="block w-full text-sm text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-accent-primary/20 file:px-3 file:py-2 file:text-sm file:font-medium file:text-accent-primary"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </div>
  );
}

/** Phase 3 vision agents — rendering, mock-up, photo analysis, installation QC. */
export default function VisionAgentsPage() {
  const [tab, setTab] = useState<TabKey>("rendering");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<Phase3VisionResult | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  const [siteFile, setSiteFile] = useState<File | null>(null);
  const [artworkFile, setArtworkFile] = useState<File | null>(null);
  const [surveyFile, setSurveyFile] = useState<File | null>(null);
  const [installFile, setInstallFile] = useState<File | null>(null);
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [optionalArtwork, setOptionalArtwork] = useState<File | null>(null);

  const resetFiles = () => {
    setSiteFile(null);
    setArtworkFile(null);
    setSurveyFile(null);
    setInstallFile(null);
    setReferenceFile(null);
    setOptionalArtwork(null);
    formRef.current?.reset();
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);

    const form = event.currentTarget;
    const fd = new FormData(form);

    try {
      let response: Phase3VisionResult;
      if (tab === "rendering") {
        if (!siteFile) throw new Error("Site photo is required.");
        fd.set("site_image", siteFile);
        if (optionalArtwork) fd.set("artwork_image", optionalArtwork);
        response = await analyzeRenderingVision(fd);
      } else if (tab === "mockup") {
        if (!siteFile || !artworkFile) {
          throw new Error("Site photo and artwork image are required.");
        }
        fd.set("site_image", siteFile);
        fd.set("artwork_image", artworkFile);
        response = await analyzeMockupVision(fd);
      } else if (tab === "photo") {
        if (!surveyFile) throw new Error("Survey photo is required.");
        fd.set("survey_image", surveyFile);
        response = await analyzePhotoVision(fd);
      } else {
        if (!installFile || !referenceFile) {
          throw new Error("Installation and reference images are required.");
        }
        fd.set("install_image", installFile);
        fd.set("reference_image", referenceFile);
        response = await analyzeInstallationQcVision(fd);
      }
      setResult(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed.");
    } finally {
      setLoading(false);
    }
  };

  const switchTab = (next: TabKey) => {
    setTab(next);
    setError(null);
    setResult(null);
    resetFiles();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-accent-primary">
          Phase 3 · AI Vision
        </p>
        <h1 className="mt-1 text-2xl font-bold text-white">Vision Agents</h1>
        <p className="mt-2 text-sm text-slate-400">
          Upload images for rendering guidance, mock-up readiness, survey analysis, or
          installation QC. Risky results go to the audit log for human approval.
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {TABS.map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => switchTab(key)}
            className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition ${
              tab === key
                ? "bg-accent-primary/20 text-accent-primary"
                : "bg-white/5 text-slate-400 hover:bg-white/10 hover:text-white"
            }`}
          >
            <Icon className="h-4 w-4" />
            {label}
          </button>
        ))}
      </div>

      <form
        ref={formRef}
        onSubmit={onSubmit}
        className="space-y-4 rounded-xl border border-white/10 bg-white/[0.02] p-5"
      >
        <label className="block text-sm text-slate-300">
          Project ID
          <input
            name="project_id"
            placeholder="P-301"
            className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-slate-500"
          />
        </label>

        {tab === "rendering" ? (
          <>
            <FileField label="Site / storefront photo" required onChange={setSiteFile} />
            <FileField
              label="Artwork reference (optional)"
              onChange={setOptionalArtwork}
            />
            <label className="block text-sm text-slate-300">
              Design brief
              <textarea
                name="design_brief"
                rows={3}
                placeholder="48in × 36in navy logo centered on white vinyl"
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder:text-slate-500"
              />
            </label>
          </>
        ) : null}

        {tab === "mockup" ? (
          <>
            <FileField label="Site photo" required onChange={setSiteFile} />
            <FileField label="Artwork image" required onChange={setArtworkFile} />
            <label className="block text-sm text-slate-300">
              Brief
              <textarea
                name="brief"
                rows={2}
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              />
            </label>
            <label className="block text-sm text-slate-300">
              Client email (for external share gate)
              <input
                name="client_email"
                type="email"
                placeholder="client@example.com"
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              />
            </label>
          </>
        ) : null}

        {tab === "photo" ? (
          <>
            <FileField label="Survey photo" required onChange={setSurveyFile} />
            <label className="block text-sm text-slate-300">
              Context
              <textarea
                name="context"
                rows={2}
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              />
            </label>
            <label className="block text-sm text-slate-300">
              Monday item ID (optional write-back)
              <input
                name="monday_item_id"
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              />
            </label>
          </>
        ) : null}

        {tab === "qc" ? (
          <>
            <FileField label="Installation photo" required onChange={setInstallFile} />
            <FileField
              label="Approved rendering / reference"
              required
              onChange={setReferenceFile}
            />
            <label className="block text-sm text-slate-300">
              QC spec notes
              <textarea
                name="spec_notes"
                rows={2}
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              />
            </label>
            <label className="block text-sm text-slate-300">
              Monday item ID (optional QC status write-back)
              <input
                name="monday_item_id"
                className="mt-1.5 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white"
              />
            </label>
          </>
        ) : null}

        {error ? (
          <p className="rounded-lg bg-accent-red/10 px-3 py-2 text-sm text-accent-red">
            {error}
          </p>
        ) : null}

        <button
          type="submit"
          disabled={loading}
          className="rounded-lg bg-accent-primary px-4 py-2.5 text-sm font-semibold text-slate-950 disabled:opacity-50"
        >
          {loading ? "Analyzing…" : "Run analysis"}
        </button>
      </form>

      <ResultPanel result={result} />
    </div>
  );
}
