import { createHmac, timingSafeEqual } from "crypto";
import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/auth";
import { DASHBOARD_AUTH_COOKIE, expectedAuthToken } from "@/lib/auth";

const API_BASE =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000";

async function proxy(
  request: NextRequest,
  pathSegments: string[],
): Promise<NextResponse> {
  const session = await auth();
  const email = session?.user?.email?.trim().toLowerCase();
  const role = session?.user?.role;
  const localFallback = await isLocalFallback(request);
  if ((!email || !role) && !localFallback) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
  }

  const path = pathSegments.join("/");
  const url = new URL(request.url);
  const target = `${API_BASE.replace(/\/$/, "")}/api/${path}${url.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) {
    headers.set("content-type", contentType);
  }
  for (const name of ["Idempotency-Key", "X-Correlation-ID"]) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  // Prefer BACKEND_API_KEY; fall back to API_KEY for existing Vercel config.
  const apiKey = (
    process.env.BACKEND_API_KEY ||
    process.env.API_KEY ||
    ""
  ).trim();
  if (apiKey) {
    headers.set("X-API-Key", apiKey);
  }
  const identitySecret = (process.env.TRUSTED_IDENTITY_SECRET || "").trim();
  if (email && role) {
    if (!identitySecret) {
      return NextResponse.json(
        { detail: "Trusted identity signing is not configured." },
        { status: 503 },
      );
    }
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const signature = createHmac("sha256", identitySecret)
      .update(`${timestamp}\n${email}\n${role}`, "utf8")
      .digest("hex");
    headers.set("X-Principal-Email", email);
    headers.set("X-Principal-Role", role);
    headers.set("X-Principal-Timestamp", timestamp);
    headers.set("X-Principal-Signature", signature);
  }

  const init: RequestInit = {
    method: request.method,
    headers,
    cache: "no-store",
  };

  if (request.method !== "GET" && request.method !== "HEAD") {
    // Multipart uploads must stay binary; text() corrupts image bodies.
    const isMultipart = (contentType ?? "").includes("multipart/form-data");
    init.body = isMultipart
      ? await request.arrayBuffer()
      : await request.text();
  }

  const upstream = await fetch(target, init);
  const body = await upstream.text();
  return new NextResponse(body, {
    status: upstream.status,
    headers: {
      "content-type":
        upstream.headers.get("content-type") ?? "application/json",
    },
  });
}

async function isLocalFallback(request: NextRequest): Promise<boolean> {
  if (
    process.env.NODE_ENV === "production" ||
    process.env.DASHBOARD_LOCAL_PASSWORD_FALLBACK !== "true" ||
    process.env.TRUSTED_IDENTITY_SECRET
  ) {
    return false;
  }
  const password = (process.env.DASHBOARD_PASSWORD || "").trim();
  const cookie = request.cookies.get(DASHBOARD_AUTH_COOKIE)?.value || "";
  if (!password || !cookie) return false;
  const expected = await expectedAuthToken(password);
  const left = Buffer.from(cookie);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

type RouteContext = { params: { path: string[] } };

/** Server-side BFF proxy — attaches BACKEND_API_KEY / API_KEY (never to browser). */
export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context.params.path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context.params.path);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return proxy(request, context.params.path);
}

export async function PUT(request: NextRequest, context: RouteContext) {
  return proxy(request, context.params.path);
}
