"use client";

import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import {
  apiBaseUrl,
  fetchStackStatus,
  overallLabel,
  type HealthResponse,
  type ReadyResponse,
  type ServiceStatus,
} from "@/lib/health";
import { SERVICE_HEALTH_STYLES, type ServiceHealthTone } from "@/lib/status-styles";

type LoadState = "loading" | "loaded" | "error";

type ServiceRow = {
  name: string;
  description: string;
  tone: ServiceHealthTone;
  detail: string;
};

function toTone(value: ServiceStatus | "ok" | "checking" | "unavailable"): ServiceHealthTone {
  if (value === "ok") {
    return "operational";
  }
  if (value === "checking") {
    return "degraded";
  }
  return "down";
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
  const [checkedAt] = useState(() =>
    new Intl.DateTimeFormat("en-US", {
      dateStyle: "medium",
      timeStyle: "short",
      timeZone: "UTC",
    }).format(new Date()),
  );

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

  const services = useMemo<ServiceRow[]>(() => {
    const apiTone = toTone(health ? "ok" : state === "loading" ? "checking" : "unavailable");
    const databaseTone = toTone(
      ready?.database ?? (state === "loading" ? "checking" : "unavailable"),
    );
    const redisTone = toTone(ready?.redis ?? (state === "loading" ? "checking" : "unavailable"));

    return [
      {
        name: "API",
        description: "FastAPI process",
        tone: apiTone,
        detail: health ? `${health.service} ${health.version}` : "Liveness endpoint /health",
      },
      {
        name: "PostgreSQL",
        description: "Engineering model store",
        tone: databaseTone,
        detail: "Readiness requires a live database",
      },
      {
        name: "Redis",
        description: "Background job broker",
        tone: redisTone,
        detail: "Optional in Phase 0; workers need it",
      },
    ];
  }, [health, ready, state]);

  const counts = useMemo(() => {
    return {
      operational: services.filter((service) => service.tone === "operational").length,
      degraded: services.filter((service) => service.tone === "degraded").length,
      down: services.filter((service) => service.tone === "down").length,
    };
  }, [services]);

  const anyDown = counts.down > 0;
  const allOk = counts.degraded === 0 && counts.down === 0 && state !== "error";

  const banner =
    state === "error" || anyDown
      ? {
          color: "bg-red-50 border-red-200 text-red-700",
          dot: "bg-red-500",
          text:
            state === "error"
              ? "API unreachable — stack health could not be verified."
              : `${counts.down} service${counts.down > 1 ? "s are" : " is"} unavailable${
                  counts.degraded > 0 ? `, and ${counts.degraded} degraded` : ""
                }.`,
        }
      : !allOk
        ? {
            color: "bg-amber-50 border-amber-200 text-amber-700",
            dot: "bg-amber-400",
            text: `${counts.degraded} service${counts.degraded > 1 ? "s are" : " is"} degraded. All other systems operational.`,
          }
        : {
            color: "bg-emerald-50 border-emerald-200 text-emerald-700",
            dot: "bg-emerald-500",
            text: "All systems are fully operational.",
          };

  const summary = state === "error" ? "API unreachable" : overallLabel(ready, health);

  return (
    <div className="mx-auto max-w-3xl px-8 py-8">
      <PageHeader
        title="System Status"
        description={`Last checked ${checkedAt} · ${summary}`}
        actions={
          <Button type="button" variant="outline" size="sm" onClick={() => void refresh()}>
            {state === "loading" ? "Checking…" : "Refresh"}
          </Button>
        }
      />

      {error ? <p className="mb-4 text-[13px] text-red-600">{error}</p> : null}

      <div
        className={`mb-6 flex items-center gap-3 rounded-xl border px-4 py-3.5 text-[13.5px] font-medium ${banner.color}`}
      >
        <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${banner.dot}`} />
        {banner.text}
      </div>

      <div className="mb-6 grid grid-cols-3 gap-3">
        {(
          [
            { label: "Operational", count: counts.operational, tone: "operational" as const },
            { label: "Degraded", count: counts.degraded, tone: "degraded" as const },
            { label: "Down", count: counts.down, tone: "down" as const },
          ] as const
        ).map(({ label, count, tone }) => {
          const style = SERVICE_HEALTH_STYLES[tone];
          return (
            <Card key={label} className={`border-0 px-4 py-3 ${style.bg}`}>
              <p className={`text-[22px] font-bold ${style.text}`}>{count}</p>
              <p
                className={`text-[12px] font-semibold tracking-wider uppercase opacity-70 ${style.text}`}
              >
                {label}
              </p>
            </Card>
          );
        })}
      </div>

      <Card className="overflow-hidden">
        <div className="border-b border-slate-100 px-5 py-3">
          <p className="text-[11px] font-bold tracking-widest text-slate-400 uppercase">Services</p>
        </div>
        <ul className="divide-y divide-slate-100">
          {services.map((service) => {
            const style = SERVICE_HEALTH_STYLES[service.tone];
            return (
              <li key={service.name} className="flex items-start justify-between gap-4 px-5 py-4">
                <div>
                  <p className="text-[14px] font-semibold text-slate-800">{service.name}</p>
                  <p className="mt-0.5 text-[12.5px] text-slate-400">{service.description}</p>
                  <p className="mt-1 text-[12.5px] text-slate-500">{service.detail}</p>
                </div>
                <span
                  className={`inline-flex shrink-0 items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-semibold ${style.bg} ${style.text}`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                  {style.label}
                </span>
              </li>
            );
          })}
        </ul>
      </Card>
    </div>
  );
}
