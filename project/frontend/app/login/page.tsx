import { Suspense, type ReactNode } from "react";

import LoginClient from "./LoginClient";

/** Login route — wraps client form in Suspense for useSearchParams. */
export default function LoginRoute(): ReactNode {
  const localFallback =
    process.env.DASHBOARD_LOCAL_PASSWORD_FALLBACK === "true";
  const googleConfigured = Boolean(
    process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET,
  );
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-background px-5">
          <div className="premium-card w-full max-w-md p-8">
            <div className="skeleton h-10 w-10 rounded-control" />
            <div className="skeleton mt-6 h-4 w-32 rounded-full" />
            <div className="skeleton mt-4 h-8 w-24 rounded-md" />
            <div className="skeleton mt-8 h-11 w-full rounded-control" />
          </div>
        </div>
      }
    >
      <LoginClient
        localFallback={localFallback}
        googleConfigured={googleConfigured}
      />
    </Suspense>
  );
}
