"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/email-agent", label: "Email" },
  { href: "/vendor-agent", label: "Vendor" },
  { href: "/po-agent", label: "PO" },
  { href: "/artwork-agent", label: "Artwork" },
  { href: "/audit-log", label: "Audit" },
] as const;

/** Top navigation with active route highlighting. */
export default function AppNav() {
  const pathname = usePathname();

  return (
    <nav className="sticky top-0 z-40 border-b border-surface-border bg-surface/85 backdrop-blur-md">
      <div className="mx-auto flex max-w-6xl items-center gap-4 overflow-x-auto px-5 py-3.5">
        <Link
          href="/"
          className="shrink-0 font-display text-sm font-semibold tracking-[0.14em] text-slate-100"
        >
          Softude Ops Console
        </Link>
        <div className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active =
              item.href === "/"
                ? pathname === "/"
                : pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`shrink-0 rounded-lg border px-3 py-1.5 text-sm font-medium transition ${
                  active
                    ? "border-accent-primary/30 bg-accent-primary/15 text-accent-primary"
                    : "border-transparent text-slate-400 hover:border-white/10 hover:bg-white/[0.03] hover:text-slate-100"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
