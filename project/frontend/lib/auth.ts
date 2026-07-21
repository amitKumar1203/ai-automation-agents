/** Cookie name for the dashboard password gate. */
export const DASHBOARD_AUTH_COOKIE = "dashboard_auth";

/** Build the expected cookie value from DASHBOARD_PASSWORD (Edge + Node). */
export async function expectedAuthToken(password: string): Promise<string> {
  const data = new TextEncoder().encode(`dashboard-auth:v1:${password}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}
