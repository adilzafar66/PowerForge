import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import {
  PROJECT_STATUS_STYLES,
  REVISION_STATUS_STYLES,
  type StatusStyle,
} from "@/lib/status-styles";
import type { ProjectStatus, RevisionStatus } from "@/lib/projects";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11.5px] font-semibold tracking-wide",
);

export type BadgeProps = React.HTMLAttributes<HTMLSpanElement> &
  VariantProps<typeof badgeVariants> & {
    presentation?: "default" | "workspace";
    status?: ProjectStatus | RevisionStatus | string;
    kind?: "project" | "revision";
    /** @deprecated Prefer status + kind. Kept for transitional call sites. */
    variant?:
      | "default"
      | "active"
      | "paused"
      | "cancelled"
      | "archived"
      | "draft"
      | "superseded";
  };

function styleFromLegacyVariant(
  variant: BadgeProps["variant"],
): StatusStyle | null {
  switch (variant) {
    case "active":
      return PROJECT_STATUS_STYLES.ACTIVE;
    case "paused":
      return PROJECT_STATUS_STYLES.PAUSED;
    case "cancelled":
      return PROJECT_STATUS_STYLES.CANCELLED;
    case "archived":
      return PROJECT_STATUS_STYLES.ARCHIVED;
    case "draft":
      return REVISION_STATUS_STYLES.DRAFT;
    case "superseded":
      return REVISION_STATUS_STYLES.SUPERSEDED;
    default:
      return null;
  }
}

function resolveStyle({
  status,
  kind = "project",
  variant,
}: Pick<BadgeProps, "status" | "kind" | "variant">): StatusStyle | null {
  if (status) {
    if (kind === "revision") {
      return REVISION_STATUS_STYLES[status as RevisionStatus] ?? null;
    }
    return PROJECT_STATUS_STYLES[status as ProjectStatus] ?? null;
  }
  return styleFromLegacyVariant(variant);
}

function Badge({
  className,
  presentation = "default",
  status,
  kind = "project",
  variant,
  children,
  ...props
}: BadgeProps) {
  if (presentation === "workspace") {
    return (
      <span
        {...props}
        className={cn(
          "inline-flex items-center gap-[6px] py-[5px] px-[10px] rounded-[var(--pf-radius-pill)] text-workspace-badge font-semibold whitespace-nowrap leading-[normal] text-muted bg-soft before:content-[''] before:w-[7px] before:h-[7px] before:rounded-[50%] before:bg-[currentColor]",
          status === "ACTIVE" &&
            "text-[var(--pf-positive)] bg-[var(--pf-positive-tint)]",
          status === "DRAFT" &&
            "text-[var(--pf-status-draft)] bg-[var(--pf-status-draft-tint)]",
          status === "PAUSED" &&
            "text-[var(--pf-status-paused)] bg-[var(--pf-warning-tint)]",
          status === "CANCELLED" &&
            "text-[var(--pf-status-cancelled)] bg-[var(--pf-danger-tint)]",
          className,
        )}
      >
        {children ??
          (status ? status.charAt(0) + status.slice(1).toLowerCase() : "")}
      </span>
    );
  }
  const style = resolveStyle({ status, kind, variant });
  if (!style && !children) {
    return null;
  }

  const label = children ?? style?.label.toUpperCase();

  return (
    <span
      className={cn(
        badgeVariants(),
        style ? `${style.bg} ${style.text}` : "bg-slate-100 text-slate-700",
        className,
      )}
      {...props}
    >
      {style ? (
        <span className={cn("h-1.5 w-1.5 shrink-0 rounded-full", style.dot)} />
      ) : null}
      {label}
    </span>
  );
}

export { Badge, badgeVariants };
