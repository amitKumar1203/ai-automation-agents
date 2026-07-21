"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";

/** Initials from a display name or email (Gmail-style fallback avatar). */
export function initialsFromLabel(label: string): string {
  const cleaned = (label || "").trim();
  if (!cleaned) return "?";
  const local = cleaned.includes("@") ? cleaned.split("@")[0] : cleaned;
  const parts = local.replace(/[._-]+/g, " ").split(/\s+/).filter(Boolean);
  if (parts.length >= 2) {
    return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  }
  return local.slice(0, 2).toUpperCase();
}

interface ProfileAvatarProps {
  name?: string;
  email?: string;
  pictureUrl?: string | null;
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZE_CLASS = {
  sm: "h-8 w-8 text-[10px]",
  md: "h-9 w-9 text-xs",
  lg: "h-11 w-11 text-sm",
} as const;

/** Circular avatar: Google profile photo when available, else initials. */
export default function ProfileAvatar({
  name = "",
  email = "",
  pictureUrl = null,
  size = "md",
  className = "",
}: ProfileAvatarProps): ReactNode {
  const [imgFailed, setImgFailed] = useState(false);
  const label = name || email || "?";
  const initials = useMemo(() => initialsFromLabel(label), [label]);
  const showImage = Boolean(pictureUrl) && !imgFailed;

  return (
    <span
      className={`relative inline-flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-white/10 bg-accent-primary/20 font-semibold text-accent-primary ${SIZE_CLASS[size]} ${className}`}
      title={label}
      aria-label={label}
    >
      {showImage ? (
        // eslint-disable-next-line @next/next/no-img-element -- Google CDN photo URL
        <img
          src={pictureUrl!}
          alt=""
          className="h-full w-full object-cover"
          referrerPolicy="no-referrer"
          onError={() => setImgFailed(true)}
        />
      ) : (
        <span aria-hidden="true">{initials}</span>
      )}
    </span>
  );
}
