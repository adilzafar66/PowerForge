"use client";

import { useCallback, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  apiBaseUrl,
  fetchStackStatus,
  overallLabel,
  type HealthResponse,
  type ReadyResponse,
  type ServiceStatus,
} from "@/lib/health";

type LoadState = "loading" | "loaded" | "error";

function statusTone(status: ServiceStatus | "ok" | "degraded" | "unavailable" | "error" | "loading"): string {
  if (status === "ok") {
    return "bg-emerald-50 text-emerald-800 ring-emerald-200";
  }
  if (status === "degraded" || status === "loading") {
    return "bg-amber-50 text-amber-900 ring-amber-200";
  }
  return "bg-red-50 text-red-800 ring-red-200";
}

export function StatusDashboard({
  initialHealth,
  initialReady,
}: {
  initialHealth: HealthResponse | null;
  initialReady: ReadyResponse | null;
}) {
  const [health, setHealth] = useState<HealthResponse | null>(initialHealth);
  const [ready, setReady] = useState<ReadyResponse | null>(initialReady);
  const [state, setState] = useState<LoadState>(initialHealth ? "loaded" : "error");
  const [error, setError] = useState<string | null>(initialHealth ? null : "Unable to reach the API");

  const refresh = useCallback(async () => {
    setState("loading");
    setError(null);
    const { health: nextHealth, ready: nextReady } = await fetchStackStatus(apiBaseUrl());
    setHealth(nextHealth);
    setReady(nextReady);
    if (!nextHealth) {
      setState("error");
      setError(`Could not reach ${apiBaseUrl()}`);
      return;
    }
    setState("loaded");
  }, []);

  const summary = state === "error" ? "API unreachable" : overallLabel(ready, health);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className={`inline-flex items-center rounded-full px-3 py-1 text-sm ring-1 ring-inset ${statusTone(state === "error" ? "error" : (ready?.status ?? "loading"))}`}>
          {state === "loading" ? "Checking stack…" : summary}
        </p>
        <Button type="button" variant="outline" size="sm" onClick={() => void refresh()}>
          Refresh
        </Button>
      </div>

      {error ? <p className="text-sm text-red-700">{error}</p> : null}

      <div className="grid gap-4 md:grid-cols-3">
        <ServiceCard
          title="API"
          description="FastAPI process"
          value={health ? "ok" : state === "loading" ? "checking" : "unavailable"}
          detail={health ? `${health.service} ${health.version}` : "Liveness endpoint /health"}
        />
        <ServiceCard
          title="PostgreSQL"
          description="Engineering model store"
          value={ready?.database ?? (state === "loading" ? "checking" : "unavailable")}
          detail="Readiness requires a live database"
        />
        <ServiceCard
          title="Redis"
          description="Background job broker"
          value={ready?.redis ?? (state === "loading" ? "checking" : "unavailable")}
          detail="Optional in Phase 0; workers need it"
        />
      </div>
    </div>
  );
}

function ServiceCard({
  title,
  description,
  value,
  detail,
}: {
  title: string;
  description: string;
  value: string;
  detail: string;
}) {
  const tone = value === "ok" ? "ok" : value === "checking" ? "loading" : "unavailable";
  return (
    <Card>
      <CardHeader>
        <CardDescription>{description}</CardDescription>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        <p className={`inline-flex rounded-md px-2 py-1 text-xs font-medium uppercase tracking-wide ring-1 ring-inset ${statusTone(tone)}`}>
          {value}
        </p>
        <p className="text-sm text-slate-500">{detail}</p>
      </CardContent>
    </Card>
  );
}
