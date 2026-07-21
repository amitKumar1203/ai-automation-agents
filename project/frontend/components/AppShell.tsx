"use client";

import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { signOut, useSession } from "next-auth/react";
import Link from "next/link";
import { motion, useReducedMotion } from "framer-motion";
import {
  FileCheck2,
  Inbox,
  HardHat,
  ImageIcon,
  LayoutDashboard,
  LogOut,
  MailCheck,
  ScanSearch,
  ScrollText,
  Send,
  Settings,
  Store,
  Radio,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import ProfileAvatar from "@/components/ProfileAvatar";
import type { OperatorRole } from "@/lib/types";

type OperatorIdentity = {
  name: string | null;
  email: string | null;
  image: string | null;
  role: OperatorRole;
};

type NavDef = {
  href: string;
  label: string;
  icon: LucideIcon;
};

const OVERVIEW_NAV: NavDef = {
  href: "/",
  label: "Overview",
  icon: LayoutDashboard,
};

const AGENT_NAV: NavDef[] = [
  { href: "/intake-agent", label: "Intake Agent", icon: Inbox },
  { href: "/email-agent", label: "Email Agent", icon: MailCheck },
  { href: "/vendor-agent", label: "Vendor Agent", icon: Store },
  { href: "/followup-agent", label: "Follow-up Agent", icon: Send },
  { href: "/storefront-agent", label: "Storefront Search", icon: ImageIcon },
  { href: "/installer-agent", label: "Installer Matching", icon: HardHat },
  { href: "/po-agent", label: "PO Agent", icon: FileCheck2 },
  { href: "/artwork-agent", label: "Artwork Agent", icon: ScanSearch },
  { href: "/vision-agents", label: "Vision Agents", icon: Sparkles },
];

const AUDIT_NAV: NavDef = {
  href: "/audit-log",
  label: "Audit Log",
  icon: ScrollText,
};

const SUPERVISOR_NAV: NavDef = {
  href: "/supervisor",
  label: "Supervisor",
  icon: Radio,
};

const ADMIN_NAV_ITEM: NavDef = {
  href: "/admin",
  label: "Admin",
  icon: Settings,
};

function navForRole(role: OperatorRole | null | undefined): NavDef[] {
  if (role === "admin") {
    return [OVERVIEW_NAV, ...AGENT_NAV, AUDIT_NAV, SUPERVISOR_NAV, ADMIN_NAV_ITEM];
  }
  if (role === "reviewer") {
    return [
      { ...OVERVIEW_NAV, label: "Review Queue" },
      { ...AUDIT_NAV, label: "Approvals" },
      SUPERVISOR_NAV,
      ...AGENT_NAV,
    ];
  }
  return [OVERVIEW_NAV, ...AGENT_NAV, AUDIT_NAV, SUPERVISOR_NAV];
}

function pageTitleFromPathname(
  pathname: string,
  role: OperatorRole | null | undefined,
): string {
  if (pathname === "/") {
    if (role === "admin") return "Management Overview";
    if (role === "reviewer") return "Review Queue";
    return "Operator Workspace";
  }
  if (pathname === "/admin" || pathname.startsWith("/admin/")) {
    return "Admin Settings";
  }
  if (pathname === "/audit-log" || pathname.startsWith("/audit-log/")) {
    return role === "reviewer" ? "Approvals" : "Audit Log";
  }
  if (pathname === "/supervisor" || pathname.startsWith("/supervisor/")) {
    return "Supervisor";
  }
  const item = [...AGENT_NAV, OVERVIEW_NAV, AUDIT_NAV, SUPERVISOR_NAV, ADMIN_NAV_ITEM].find(
    (i) => pathname === i.href || pathname.startsWith(`${i.href}/`),
  );
  if (item) return item.label;
  return "Supervisor";
}

function NavItem({
  href,
  label,
  icon: Icon,
  active,
  compact = false,
}: {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  compact?: boolean;
}) {
  const reduceMotion = useReducedMotion();

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`relative flex shrink-0 items-center gap-2.5 rounded-control px-3 py-2 text-sm font-medium transition-colors ${
        active ? "text-white" : "text-slate-400 hover:bg-white/[0.04] hover:text-slate-100"
      } ${compact ? "whitespace-nowrap" : "w-full"}`}
    >
      {active && (
        <motion.span
          layoutId={compact ? "mobile-nav-active" : "desktop-nav-active"}
          transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 420, damping: 34 }}
          className="absolute inset-0 rounded-control border border-accent-primary/20 bg-accent-primary/10"
        />
      )}
      <Icon
        className={`relative h-4 w-4 ${active ? "text-accent-primary" : "text-slate-500"}`}
        strokeWidth={1.8}
        aria-hidden
      />
      <span className="relative">{label}</span>
      {active && !compact && (
        <span className="relative ml-auto h-1.5 w-1.5 rounded-full bg-accent-primary" aria-hidden />
      )}
    </Link>
  );
}

function roleLabel(role: OperatorRole): string {
  if (role === "admin") return "Admin";
  if (role === "reviewer") return "Reviewer";
  return "Operator";
}

