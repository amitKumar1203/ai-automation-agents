import { NextResponse } from "next/server";

import { DASHBOARD_AUTH_COOKIE } from "@/lib/auth";

/** Clear the dashboard session cookie and complete logout. */
export async function POST() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: DASHBOARD_AUTH_COOKIE,
    value: "",
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 0,
    expires: new Date(0),
  });
  return response;
}
