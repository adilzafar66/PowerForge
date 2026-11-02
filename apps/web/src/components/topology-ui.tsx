"use client";

import { X } from "lucide-react";
import { useId, type ReactNode } from "react";

import { Sheet } from "@/components/ui/sheet";
import { cn } from "@/lib/utils";

export const topoButton = {
  base: "inline-flex h-9 cursor-pointer items-center justify-center gap-2 rounded-[var(--pf-radius-control)] border border-border bg-panel px-[13px] text-workspace-label font-semibold whitespace-nowrap text-ink transition-[background-color,border-color,transform] duration-150 select-none hover:border-[#c0ccd5] hover:bg-soft focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)] active:translate-y-px disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 [&>svg]:size-[15px] [&>svg]:shrink-0",
  primary:
    "border-accent bg-accent text-white hover:border-accent hover:bg-accent-hover",
  danger:
    "border-[var(--pf-action-destructive-border)] text-[var(--pf-action-destructive)] hover:border-[var(--pf-action-destructive-border)] hover:bg-danger-tint",
  ghost:
    "border-transparent bg-transparent text-accent hover:border-transparent hover:bg-selection",
};

export function topoButtonClass(
  ...variants: (
    keyof Omit<typeof topoButton, "base"> | false | null | undefined
  )[]
) {
  return cn(
    topoButton.base,
    ...variants.map((v) => (v ? topoButton[v] : null)),
  );
}

export function TopologyHeader({
  revisionLabel,
  writable,
}: {
  revisionLabel?: string;
  writable: boolean;
}) {
  return (
    <header className="border-b border-border bg-panel px-[42px] pt-[26px] pb-[25px] max-[1240px]:px-[27px] max-[720px]:px-4">
      <div className="mx-auto flex max-w-[var(--pf-topology-max)] items-start justify-between gap-4 max-[720px]:flex-col">
        <div className="min-w-0">
          <h1 className="m-0 text-workspace-title leading-[1.2] font-bold tracking-[-0.75px] text-ink">
            Topology
          </h1>
          <p className="m-0 mt-[7px] text-workspace-caption text-muted">
            Manage electrical nodes, equipment terminals, and their connections
            in{" "}
            {revisionLabel ? (
              <strong className="font-bold text-ink">{revisionLabel}</strong>
            ) : (
              "this revision"
            )}
            .
          </p>
        </div>
        <span
          className={cn(
            "inline-flex shrink-0 items-center rounded-[20px] px-2.5 py-[5px] text-workspace-overline font-semibold",
            writable
              ? "bg-positive-tint text-positive"
              : "bg-danger-tint text-danger",
          )}
        >
          {writable ? "Editable revision" : "Read-only revision"}
        </span>
      </div>
    </header>
  );
}

export function TopologyMetrics({
  activeNodes,
  activeConnections,
  removed,
}: {
  activeNodes?: number;
  activeConnections?: number;
  removed?: number;
}) {
  return (
    <div className="mb-[25px] grid grid-cols-3 gap-[15px] max-[1240px]:gap-2.5 max-[720px]:grid-cols-1">
      <Metric value={activeNodes} label="Active nodes">
        Electrical nodes and terminals
      </Metric>
      <Metric value={activeConnections} label="Active connections">
        Current topology links
      </Metric>
      <Metric value={removed} label="Removed objects">
        History retained
      </Metric>
    </div>
  );
}

function Metric({
  value,
  label,
  children,
}: {
  value?: number;
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="min-h-[90px] rounded-[11px] border border-border bg-panel px-5 py-[17px]">
      <p className="m-0 text-2xl leading-[1.12] font-bold tracking-[-0.4px] text-ink">
        {value ?? "—"}
      </p>
      <p className="m-0 mt-2 text-workspace-caption text-muted">
        <span className="font-semibold text-ink">{label}</span>
        <span className="mt-0.5 block">{children}</span>
      </p>
    </div>
  );
}

export function EngineeringNotice() {
  return (
    <p
      role="note"
      className="m-0 mb-[25px] flex items-start gap-2.5 rounded-[9px] border border-[var(--pf-topology-notice-border)] bg-[var(--pf-topology-notice)] px-4 py-3 text-workspace-caption leading-[1.55] text-[var(--pf-topology-notice-text)]"
    >
      <span>
        <strong className="font-bold">
          Engineering topology, not a graphical SLD.
        </strong>{" "}
        Managed terminals originate from equipment profiles. A connection
        records association between nodes; nominal direction does not imply
        calculated power flow. An SLD visualization is planned for a later
        phase.
      </span>
    </p>
  );
}

export function TopologyReadOnlyNotice({ reason }: { reason: string }) {
  return (
    <p
      role="status"
      className="m-0 mb-[25px] rounded-[9px] border border-[var(--pf-documents-warning-border)] bg-warning-tint px-4 py-3 text-workspace-caption leading-[1.55] text-warning"
    >
      {reason}
    </p>
  );
}

export function LifecycleChip({ removed }: { removed: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[20px] px-2.5 py-[5px] text-workspace-overline font-semibold whitespace-nowrap before:size-1.5 before:rounded-full before:bg-current before:content-['']",
        removed
          ? "bg-danger-tint text-danger"
          : "bg-positive-tint text-positive",
      )}
    >
      {removed ? "Removed" : "Active"}
    </span>
  );
}

export function InfoBox({
  tone = "info",
  children,
}: {
  tone?: "info" | "warning";
  children: ReactNode;
}) {
  return (
    <p
      className={cn(
        "m-0 rounded-[9px] border px-3.5 py-3 text-workspace-caption leading-[1.55]",
        tone === "warning"
          ? "border-[var(--pf-documents-warning-border)] bg-warning-tint text-warning"
          : "border-[var(--pf-topology-notice-border)] bg-[var(--pf-topology-notice)] text-[var(--pf-topology-notice-text)]",
      )}
    >
      {children}
    </p>
  );
}

export function TopologyEditorDrawer({
  title,
  subtitle,
  onClose,
  footer,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  footer?: ReactNode;
  children: ReactNode;
}) {
  const titleId = useId();
  return (
    <Sheet
      labelledBy={titleId}
      onClose={onClose}
      presentation="workspace-revision"
      className="w-[min(var(--pf-topology-drawer),100%)] leading-[inherit]"
      autoFocusFirst
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-[22px] pt-[18px] pb-4">
        <div className="min-w-0">
          <h2
            id={titleId}
            className="m-0 text-workspace-section leading-[1.4] font-semibold text-ink"
          >
            {title}
          </h2>
          {subtitle ? (
            <p className="m-0 mt-1 text-workspace-caption text-muted">
              {subtitle}
            </p>
          ) : null}
        </div>
        <button
          type="button"
          aria-label="Close editor"
          onClick={onClose}
          className={cn(topoButtonClass(), "size-[34px] shrink-0 px-0")}
        >
          <X aria-hidden strokeWidth={1.9} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto px-[22px] py-5">
        {children}
      </div>
      {footer ? (
        <div className="flex flex-wrap justify-end gap-2 border-t border-border bg-[var(--pf-documents-dialog-footer)] px-[22px] py-3.5">
          {footer}
        </div>
      ) : null}
    </Sheet>
  );
}
