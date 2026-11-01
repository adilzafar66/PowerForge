import type { ReactNode } from "react";
import type {
  AttributeDefinition,
  EquipmentAttribute,
  InformationState,
  Lifecycle,
} from "@/lib/engineering-model";
import { cn } from "@/lib/utils";

export const INFORMATION_STATE_LABELS: Record<InformationState, string> = {
  PRESENT: "Present",
  NOT_POPULATED: "Not populated",
  MISSING: "Missing",
  NOT_APPLICABLE: "Not applicable",
  CONFLICTING: "Conflicting",
};

/** Exact server strings; numeric values are never parsed through Number. */
export function attributeValueText(row: EquipmentAttribute) {
  if (row.information_state !== "PRESENT")
    return INFORMATION_STATE_LABELS[row.information_state];
  const value =
    row.boolean_value != null
      ? row.boolean_value
        ? "True"
        : "False"
      : (row.numeric_value ?? row.integer_value ?? row.text_value ?? "");
  return row.unit ? `${value} ${row.unit}` : String(value);
}

/** Registry-flagged critical attributes first; required ones when none are critical. */
export function keyAttributes(definitions: AttributeDefinition[]) {
  const critical = definitions.filter((d) => d.critical);
  return critical.length ? critical : definitions.filter((d) => d.required);
}

export function LifecycleStatus({
  status,
  variant = "table",
}: {
  status: Lifecycle;
  variant?: "table" | "detail" | "title";
}) {
  const removed = status === "REMOVED";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-[6px] font-semibold whitespace-nowrap",
        removed ? "text-[var(--pf-text-tertiary)]" : "text-positive",
        variant === "table" && "text-workspace-caption",
        variant === "detail" && "text-workspace-caption",
        variant === "title" &&
          "text-workspace-caption tracking-[0.4px] uppercase",
        "before:h-[7px] before:w-[7px] before:shrink-0 before:rounded-full before:bg-current before:content-['']",
      )}
    >
      {removed ? "Removed" : "Active"}
    </span>
  );
}

export function GroupTitle({
  title,
  children,
}: {
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-center justify-between gap-3">
      <h2 className="m-0 text-workspace-section font-semibold tracking-[-0.2px]">
        {title}
      </h2>
      {children && (
        <span className="text-right text-workspace-caption text-muted">
          {children}
        </span>
      )}
    </div>
  );
}

export function SectionLabel({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h3
      className={cn(
        "m-0 mb-3 text-workspace-overline font-bold tracking-[1px] text-[var(--pf-text-tertiary)] uppercase",
        className,
      )}
    >
      {children}
    </h3>
  );
}

export function DetailPair({
  label,
  children,
  muted = false,
  className,
}: {
  label: string;
  children: ReactNode;
  muted?: boolean;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-[14px] py-2",
        className,
      )}
    >
      <dt className="text-workspace-caption text-muted">{label}</dt>
      <dd
        className={cn(
          "m-0 text-right text-workspace-caption font-semibold [overflow-wrap:anywhere]",
          muted ? "font-medium text-[var(--pf-text-tertiary)]" : "text-ink",
        )}
      >
        {children}
      </dd>
    </div>
  );
}

export function RequirementPill({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "required";
}) {
  return (
    <span
      className={cn(
        "ml-[5px] inline-flex rounded-[5px] px-[6px] py-[3px] align-middle text-[10.5px] leading-none font-semibold",
        tone === "required" ? "bg-selection text-accent" : "bg-soft text-muted",
      )}
    >
      {children}
    </span>
  );
}
