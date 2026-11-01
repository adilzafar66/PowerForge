"use client";
import type { ReactNode } from "react";
import { Pencil, X } from "lucide-react";
import { useModel } from "@/components/model-shared";
import {
  DetailPair,
  LifecycleStatus,
  SectionLabel,
  attributeValueText,
  keyAttributes,
} from "@/components/equipment-ui";
import { useEquipmentSnapshot } from "@/components/use-equipment-editor";
import { AsyncState } from "@/components/ui/async-state";
import { Button } from "@/components/ui/button";
import { useResource } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import {
  equipmentLabel,
  listConnections,
  listEquipment,
  listNodes,
  nodeLabels,
  typeLabel,
  type EquipmentSnapshot,
} from "@/lib/engineering-model";

export function EquipmentQuickDetails({
  id,
  onClose,
  onEdit,
}: {
  id: string;
  onClose: () => void;
  onEdit: () => void;
}) {
  const { registry, revisionLabel } = useModel();
  const { query } = useEquipmentSnapshot(id, onClose);
  const snapshot = query.data;
  const row = snapshot?.equipment;
  return (
    <aside
      aria-label="Equipment quick details"
      onKeyDown={(e) => {
        if (e.key === "Escape") onClose();
      }}
      className="min-w-0 overflow-hidden rounded-[var(--pf-radius-lg)] border border-border bg-panel shadow-workspace-inspector animate-[workspace-inspector_var(--pf-transition-normal)_var(--pf-ease-drawer)] motion-reduce:animate-none"
    >
      <div className="flex items-start justify-between border-b border-border px-[23px] pt-5 pb-[18px]">
        <div className="min-w-0">
          <p className="m-0 text-workspace-overline font-bold tracking-[0.9px] text-[var(--pf-text-tertiary)] uppercase">
            Equipment quick details
          </p>
          <h2 className="mt-[5px] mb-[7px] text-workspace-editor leading-[1.2] font-bold tracking-[-0.4px] [overflow-wrap:anywhere]">
            {row ? equipmentLabel(row, registry) : "Equipment"}
          </h2>
          <p className="m-0 text-workspace-caption text-muted">
            {row ? typeLabel(registry, row.equipment_type) : "Loading…"}
          </p>
        </div>
        <button
          type="button"
          aria-label="Close equipment details"
          onClick={onClose}
          className="inline-flex h-[30px] w-[30px] shrink-0 items-center justify-center rounded-[var(--pf-radius-sm)] text-muted hover:bg-soft"
        >
          <X aria-hidden className="h-[17px] w-[17px]" strokeWidth={1.7} />
        </button>
      </div>
      {!snapshot && (
        <div className="px-[23px] py-[17px]">
          <AsyncState
            pending={query.isPending}
            error={query.error}
            retry={query.refetch}
          />
        </div>
      )}
      {snapshot && row && (
        <>
          <Section label="Overview">
            <DetailPair label="Equipment name" muted={!row.name}>
              {row.name || "Not provided"}
            </DetailPair>
            <DetailPair label="Lifecycle">
              <LifecycleStatus status={row.lifecycle_status} variant="detail" />
            </DetailPair>
            <DetailPair label="Revision">
              {revisionLabel ?? "Current"}
            </DetailPair>
          </Section>
          <KeyInformation snapshot={snapshot} />
          <Topology snapshot={snapshot} />
          <Section label="Engineering provenance">
            <DetailPair label="Origin">{row.origin}</DetailPair>
            <DetailPair label="Verification">
              {row.verification_state}
            </DetailPair>
          </Section>
        </>
      )}
      <div className="flex gap-[10px] px-[23px] py-[17px]">
        <Button
          presentation="workspace"
          variant="primary"
          className="min-h-[39px] flex-1 px-4"
          disabled={!snapshot}
          onClick={onEdit}
        >
          <Pencil aria-hidden strokeWidth={1.7} />
          Open full editor
        </Button>
      </div>
    </aside>
  );
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="border-b border-border px-[23px] pt-[17px] pb-[19px]">
      <SectionLabel>{label}</SectionLabel>
      <dl className="m-0">{children}</dl>
    </section>
  );
}

