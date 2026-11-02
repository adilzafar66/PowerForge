"use client";

import { Pencil, RotateCcw, Trash2, X } from "lucide-react";
import { useId, type ReactNode } from "react";

import {
  InfoBox,
  LifecycleChip,
  topoButtonClass,
} from "@/components/topology-ui";
import { Sheet } from "@/components/ui/sheet";
import {
  connectionKindLabel,
  directionLabel,
  nodeKindLabel,
  voltageText,
} from "@/lib/topology-presentation";
import type { ModelConnection, ModelNode } from "@/lib/engineering-model";

export function TopologyInspector({
  title,
  kind,
  removed,
  fields,
  info,
  warning,
  notice,
  writable,
  canEdit,
  canRemove,
  canRestore,
  restoreDisabled,
  onClose,
  onEdit,
  onRemove,
  onRestore,
}: {
  title: string;
  kind: "node" | "connection";
  removed: boolean;
  fields: [label: string, value: ReactNode][];
  info: string;
  warning?: string | null;
  notice?: ReactNode;
  writable: boolean;
  canEdit: boolean;
  canRemove: boolean;
  canRestore: boolean;
  restoreDisabled?: boolean;
  onClose: () => void;
  onEdit: () => void;
  onRemove: () => void;
  onRestore: () => void;
}) {
  const titleId = useId();
  return (
    <Sheet
      labelledBy={titleId}
      onClose={onClose}
      presentation="workspace-revision"
      className="w-[min(var(--pf-topology-inspector),100%)] leading-[inherit] max-[650px]:w-full"
    >
      <div className="flex items-start justify-between gap-3 border-b border-border px-[21px] pt-[18px] pb-4">
        <div className="min-w-0">
          <p className="m-0 mb-1.5 text-workspace-overline font-bold tracking-[0.72px] text-[var(--pf-text-tertiary)] uppercase">
            {kind === "node" ? "Node inspection" : "Connection inspection"}
          </p>
          <h2
            id={titleId}
            className="m-0 text-workspace-section leading-[1.4] font-semibold [overflow-wrap:anywhere] text-ink"
          >
            {title}
          </h2>
          <div className="mt-2.5">
            <LifecycleChip removed={removed} />
          </div>
        </div>
        <button
          type="button"
          aria-label="Close inspector"
          onClick={onClose}
          className={`${topoButtonClass()} size-[34px] shrink-0 px-0`}
        >
          <X aria-hidden strokeWidth={1.9} />
        </button>
      </div>
      {notice}
      <div className="min-h-0 flex-1 overflow-y-auto px-[22px] py-5">
        <dl className="m-0 grid grid-cols-[118px_1fr] gap-x-2.5 gap-y-2.5 text-workspace-caption">
          {fields.map(([label, value]) => (
            <div key={label} className="contents">
              <dt className="text-muted">{label}</dt>
              <dd className="m-0 text-ink [overflow-wrap:anywhere]">{value}</dd>
            </div>
          ))}
        </dl>
        <div className="mt-5 space-y-3">
          <InfoBox>{info}</InfoBox>
          {warning ? <InfoBox tone="warning">{warning}</InfoBox> : null}
        </div>
      </div>
      {writable ? (
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-[19px] py-[13px]">
          {canEdit ? (
            <button
              type="button"
              className={topoButtonClass()}
              onClick={onEdit}
            >
              <Pencil aria-hidden strokeWidth={1.8} />
              {kind === "node" ? "Edit node" : "Edit connection"}
            </button>
          ) : (
            <span />
          )}
          {canRemove ? (
            <button
              type="button"
              className={topoButtonClass("danger")}
              onClick={onRemove}
            >
              <Trash2 aria-hidden strokeWidth={1.8} />
              Remove
            </button>
          ) : null}
          {canRestore ? (
            <button
              type="button"
              className={topoButtonClass()}
              disabled={restoreDisabled}
              title={
                restoreDisabled
                  ? "Restore both endpoint nodes first"
                  : undefined
              }
              onClick={onRestore}
            >
              <RotateCcw aria-hidden strokeWidth={1.8} />
              Restore
            </button>
          ) : null}
        </div>
      ) : null}
    </Sheet>
  );
}

export function nodeInspectorFields(
  row: ModelNode,
  equipmentName: string | null,
): [string, ReactNode][] {
  return [
    ["Kind", nodeKindLabel(row.kind)],
    ["Equipment", equipmentName || "—"],
    ["Terminal key", row.terminal_key || "—"],
    ["Label", row.label?.trim() ? row.label : "Not set"],
    [
      "Ownership",
      row.managed_by_profile ? "Application-managed" : "Custom / standalone",
    ],
  ];
}

export function connectionInspectorFields(
  row: ModelConnection,
  fromLabel: string,
  toLabel: string,
): [string, ReactNode][] {
  return [
    ["From node", fromLabel],
    ["To node", toLabel],
    ["Kind", connectionKindLabel(row.connection_kind)],
    ["Direction", directionLabel(row.direction)],
    ["Phase", row.phase_configuration?.trim() || "Not set"],
    ["Nominal voltage", voltageText(row)],
  ];
}
