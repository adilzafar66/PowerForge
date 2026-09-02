export type ServiceStatus = "ok" | "unavailable";
export type ReadyStatus = "ok" | "degraded" | "unavailable";

export type HealthResponse = {
  status: "ok";
  service: string;
  version: string;
};

export type ReadyResponse = {
  status: ReadyStatus;
  service: string;
  version: string;
  database: ServiceStatus;
  redis: ServiceStatus;
};

export function apiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "");
}

/** Server-side URL. In Docker the browser uses localhost; the web container uses the API service name. */
export function apiBaseUrlServer(): string {
  return (process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
    /\/$/,
    "",
  );
}

export async function fetchStackStatus(baseUrl: string): Promise<{
  health: HealthResponse | null;
  ready: ReadyResponse | null;
}> {
  try {
    const [healthRes, readyRes] = await Promise.all([
      fetch(`${baseUrl}/health`, { cache: "no-store", signal: AbortSignal.timeout(5000) }),
      fetch(`${baseUrl}/ready`, { cache: "no-store", signal: AbortSignal.timeout(8000) }),
    ]);
    if (!healthRes.ok) {
      return { health: null, ready: null };
    }
    const health = (await healthRes.json()) as HealthResponse;
    const ready =
      readyRes.ok || readyRes.status === 503 ? ((await readyRes.json()) as ReadyResponse) : null;
    return { health, ready };
  } catch {
    return { health: null, ready: null };
  }
}

export function isApiHealthy(health: HealthResponse | null): boolean {
  return health?.status === "ok";
}

export function overallLabel(ready: ReadyResponse | null, health: HealthResponse | null): string {
  if (!health) {
    return "API unreachable";
  }
  if (!ready) {
    return "API up, readiness unknown";
  }
  if (ready.status === "ok") {
    return "Stack ready";
  }
  if (ready.status === "degraded") {
    return "API up, Redis unavailable";
  }
  return "Database unavailable";
}