function KeyInformation({ snapshot }: { snapshot: EquipmentSnapshot }) {
  const { registry } = useModel();
  const definitions = keyAttributes(
    registry.equipment_types.find(
      (t) => t.key === snapshot.equipment.equipment_type,
    )?.attributes ?? [],
  );
  return (
    <Section label="Key electrical information">
      {definitions.length === 0 && (
        <p className="m-0 py-2 text-workspace-caption text-muted">
          The registry defines no critical or required attributes for this type.
        </p>
      )}
      {definitions.map((definition) => {
        const row = snapshot.attributes.find(
          (a) => a.attribute_key === definition.key,
        );
        return (
          <DetailPair
            key={definition.key}
            label={definition.display_name}
            muted={row?.information_state !== "PRESENT"}
          >
            {row ? attributeValueText(row) : "Unavailable"}
          </DetailPair>
        );
      })}
    </Section>
  );
}

function Topology({ snapshot }: { snapshot: EquipmentSnapshot }) {
  const { projectId, revisionId, registry } = useModel();
  const nodes = useResource(keys.nodes(projectId, revisionId), () =>
    listNodes(projectId, revisionId, "ALL"),
  );
  const connections = useResource(keys.connections(projectId, revisionId), () =>
    listConnections(projectId, revisionId, "ALL"),
  );
  const equipment = useResource(
    keys.equipment(projectId, revisionId, { lifecycle_status: "ALL" }),
    () => listEquipment(projectId, revisionId, { lifecycle_status: "ALL" }),
  );
  const terminals = snapshot.terminals.filter(
    (n) => n.lifecycle_status === "ACTIVE",
  );
  const own = new Set(terminals.map((n) => n.id));
  const incident =
    connections.data?.filter(
      (c) =>
        c.lifecycle_status === "ACTIVE" &&
        (own.has(c.from_node_id) || own.has(c.to_node_id)),
    ) ?? [];
  const labels =
    nodes.data && equipment.data
      ? nodeLabels(nodes.data, equipment.data, registry)
      : new Map<string, string>();
  const keyOf = new Map(terminals.map((n) => [n.id, n.terminal_key]));
  const unavailable = nodes.error || connections.error || equipment.error;
  const loading = !unavailable && (!connections.data || !nodes.data);
  return (
    <section className="border-b border-border px-[23px] pt-[17px] pb-[19px]">
      <SectionLabel>Topology</SectionLabel>
      <div className="rounded-[var(--pf-radius-md)] border border-border bg-canvas px-[13px] py-3 text-workspace-caption leading-[var(--pf-leading-relaxed)] text-muted">
        {unavailable ? (
          "Topology information is unavailable."
        ) : loading ? (
          "Loading connections…"
        ) : (
          <>
            <strong className="font-semibold text-ink">
              {incident.length === 1
                ? "1 active connection"
                : `${incident.length} active connections`}
            </strong>
            {incident.map((c) => {
              const mine = own.has(c.from_node_id)
                ? c.from_node_id
                : c.to_node_id;
              const other =
                mine === c.from_node_id ? c.to_node_id : c.from_node_id;
              return (
                <span key={c.id} className="block [overflow-wrap:anywhere]">
                  {keyOf.get(mine)} ↔ {labels.get(other) ?? "Unknown node"}
                </span>
              );
            })}
            {incident.length === 0 && (
              <span className="block">
                {terminals.length
                  ? `Terminals: ${terminals.map((n) => n.terminal_key).join(", ")}`
                  : "No active terminals"}
              </span>
            )}
          </>
        )}
      </div>
    </section>
  );
}
