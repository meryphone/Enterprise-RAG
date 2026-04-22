import type { Scope, SourceRef } from "./types";
import { logout } from "./auth";

// In dev/Cloudflare: /api (same-origin, proxied by Next.js rewrites → localhost:8000).
// In Azure production: set NEXT_PUBLIC_API_URL to the direct backend URL.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

async function apiFetch(input: string, init?: RequestInit): Promise<Response> {
  const res = await fetch(`${API_URL}${input}`, {
    ...init,
    credentials: "same-origin", // browser sends the httpOnly auth_token cookie automatically
  });
  if (res.status === 401) {
    await logout();
    throw new Error("Session expired");
  }
  return res;
}

export async function fetchScopes(): Promise<Scope[]> {
  const res = await apiFetch("/projects");
  if (!res.ok) throw new Error("Error cargando scopes");
  return res.json();
}

export async function streamQuery(
  query: string,
  scope: Scope,
  onToken: (token: string) => void,
  onSources: (sources: SourceRef[]) => void,
  onDone: () => void,
  onError: (msg: string) => void,
): Promise<void> {
  let res: Response;
  try {
    res = await apiFetch("/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        proyecto_id: scope.proyecto_id,
        empresa: scope.empresa,
      }),
    });
  } catch {
    onError("Error de autenticación o conexión.");
    return;
  }

  if (!res.ok || !res.body) {
    onError(`Error del servidor: ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      try {
        const evt = JSON.parse(line.slice(6));
        if (evt.type === "token") onToken(evt.content);
        else if (evt.type === "sources") onSources(evt.sources);
        else if (evt.type === "done") onDone();
        else if (evt.type === "error") onError(evt.message);
      } catch {
        // línea malformada, ignorar
      }
    }
  }
}
