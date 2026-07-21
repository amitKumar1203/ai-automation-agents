import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

type OperatorRole = "operator" | "reviewer" | "admin";

const googleConfigured = Boolean(
  process.env.AUTH_GOOGLE_ID && process.env.AUTH_GOOGLE_SECRET,
);

function allowedDomain(email: string): boolean {
  const configured = (process.env.AUTH_ALLOWED_DOMAINS || "")
    .split(",")
    .map((domain) => domain.trim().toLowerCase())
    .filter(Boolean);
  if (configured.length === 0) {
    return process.env.NODE_ENV !== "production";
  }
  const domain = email.toLowerCase().split("@").at(1);
  return Boolean(domain && configured.includes(domain));
}

async function provisionOperator(
  email: string,
  name: string | null | undefined,
): Promise<OperatorRole | null> {
  const apiBase = (
    process.env.API_BASE_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://localhost:8000"
  ).replace(/\/$/, "");
  const apiKey = (process.env.BACKEND_API_KEY || process.env.API_KEY || "").trim();
  const response = await fetch(`${apiBase}/api/auth/operator`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      ...(apiKey ? { "X-API-Key": apiKey } : {}),
    },
    body: JSON.stringify({ email, name }),
    cache: "no-store",
  });
  if (!response.ok) return null;
  const account = (await response.json()) as { role?: string };
  return account.role === "operator" ||
    account.role === "reviewer" ||
    account.role === "admin"
    ? account.role
    : null;
}

export const { handlers, auth } = NextAuth({
  providers: googleConfigured
    ? [
        Google({
          clientId: process.env.AUTH_GOOGLE_ID,
          clientSecret: process.env.AUTH_GOOGLE_SECRET,
          authorization: {
            params: { hd: process.env.AUTH_GOOGLE_WORKSPACE_DOMAIN },
          },
        }),
      ]
    : [],
  pages: { signIn: "/login" },
  session: { strategy: "jwt" },
  callbacks: {
    async signIn({ user, profile }) {
      const email = (user.email || profile?.email || "").toLowerCase();
      if (!email || !allowedDomain(email)) return false;
      const role = await provisionOperator(email, user.name);
      if (!role) return false;
      user.role = role;
      return true;
    },
    jwt({ token, user }) {
      if (user?.role) token.role = user.role;
      return token;
    },
    session({ session, token }) {
      if (session.user) session.user.role = token.role as OperatorRole;
      return session;
    },
  },
});
