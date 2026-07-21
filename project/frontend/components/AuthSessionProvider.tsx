"use client";

import type { ReactNode } from "react";
import { SessionProvider } from "next-auth/react";

/** Client wrapper so dashboard components can read the signed-in operator. */
export default function AuthSessionProvider({
  children,
}: {
  children: ReactNode;
}) {
  return <SessionProvider>{children}</SessionProvider>;
}
