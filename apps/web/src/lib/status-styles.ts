import type { ProjectStatus, RevisionStatus } from "@/lib/projects";

export type StatusStyle = {
  dot: string;
  bg: string;
  text: string;
  label: string;
};

export const PROJECT_STATUS_STYLES: Record<ProjectStatus, StatusStyle> = {
  ACTIVE: {
    dot: "bg-positive",
    bg: "bg-positive-tint",
    text: "text-positive",
    label: "Active",
  },
  PAUSED: {
    dot: "bg-warning",
    bg: "bg-warning-tint",
    text: "text-warning",
    label: "Paused",
  },
  CANCELLED: {
    dot: "bg-danger",
    bg: "bg-danger-tint",
    text: "text-danger",
    label: "Cancelled",
  },
  ARCHIVED: {
    dot: "bg-slate-400",
    bg: "bg-slate-100",
    text: "text-slate-500",
    label: "Archived",
  },
};

export const REVISION_STATUS_STYLES: Record<RevisionStatus, StatusStyle> = {
  ACTIVE: {
    dot: "bg-blue-500",
    bg: "bg-blue-50",
    text: "text-blue-700",
    label: "Active",
  },
  DRAFT: {
    dot: "bg-violet-400",
    bg: "bg-violet-50",
    text: "text-violet-700",
    label: "Draft",
  },
  SUPERSEDED: {
    dot: "bg-slate-300",
    bg: "bg-slate-100",
    text: "text-slate-500",
    label: "Superseded",
  },
};

export type ServiceHealthTone = "operational" | "degraded" | "down";

export const SERVICE_HEALTH_STYLES: Record<
  ServiceHealthTone,
  StatusStyle & { ring: string }
> = {
  operational: {
    dot: "bg-positive",
    ring: "ring-emerald-500/20",
    bg: "bg-positive-tint",
    text: "text-positive",
    label: "Operational",
  },
  degraded: {
    dot: "bg-warning",
    ring: "ring-amber-400/20",
    bg: "bg-warning-tint",
    text: "text-warning",
    label: "Degraded",
  },
  down: {
    dot: "bg-danger",
    ring: "ring-red-500/20",
    bg: "bg-danger-tint",
    text: "text-danger",
    label: "Down",
  },
};
