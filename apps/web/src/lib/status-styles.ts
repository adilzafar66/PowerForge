import type { ProjectStatus, RevisionStatus } from "@/lib/projects";

export type StatusStyle = {
  dot: string;
  bg: string;
  text: string;
  label: string;
};

export const PROJECT_STATUS_STYLES: Record<ProjectStatus, StatusStyle> = {
  ACTIVE: { dot: "bg-emerald-500", bg: "bg-emerald-50", text: "text-emerald-700", label: "Active" },
  PAUSED: { dot: "bg-amber-400", bg: "bg-amber-50", text: "text-amber-700", label: "Paused" },
  CANCELLED: { dot: "bg-red-400", bg: "bg-red-50", text: "text-red-600", label: "Cancelled" },
  ARCHIVED: { dot: "bg-slate-400", bg: "bg-slate-100", text: "text-slate-500", label: "Archived" },
};

export const REVISION_STATUS_STYLES: Record<RevisionStatus, StatusStyle> = {
  ACTIVE: { dot: "bg-blue-500", bg: "bg-blue-50", text: "text-blue-700", label: "Active" },
  DRAFT: { dot: "bg-violet-400", bg: "bg-violet-50", text: "text-violet-700", label: "Draft" },
  SUPERSEDED: { dot: "bg-slate-300", bg: "bg-slate-100", text: "text-slate-500", label: "Superseded" },
};

export type ServiceHealthTone = "operational" | "degraded" | "down";

export const SERVICE_HEALTH_STYLES: Record<
  ServiceHealthTone,
  StatusStyle & { ring: string }
> = {
  operational: {
    dot: "bg-emerald-500",
    ring: "ring-emerald-500/20",
    bg: "bg-emerald-50",
    text: "text-emerald-600",
    label: "Operational",
  },
  degraded: {
    dot: "bg-amber-400",
    ring: "ring-amber-400/20",
    bg: "bg-amber-50",
    text: "text-amber-600",
    label: "Degraded",
  },
  down: {
    dot: "bg-red-500",
    ring: "ring-red-500/20",
    bg: "bg-red-50",
    text: "text-red-600",
    label: "Down",
  },
};
