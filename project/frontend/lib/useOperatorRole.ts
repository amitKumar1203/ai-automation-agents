"use client";

import { useEffect, useState } from "react";
import { useSession } from "next-auth/react";

import type { OperatorRole } from "@/lib/types";

/** Resolve signed-in operator role from NextAuth session or local fallback. */
export function useOperatorRole(): {
  role: OperatorRole | null;
  email: string | null;
  name: string | null;
  loading: boolean;
} {
  const { data: session, status } = useSession();
  const [role, setRole] = useState<OperatorRole | null>(
    session?.user?.role ?? null,
  );
  const [email, setEmail] = useState<string | null>(
    session?.user?.email ?? null,
  );
  const [name, setName] = useState<string | null>(session?.user?.name ?? null);
  const [loading, setLoading] = useState(status === "loading");

  useEffect(() => {
    if (status === "loading") {
      setLoading(true);
      return;
    }

    if (session?.user?.email) {
      setRole(session.user.role ?? "operator");
      setEmail(session.user.email);
      setName(session.user.name ?? null);
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as {
          role?: OperatorRole;
          email?: string | null;
          name?: string | null;
        };
      })
      .then((data) => {
        if (cancelled) return;
        setRole(data?.role ?? "operator");
        setEmail(data?.email ?? null);
        setName(data?.name ?? null);
      })
      .catch(() => {
        if (!cancelled) {
          setRole("operator");
          setEmail(null);
          setName(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [session, status]);

  return { role, email, name, loading };
}

export function canReview(role: OperatorRole | null): boolean {
  return role === "reviewer" || role === "admin";
}

export function isAdmin(role: OperatorRole | null): boolean {
  return role === "admin";
}