/** Hide global nav on the login page. */
export default function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { data: session, status } = useSession();
  const [operator, setOperator] = useState<OperatorIdentity | null>(null);
  const [loggingOut, setLoggingOut] = useState(false);

  async function handleLogout() {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) {
        throw new Error("Logout failed");
      }
      await signOut({ redirect: false });
      window.location.replace("/login");
    } catch {
      setLoggingOut(false);
    }
  }

  useEffect(() => {
    if (pathname === "/login" || status === "loading") return;

    if (session?.user?.email) {
      setOperator({
        name: session.user.name ?? null,
        email: session.user.email,
        image: session.user.image ?? null,
        role: session.user.role ?? "operator",
      });
      return;
    }

    let cancelled = false;
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as OperatorIdentity;
      })
      .then((data) => {
        if (!cancelled) setOperator(data);
      })
      .catch(() => {
        if (!cancelled) setOperator(null);
      });

    return () => {
      cancelled = true;
    };
  }, [pathname, session, status]);

  if (pathname === "/login") {
    return <>{children}</>;
  }

  const title = pageTitleFromPathname(pathname, operator?.role);
  const displayName =
    operator?.name || operator?.email || "Signed-in operator";
  const displayEmail = operator?.email || roleLabel(operator?.role ?? "operator");
  const navItems = navForRole(operator?.role);
  const shellSubtitle =
    operator?.role === "admin"
      ? "Management, routing, and policy."
      : operator?.role === "reviewer"
        ? "Approvals and agent review."
        : "Agent runs and operational checks.";

  return (
    <div className="h-dvh overflow-hidden bg-transparent">
      <div className="flex h-dvh">
        <aside className="sticky top-0 hidden h-dvh w-64 shrink-0 border-r border-white/12 bg-surface-raised/68 shadow-[8px_0_28px_rgba(0,0,0,0.16)] backdrop-blur-2xl md:block md:w-64 lg:w-72">
          <div className="flex h-full flex-col">
            <div className="px-5 pb-5 pt-6">
              <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-[#d6b87a]">
                Softude Ops Console
              </p>
              <h2 className="mt-2 font-display text-lg font-bold tracking-[-0.02em] text-slate-50">
                {operator?.role === "admin"
                  ? "Management"
                  : operator?.role === "reviewer"
                    ? "Review"
                    : "Operations"}
              </h2>
              <p className="mt-1 text-xs leading-relaxed text-slate-400">
                {shellSubtitle}
              </p>
            </div>

            <nav className="flex-1 px-3 pb-3" aria-label="Primary navigation">
              <ul className="space-y-0.5">
                {navItems.map((item) => {
                  const active =
                    item.href === "/"
                      ? pathname === "/"
                      : pathname === item.href || pathname.startsWith(`${item.href}/`);

                  return (
                    <li key={item.href}>
                      <NavItem {...item} active={active} />
                    </li>
                  );
                })}
              </ul>
            </nav>

            <div className="border-t border-white/10 bg-white/[0.03] px-5 py-4">
              <div className="flex items-center gap-3">
                <ProfileAvatar
                  name={operator?.name ?? undefined}
                  email={operator?.email ?? undefined}
                  pictureUrl={operator?.image}
                  size="md"
                />
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-slate-200">
                    {displayName}
                  </p>
                  <p className="truncate text-[11px] text-slate-500">
                    {displayEmail}
                  </p>
                  {operator?.role && (
                    <p className="mt-1 text-[10px] font-semibold uppercase tracking-wide text-accent-primary/80">
                      {roleLabel(operator.role)}
                    </p>
                  )}
                </div>
              </div>
            </div>
          </div>
        </aside>

        <div className="flex h-dvh min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 border-b border-white/12 bg-surface/62 shadow-[0_6px_24px_rgba(0,0,0,0.12)] backdrop-blur-2xl">
            <div className="flex w-full items-center justify-between gap-4 px-4 py-3.5 sm:px-5">
              <div className="min-w-0 flex-1 text-left">
                <p className="truncate text-left text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-400">
                  {title}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="status-success inline-flex items-center gap-1.5 rounded-full border border-accent-green/25 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-accent-green">
                  <span className="h-1.5 w-1.5 rounded-full bg-accent-green" aria-hidden />
                  Online
                </span>
                <div className="flex items-center gap-2">
                  <ProfileAvatar
                    name={operator?.name ?? undefined}
                    email={operator?.email ?? undefined}
                    pictureUrl={operator?.image}
                    size="sm"
                  />
                  <div className="hidden min-w-0 sm:block">
                    <p className="max-w-[10rem] truncate text-xs font-medium text-slate-200">
                      {displayName}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  disabled={loggingOut}
                  aria-label="Log out"
                  title="Log out"
                  className="button-press inline-flex h-8 w-8 items-center justify-center rounded-control border border-white/10 bg-white/[0.04] text-slate-400 hover:border-accent-primary/30 hover:text-accent-primary disabled:cursor-wait disabled:opacity-50"
                >
                  <LogOut className="h-4 w-4" strokeWidth={1.8} aria-hidden />
                </button>
              </div>
            </div>
            <nav className="overflow-x-auto border-t border-white/10 bg-white/[0.025] px-2 py-1.5 md:hidden" aria-label="Primary navigation">
              <div className="flex min-w-max gap-1">
                {navItems.map((item) => {
                  const active =
                    item.href === "/"
                      ? pathname === "/"
                      : pathname === item.href || pathname.startsWith(`${item.href}/`);
                  return <NavItem key={item.href} {...item} active={active} compact />;
                })}
              </div>
            </nav>
          </header>

          <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>

          <footer className="border-t border-white/10 bg-surface/42 backdrop-blur-xl">
            <div className="flex w-full items-center justify-between px-4 py-3 text-xs text-slate-500 sm:px-5">
              <span>© {new Date().getFullYear()} Softude Ops Console</span>
              <span className="font-mono">v1</span>
            </div>
          </footer>
        </div>
      </div>
    </div>
  );
}
