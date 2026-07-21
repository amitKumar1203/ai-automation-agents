import { timingSafeEqual } from "crypto";
import { NextRequest, NextResponse } from "next/server";

import {
  DASHBOARD_AUTH_COOKIE,
  expectedAuthToken,
} from "@/lib/auth";

function safeEqual(a: string, b: string): boolean {
  const left = Buffer.from(a, "utf8");
  const right = Buffer.from(b, "utf8");
  if (left.length !== right.length) {
    return false;
  }
  return timingSafeEqual(left, right);
}

/** POST { password } — sets httpOnly dashboard_auth cookie on success. */
export async function POST(request: NextRequest) {
  if (process.env.DASHBOARD_LOCAL_PASSWORD_FALLBACK !== "true") {
    return NextResponse.json(
      { error: "Local password fallback is disabled." },
      { status: 404 },
    );
  }
  const expectedPassword = (process.env.DASHBOARD_PASSWORD || "").trim();
  if (!expectedPassword) {
    return NextResponse.json(
      { error: "DASHBOARD_PASSWORD is not configured on the server." },
      { status: 503 },
    );
  }

  let body: { password?: string };
  try {
    body = (await request.json()) as { password?: string };
  } catch {
    return NextResponse.json({ error: "Invalid JSON body" }, { status: 400 });
  }

  const password = typeof body.password === "string" ? body.password : "";
  if (!safeEqual(password, expectedPassword)) {
    return NextResponse.json(
      { error: "Incorrect password" },
      { status: 401 },
    );
  }

  const token = await expectedAuthToken(expectedPassword);
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: DASHBOARD_AUTH_COOKIE,
    value: token,
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 24 * 30,
  });
  return response;
}
