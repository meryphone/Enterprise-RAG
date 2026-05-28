/**
 * Server-side helpers for Next.js API routes that proxy to the backend.
 *
 * We do NOT verify the JWT signature here — that's the backend's job.
 * We only decode the payload to gate routes by role at the proxy layer
 * (defense in depth). If a token is forged, the backend will reject it.
 */
import { cookies } from "next/headers";

type JwtPayload = { sub?: string; role?: string; exp?: number };

function decodePayload(token: string): JwtPayload | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    const json = Buffer.from(parts[1], "base64url").toString("utf8");
    return JSON.parse(json) as JwtPayload;
  } catch {
    return null;
  }
}

export async function getAuthToken(): Promise<string | null> {
  const store = await cookies();
  return store.get("auth_token")?.value ?? null;
}

/**
 * Returns the token if the cookie payload claims `role === "admin"`, else null.
 * The backend re-verifies — this only avoids forwarding obviously-non-admin tokens.
 */
export async function getAdminToken(): Promise<string | null> {
  const token = await getAuthToken();
  if (!token) return null;
  const payload = decodePayload(token);
  if (!payload || payload.role !== "admin") return null;
  return token;
}
