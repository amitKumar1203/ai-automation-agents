import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/auth";
import {
  DASHBOARD_AUTH_COOKIE,
  expectedAuthToken,
} from "@/lib/auth";

async function hasLocalFallback(request: NextRequest): Promise<boolean> {
  if (process.env.DASHBOARD_LOCAL_PASSWORD_FALLBACK !== "true") {
    return false;
  }
  const password = (process.env.DASHBOARD_PASSWORD || "").trim();
  if (!password) return false;
  const expected = await expectedAuthToken(password);
  return request.cookies.get(DASHBOARD_AUTH_COOKIE)?.value === expected;
}

export default auth(async function middleware(request) {
  const { pathname } = request.nextUrl;
  const isLoginPage = pathname === "/login";
  const isAuthEndpoint = pathname.startsWith("/api/auth/");
  const isPublicAsset =
    pathname.startsWith("/_next/") ||
    pathname === "/favicon.ico" ||
    pathname.startsWith("/favicon") ||
    pathname === "/ai-neural-network-background.svg";

  if (isAuthEndpoint || isPublicAsset) {
    return NextResponse.next();
  }

  const authenticated =
    Boolean(request.auth?.user?.email) || (await hasLocalFallback(request));

  if (isLoginPage) {
    return authenticated
      ? NextResponse.redirect(new URL("/", request.url))
      : NextResponse.next();
  }

  if (
    (pathname === "/admin" || pathname.startsWith("/admin/")) &&
    request.auth?.user?.role !== "admin"
  ) {
    if (pathname.startsWith("/api/")) {
      return NextResponse.json({ detail: "Admin access required" }, { status: 403 });
    }
    return NextResponse.redirect(new URL("/", request.url));
  }

  if (!authenticated) {
    // API/BFF callers expect JSON — never redirect them to an HTML login page
    // (browser fetch would follow the redirect and fail with "Unexpected token '<'").
    if (pathname.startsWith("/api/")) {
      return NextResponse.json(
        { detail: "Unauthorized — please log in again, then retry." },
        { status: 401 },
      );
    }

    const login = new URL("/login", request.url);
    const next = pathname + request.nextUrl.search;
    if (next && next !== "/") {
      login.searchParams.set("next", next);
    }
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
});

export const config = {
  matcher: ["/((?!_next/static|_next/image).*)"],
};
