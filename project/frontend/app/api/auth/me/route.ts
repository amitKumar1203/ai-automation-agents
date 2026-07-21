import { timingSafeEqual } from "crypto";
import { NextRequest, NextResponse } from "next/server";

import { auth } from "@/auth";
import { DASHBOARD_AUTH_COOKIE, expectedAuthToken } from "@/lib/auth";

async function hasLocalFallback(request: NextRequest): Promise<boolean> {
  if (process.env.DASHBOARD_LOCAL_PASSWORD_FALLBACK !== "true") {
    return false;
  }
  const password = (process.env.DASHBOARD_PASSWORD || "").trim();
  if (!password) return false;
  const expected = await expectedAuthToken(password);
  const cookie = request.cookies.get(DASHBOARD_AUTH_COOKIE)?.value || "";
  const left = Buffer.from(cookie);
  const right = Buffer.from(expected);
  return left.length === right.length && timingSafeEqual(left, right);
}

/** Return the active dashboard operator (Google session or local password fallback). */
export async function GET(request: NextRequest) {
  const session = await auth();
  if (session?.user?.email) {
    return NextResponse.json({
      name: session.user.name ?? null,
      email: session.user.email,
      image: session.user.image ?? null,
      role: session.user.role ?? "operator",
      source: "google",
    });
  }

  if (await hasLocalFallback(request)) {
    return NextResponse.json({
      name: "Local operator",
      email: null,
      image: null,
      role: "admin",
      source: "password",
    });
  }

  return NextResponse.json({ detail: "Unauthorized" }, { status: 401 });
}
