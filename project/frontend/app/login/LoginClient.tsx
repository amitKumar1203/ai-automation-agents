"use client";

import { FormEvent, useState } from "react";
import { signIn } from "next-auth/react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";
import { LockKeyhole, ShieldCheck } from "lucide-react";

/** Google Workspace login with an explicitly configured password fallback. */
export default function LoginClient({
  localFallback,
  googleConfigured,
}: {
  localFallback: boolean;
  googleConfigured: boolean;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(
    searchParams.get("error") === "config"
      ? "Dashboard password is not configured. Set DASHBOARD_PASSWORD on Vercel."
      : null,
  );
  const [loading, setLoading] = useState(false);
  const [shakeKey, setShakeKey] = useState(0);
  const reduceMotion = useReducedMotion();
  const requestedNext = searchParams.get("next") || "/";
  const safeNext =
    requestedNext.startsWith("/") && !requestedNext.startsWith("//")
      ? requestedNext
      : "/";

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as {
          error?: string;
        } | null;
        setError(payload?.error ?? "Incorrect password");
        setShakeKey((key) => key + 1);
        return;
      }
      router.replace(safeNext);
      router.refresh();
    } catch {
      setError("Login failed. Please try again.");
      setShakeKey((key) => key + 1);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-background relative flex min-h-screen items-center justify-center overflow-hidden px-5">
      <div className="pointer-events-none absolute inset-0 [background:radial-gradient(circle_at_50%_32%,rgb(var(--color-accent)/0.12),transparent_38%)]" />
      <motion.div
        initial={reduceMotion ? false : { opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring", stiffness: 280, damping: 26 }}
        className="relative w-full max-w-md rounded-card border border-surface-border bg-surface-card/85 p-7 shadow-2xl backdrop-blur-xl sm:p-8"
      >
        <span className="mb-6 flex h-10 w-10 items-center justify-center rounded-control border border-accent-primary/25 bg-accent-primary/10">
          <ShieldCheck className="h-5 w-5 text-accent-primary" strokeWidth={1.8} aria-hidden />
        </span>
        <p className="page-eyebrow">
          Softude Ops Console
        </p>
        <h1 className="font-display text-2xl font-bold tracking-tight text-white">
          Sign in
        </h1>
        <p className="mt-2 text-sm leading-loose text-slate-400">
          {googleConfigured
            ? "Use your approved Google Workspace account to view agents and approvals."
            : "Enter the dashboard password to view agents and approvals."}
        </p>

        {googleConfigured && (
          <button
            type="button"
            onClick={() => void signIn("google", { callbackUrl: safeNext })}
            className="button-press mt-6 w-full rounded-control border border-accent-primary bg-accent-primary px-4 py-2.5 text-sm font-semibold text-background hover:bg-accent-primary/90"
          >
            Continue with Google
          </button>
        )}

        {localFallback && <form onSubmit={onSubmit} className="mt-6 space-y-4">
          {googleConfigured && (
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Password fallback
            </p>
          )}
          <div>
            <label
              htmlFor="dashboard-password"
              className="mb-1.5 block text-sm text-slate-400"
            >
              Password
            </label>
            <motion.div
              key={shakeKey}
              animate={shakeKey > 0 && !reduceMotion ? { x: [0, -5, 4, -2, 0] } : undefined}
              transition={{ duration: 0.32 }}
              className="relative"
            >
              <LockKeyhole className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" aria-hidden />
              <input
                id="dashboard-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className={`control-input py-2.5 pl-10 pr-3 text-sm placeholder:text-slate-500 ${error ? "border-accent-red/60" : ""}`}
                placeholder="••••••••"
                required
              />
            </motion.div>
          </div>

          {error && (
            <p role="alert" className="rounded-control border border-accent-red/30 bg-accent-red/10 px-3 py-2 text-sm text-red-200">
              {error}
            </p>
          )}

          <motion.button
            type="submit"
            disabled={loading || !password}
            whileTap={reduceMotion ? undefined : { scale: 0.98 }}
            className={`button-press w-full rounded-control border border-accent-primary bg-accent-primary px-4 py-2.5 text-sm font-semibold text-background hover:bg-accent-primary/90 disabled:opacity-50 ${
              loading ? "motion-button-pulse" : ""
            }`}
          >
            {loading ? "Signing in…" : "Login"}
          </motion.button>
        </form>}
      </motion.div>
    </div>
  );
}
