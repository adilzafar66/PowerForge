"use client";

import { Plus, Search } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useId, useState } from "react";

import { ConnectionEditorSheet } from "@/components/connection-editor-sheet";
import { ModelNodeEditor } from "@/components/model-node-editor";
import { LoadState, useModel } from "@/components/model-shared";
import { DocumentsDialog } from "@/components/documents-ui";
import {
  connectionInspectorFields,
  nodeInspectorFields,
  TopologyInspector,
} from "@/components/topology-inspector";
import {
  EngineeringNotice,
  LifecycleChip,
  TopologyEditorDrawer,
  TopologyHeader,
  TopologyMetrics,
  TopologyReadOnlyNotice,
  topoButtonClass,
} from "@/components/topology-ui";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { apiErrorOf } from "@/lib/api";
import {
  equipmentLabel,
  listConnections,
  listEquipment,
  listNodes,
  nodeLabels,
  removeConnection,
  removeNode,
  restoreConnection,
  restoreNode,
  type LifecycleFilter,
} from "@/lib/engineering-model";
import { useNavigationBlocker } from "@/lib/navigation-guard";
import { useResource } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import {
  connectionKindLabel,
  directionLabel,
  incidentActiveCount,
  matchesConnectionSearch,
  matchesLifecycle,
  matchesNodeSearch,
  nodeKindLabel,
  topologyCounts,
  voltageText,
} from "@/lib/topology-presentation";
import { cn } from "@/lib/utils";

type Selection =
  { kind: "node"; id: string } | { kind: "connection"; id: string };
type Editor =
  | { kind: "node"; id: string | "new" }
  | { kind: "connection"; id: string | "new" };
type PendingLeave = { kind: "close" } | { kind: "navigate"; href: string };
type Message = { tone: "success" | "error"; text: string };

export function TopologyWorkspace({
  readOnlyReason,
}: {
  readOnlyReason?: string | null;
} = {}) {
  const { projectId, revisionId, revisionLabel, registry, writable } =
    useModel();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("ACTIVE");
  const [searchInput, setSearchInput] = useState("");
  const [editor, setEditor] = useState<Editor | null>(null);
  const [editorDirty, setEditorDirty] = useState(false);
  const [pendingLeave, setPendingLeave] = useState<PendingLeave | null>(null);
  const [removing, setRemoving] = useState<Selection | null>(null);
  const [message, setMessage] = useState<Message | null>(null);
  const [missing, setMissing] = useState(false);
  const nodeFormId = useId();
  const connectionFormId = useId();
  const query = searchInput.trim().toLowerCase();

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
  const load = {
    loading: nodes.loading || connections.loading || equipment.loading,
    refreshing:
      nodes.refreshing || connections.refreshing || equipment.refreshing,
    error: nodes.error || connections.error || equipment.error,
    retry: () => {
      nodes.retry();
      connections.retry();
      equipment.retry();
    },
  };
  const data =
    nodes.data && connections.data && equipment.data
      ? {
          nodes: nodes.data,
          connections: connections.data,
          equipment: equipment.data,
        }
      : null;
  const labels = data
    ? nodeLabels(data.nodes, data.equipment, registry)
    : new Map<string, string>();
  const ownerLabels = new Map(
    data?.equipment.map((row) => [row.id, equipmentLabel(row, registry)]),
  );
  const counts = data
    ? topologyCounts(data.nodes, data.connections)
    : undefined;
  const visibleNodes =
    data?.nodes.filter(
      (row) =>
        matchesLifecycle(row, lifecycle) &&
        matchesNodeSearch(
          query,
          row,
          labels.get(row.id) ?? "",
          row.equipment_id ? (ownerLabels.get(row.equipment_id) ?? null) : null,
        ),
    ) ?? [];
  const visibleConnections =
    data?.connections.filter(
      (row) =>
        matchesLifecycle(row, lifecycle) &&
        matchesConnectionSearch(
          query,
          labels.get(row.from_node_id) ?? "",
          labels.get(row.to_node_id) ?? "",
        ),
    ) ?? [];
  const activeNodeIds = new Set(
    data?.nodes.filter((n) => n.lifecycle_status === "ACTIVE").map((n) => n.id),
  );
  const activeEquipmentIds = new Set(
    data?.equipment
      .filter((row) => row.lifecycle_status === "ACTIVE")
      .map((row) => row.id),
  );

  const urlSelection: Selection | null = params.get("node")
    ? { kind: "node", id: params.get("node")! }
    : params.get("connection")
      ? { kind: "connection", id: params.get("connection")! }
      : null;
  const [selectedParam, setSelectedParam] = useState<Selection | null>(
    urlSelection,
  );
  useEffect(() => {
    setSelectedParam(urlSelection);
    // The URL is the deep-link source; row clicks update local state first.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-sync when the ids change
  }, [urlSelection?.kind, urlSelection?.id]);
  const selectedNode =
    selectedParam?.kind === "node"
      ? data?.nodes.find((row) => row.id === selectedParam.id)
      : undefined;
  const selectedConnection =
    selectedParam?.kind === "connection"
      ? data?.connections.find((row) => row.id === selectedParam.id)
      : undefined;
  useEffect(() => {
    setMissing(
      !!selectedParam && !!nodes.data && !selectedNode && !selectedConnection,
    );
  }, [selectedParam, selectedNode, selectedConnection, nodes.data]);

  const href = useCallback(
    (change: (next: URLSearchParams) => void, method: "push" | "replace") => {
      const next = new URLSearchParams(params.toString());
      change(next);
      const url = `${pathname}${next.size ? `?${next}` : ""}`;
      router[method](url, { scroll: false });
    },
    [params, pathname, router],
  );
  const showSelection = useCallback(
    (next: Selection) => {
      setSelectedParam(next);
      setMessage(null);
      href((query) => {
        query.set("workspace", "model");
        query.set("view", "topology");
        if (next.kind === "node") {
          query.set("node", next.id);
          query.delete("connection");
        } else {
          query.set("connection", next.id);
          query.delete("node");
        }
      }, "push");
    },
    [href],
  );
  const hideSelection = useCallback(() => {
    setSelectedParam(null);
    setMissing(false);
    href((query) => {
      query.delete("node");
      query.delete("connection");
    }, "replace");
  }, [href]);

  const requestCloseEditor = useCallback(() => {
    if (editorDirty) {
      setPendingLeave({ kind: "close" });
      return;
    }
    setEditor(null);
  }, [editorDirty]);
  useNavigationBlocker(editorDirty, (next) =>
    setPendingLeave({ kind: "navigate", href: next }),
  );
  function discardAndLeave() {
    const leave = pendingLeave;
    setPendingLeave(null);
    setEditorDirty(false);
    setEditor(null);
    if (leave?.kind === "navigate") router.push(leave.href);
  }

  function changeLifecycle(value: LifecycleFilter) {
    setLifecycle(value);
    if (selectedParam) hideSelection();
  }

  async function restore(selection: Selection) {
    try {
      if (selection.kind === "node") {
        await restoreNode(projectId, revisionId, selection.id);
        setMessage({
          tone: "success",
          text: "Node restored; previous connections remain removed.",
        });
      } else {
        await restoreConnection(projectId, revisionId, selection.id);
        setMessage({
          tone: "success",
          text: "Connection restored; previous links remain unchanged.",
        });
      }
    } catch (error) {
      setMessage({ tone: "error", text: apiErrorOf(error).detail });
    }
  }

  async function confirmRemove() {
    const target = removing;
    setRemoving(null);
    if (!target) return;
    try {
      if (target.kind === "node") {
        await removeNode(projectId, revisionId, target.id);
        setMessage({ tone: "success", text: "Node removed." });
      } else {
        await removeConnection(projectId, revisionId, target.id);
        setMessage({ tone: "success", text: "Connection removed." });
      }
    } catch (error) {
      setMessage({ tone: "error", text: apiErrorOf(error).detail });
    }
  }

  const editingNode =
    editor?.kind === "node"
      ? editor.id === "new"
        ? undefined
        : data?.nodes.find((row) => row.id === editor.id)
      : undefined;
  const editingConnection =
    editor?.kind === "connection" && editor.id !== "new"
      ? data?.connections.find((row) => row.id === editor.id)
      : undefined;
  const messageLine = (className: string) =>
    message ? (
      <p
        role={message.tone === "error" ? "alert" : "status"}
        className={cn(
          "m-0 text-workspace-label",
          message.tone === "success" && "text-positive",
          message.tone === "error" && "text-danger",
          className,
        )}
      >
        {message.text}
      </p>
    ) : null;

  const removeTarget =
    removing?.kind === "node"
      ? data?.nodes.find((row) => row.id === removing.id)
      : removing?.kind === "connection"
        ? data?.connections.find((row) => row.id === removing.id)
        : undefined;
  const removeCount =
    removing?.kind === "node" && data
      ? incidentActiveCount(removing.id, data.connections)
      : 0;

  return (
    <section aria-label="Topology">
      <TopologyHeader revisionLabel={revisionLabel} writable={writable} />
      <div className="mx-auto max-w-[var(--pf-topology-max)] min-w-0 px-[42px] pt-[37px] pb-[52px] max-[1240px]:px-[27px] max-[1240px]:pt-[30px] max-[720px]:px-4">
        <TopologyMetrics
          activeNodes={counts?.activeNodes}
          activeConnections={counts?.activeConnections}
          removed={counts?.removed}
        />
        {readOnlyReason ? (
          <TopologyReadOnlyNotice reason={readOnlyReason} />
        ) : null}
        <EngineeringNotice />
        {messageLine("mb-3.5")}
        <LoadState {...load} />
        {data ? (
          <>
            <RegisterCard
              title={`Nodes · ${visibleNodes.length}`}
              subtitle="Terminals belong to equipment; standalone junctions are electrical nodes."
              action={
                writable ? (
                  <button
                    type="button"
                    className={topoButtonClass("primary")}
                    onClick={() => setEditor({ kind: "node", id: "new" })}
                  >
                    <Plus aria-hidden strokeWidth={1.8} />
                    Add Electrical Node
                  </button>
                ) : null
              }
              toolbar={
                <>
                  <label className="flex h-[38px] w-full max-w-[430px] items-center gap-2 rounded-[var(--pf-radius-control)] border border-border bg-panel px-3 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--pf-ring)]">
                    <Search
                      aria-hidden
                      className="size-4 shrink-0 text-muted"
                      strokeWidth={1.7}
                    />
                    <input
                      aria-label="Search topology"
                      value={searchInput}
                      onChange={(e) => setSearchInput(e.target.value)}
                      placeholder="Search nodes or equipment…"
                      className="min-w-0 flex-1 bg-transparent text-workspace-caption text-ink outline-none placeholder:text-muted"
                    />
                  </label>
                  <Select
                    aria-label="Lifecycle"
                    value={lifecycle}
                    onValueChange={(value) =>
                      changeLifecycle(value as LifecycleFilter)
                    }
                    className="h-[38px] min-w-[140px] rounded-[var(--pf-radius-control)] border-border px-3 text-workspace-caption font-semibold"
                  >
                    <option value="ACTIVE">Active</option>
                    <option value="REMOVED">Removed</option>
                    <option value="ALL">All</option>
                  </Select>
                </>
              }
            >
              <RegisterTable
                label="Nodes"
                minWidth="820px"
                columns={[
                  ["29%", "Node"],
                  ["20%", "Type"],
                  ["18%", "Equipment"],
                  ["19%", "Terminal"],
                  ["14%", "State"],
                ]}
                empty="No nodes match this filter."
                footer={`${visibleNodes.length} ${visibleNodes.length === 1 ? "node" : "nodes"}`}
                selected={
                  selectedParam?.kind === "node" ? selectedParam.id : null
                }
                rows={visibleNodes.map((row) => ({
                  id: row.id,
                  removed: row.lifecycle_status === "REMOVED",
                  cells: [
                    <span key="name">
                      <strong className="block font-semibold [overflow-wrap:anywhere]">
                        {labels.get(row.id)}
                      </strong>
                      {row.kind === "ELECTRICAL_NODE" ? (
                        <span className="mt-0.5 block text-workspace-caption text-muted">
                          Standalone electrical junction
                        </span>
                      ) : null}
                    </span>,
                    nodeKindLabel(row.kind),
                    row.equipment_id
                      ? (ownerLabels.get(row.equipment_id) ?? "—")
                      : "—",
                    <span key="terminal">
                      {row.terminal_key ?? "—"}
                      {row.managed_by_profile ? (
                        <span className="mt-0.5 block text-workspace-caption text-muted">
                          Application-managed
                        </span>
                      ) : null}
                    </span>,
                    <LifecycleChip
                      key="state"
                      removed={row.lifecycle_status === "REMOVED"}
                    />,
                  ],
                }))}
                onOpen={(id) => showSelection({ kind: "node", id })}
              />
            </RegisterCard>

            <RegisterCard
              title={`Connections · ${visibleConnections.length}`}
              subtitle="Connect distinct active endpoints. Parallel connections are allowed."
              action={
                writable ? (
                  <button
                    type="button"
                    className={topoButtonClass("primary")}
                    onClick={() => setEditor({ kind: "connection", id: "new" })}
                  >
                    <Plus aria-hidden strokeWidth={1.8} />
                    Add Connection
                  </button>
                ) : null
              }
            >
              <RegisterTable
                label="Connections"
                minWidth="900px"
                columns={[
                  ["24%", "From"],
                  ["24%", "To"],
                  ["15%", "Kind"],
                  ["15%", "Direction"],
                  ["10%", "Voltage"],
                  ["12%", "State"],
                ]}
                empty="No connections match this filter."
                footer={`${visibleConnections.length} ${visibleConnections.length === 1 ? "connection" : "connections"}`}
                selected={
                  selectedParam?.kind === "connection" ? selectedParam.id : null
                }
                rows={visibleConnections.map((row) => ({
                  id: row.id,
                  removed: row.lifecycle_status === "REMOVED",
                  cells: [
                    labels.get(row.from_node_id) ?? "Unavailable node",
                    labels.get(row.to_node_id) ?? "Unavailable node",
                    connectionKindLabel(row.connection_kind),
                    directionLabel(row.direction),
                    voltageText(row),
                    <LifecycleChip
                      key="state"
                      removed={row.lifecycle_status === "REMOVED"}
                    />,
                  ],
                }))}
                onOpen={(id) => showSelection({ kind: "connection", id })}
              />
            </RegisterCard>
          </>
        ) : null}

        {missing && selectedParam ? (
          <p role="status" className="mt-4 text-workspace-label text-muted">
            That {selectedParam.kind} is not in this revision.{" "}
            <button
              type="button"
              className={topoButtonClass("ghost")}
              onClick={hideSelection}
            >
              Clear selection
            </button>
          </p>
        ) : null}
      </div>

      {selectedNode ? (
        <TopologyInspector
          kind="node"
          title={labels.get(selectedNode.id) ?? selectedNode.id}
          removed={selectedNode.lifecycle_status === "REMOVED"}
          fields={nodeInspectorFields(
            selectedNode,
            selectedNode.equipment_id
              ? (ownerLabels.get(selectedNode.equipment_id) ?? null)
              : null,
          )}
          info={
            selectedNode.managed_by_profile
              ? "This terminal is controlled by the equipment profile. Its key and lifecycle cannot be changed independently."
              : "Restoring a node does not automatically restore connections previously removed with it."
          }
          warning={
            selectedNode.lifecycle_status === "REMOVED" &&
            selectedNode.kind === "EQUIPMENT_TERMINAL" &&
            !(
              selectedNode.equipment_id &&
              activeEquipmentIds.has(selectedNode.equipment_id)
            )
              ? "Restore the owning equipment before restoring this terminal."
              : null
          }
          notice={messageLine("border-b border-border px-[21px] py-3")}
          writable={writable}
          canEdit={selectedNode.lifecycle_status === "ACTIVE"}
          canRemove={
            !selectedNode.managed_by_profile &&
            selectedNode.lifecycle_status === "ACTIVE"
          }
          canRestore={
            !selectedNode.managed_by_profile &&
            selectedNode.lifecycle_status === "REMOVED"
          }
          restoreDisabled={
            selectedNode.kind === "EQUIPMENT_TERMINAL" &&
            !(
              selectedNode.equipment_id &&
              activeEquipmentIds.has(selectedNode.equipment_id)
            )
          }
          onClose={hideSelection}
          onEdit={() => setEditor({ kind: "node", id: selectedNode.id })}
          onRemove={() => setRemoving({ kind: "node", id: selectedNode.id })}
          onRestore={() => void restore({ kind: "node", id: selectedNode.id })}
        />
      ) : null}

      {selectedConnection ? (
        <TopologyInspector
          kind="connection"
          title={`Connection ${selectedConnection.id.slice(0, 8)}`}
          removed={selectedConnection.lifecycle_status === "REMOVED"}
          fields={connectionInspectorFields(
            selectedConnection,
            labels.get(selectedConnection.from_node_id) ?? "Unavailable node",
            labels.get(selectedConnection.to_node_id) ?? "Unavailable node",
          )}
          info="Nominal direction describes stored endpoint order, not electrical power flow. Voltages are normalized to kV by the server."
          warning={
            selectedConnection.lifecycle_status === "REMOVED" &&
            !(
              activeNodeIds.has(selectedConnection.from_node_id) &&
              activeNodeIds.has(selectedConnection.to_node_id)
            )
              ? "Restore both endpoint nodes before restoring this connection."
              : null
          }
          notice={messageLine("border-b border-border px-[21px] py-3")}
          writable={writable}
          canEdit={selectedConnection.lifecycle_status === "ACTIVE"}
          canRemove={selectedConnection.lifecycle_status === "ACTIVE"}
          canRestore={selectedConnection.lifecycle_status === "REMOVED"}
          restoreDisabled={
            !(
              activeNodeIds.has(selectedConnection.from_node_id) &&
              activeNodeIds.has(selectedConnection.to_node_id)
            )
          }
          onClose={hideSelection}
          onEdit={() =>
            setEditor({ kind: "connection", id: selectedConnection.id })
          }
          onRemove={() =>
            setRemoving({ kind: "connection", id: selectedConnection.id })
          }
          onRestore={() =>
            void restore({ kind: "connection", id: selectedConnection.id })
          }
        />
      ) : null}

      {editor?.kind === "node" && (editor.id !== "new" || writable) ? (
        <TopologyEditorDrawer
          title={
            editor.id === "new"
              ? "Add Electrical Node"
              : editingNode?.kind === "EQUIPMENT_TERMINAL"
                ? "Edit Terminal Label"
                : "Edit Electrical Node"
          }
          subtitle={revisionLabel ? `Topology · ${revisionLabel}` : "Topology"}
          onClose={requestCloseEditor}
          footer={
            writable &&
            (!editingNode || editingNode.lifecycle_status === "ACTIVE") ? (
              <>
                <button
                  type="button"
                  className={topoButtonClass()}
                  onClick={requestCloseEditor}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form={nodeFormId}
                  className={topoButtonClass("primary")}
                  disabled={editor.id !== "new" && !editorDirty}
                >
                  {editor.id === "new" ? "Create" : "Save changes"}
                </button>
              </>
            ) : null
          }
        >
          <ModelNodeEditor
            key={editor.id}
            formId={nodeFormId}
            row={editingNode}
            equipmentName={
              editingNode?.equipment_id
                ? (ownerLabels.get(editingNode.equipment_id) ?? null)
                : null
            }
            onSaved={() => {
              setEditorDirty(false);
              setEditor(null);
              setMessage({
                tone: "success",
                text:
                  editor.id === "new"
                    ? "Electrical node created."
                    : "Node saved.",
              });
            }}
            onDirtyChange={setEditorDirty}
          />
        </TopologyEditorDrawer>
      ) : null}

      {editor?.kind === "connection" &&
      (editor.id !== "new" || writable) &&
      data ? (
        <TopologyEditorDrawer
          title={editor.id === "new" ? "Add Connection" : "Edit Connection"}
          subtitle={revisionLabel ? `Topology · ${revisionLabel}` : "Topology"}
          onClose={requestCloseEditor}
          footer={
            writable &&
            (!editingConnection ||
              editingConnection.lifecycle_status === "ACTIVE") ? (
              <>
                <button
                  type="button"
                  className={topoButtonClass()}
                  onClick={requestCloseEditor}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  form={connectionFormId}
                  className={topoButtonClass("primary")}
                  disabled={editor.id !== "new" && !editorDirty}
                >
                  {editor.id === "new" ? "Create" : "Save changes"}
                </button>
              </>
            ) : null
          }
        >
          <ConnectionEditorSheet
            key={editor.id}
            formId={connectionFormId}
            row={editingConnection}
            nodes={data.nodes}
            labels={labels}
            onClose={() => {
              setEditorDirty(false);
              setEditor(null);
              setMessage({
                tone: "success",
                text:
                  editor.id === "new"
                    ? "Connection created."
                    : "Connection saved.",
              });
            }}
            onDirtyChange={setEditorDirty}
          />
        </TopologyEditorDrawer>
      ) : null}

      {pendingLeave ? (
        <DocumentsDialog
          title="Discard unsaved changes?"
          description="You have unsaved topology edits."
          onClose={() => setPendingLeave(null)}
          footer={
            <>
              <button
                type="button"
                className={topoButtonClass()}
                onClick={() => setPendingLeave(null)}
              >
                Keep editing
              </button>
              <button
                type="button"
                className={topoButtonClass("danger")}
                onClick={discardAndLeave}
              >
                Discard changes
              </button>
            </>
          }
        >
          <p className="m-0 rounded-[9px] border border-[var(--pf-documents-warning-border)] bg-warning-tint px-3.5 py-3 text-workspace-caption text-warning">
            {pendingLeave.kind === "close"
              ? "Your changes will be lost if you close the editor."
              : "Your changes will be lost if you leave this page."}
          </p>
        </DocumentsDialog>
      ) : null}

      {removing && removeTarget ? (
        <ConfirmDialog
          presentation="workspace"
          className="max-w-[470px]"
          title={
            removing.kind === "node" ? "Remove node?" : "Remove connection?"
          }
          message={
            removing.kind === "node"
              ? `Removing this node also removes ${removeCount} active incident connection${removeCount === 1 ? "" : "s"}. Restoring the node will NOT restore those connections.`
              : "This connection will be soft-removed. You can restore it later if both endpoints remain active."
          }
          confirmLabel="Remove"
          danger
          onCancel={() => setRemoving(null)}
          onConfirm={() => void confirmRemove()}
        />
      ) : null}
    </section>
  );
}

function RegisterCard({
  title,
  subtitle,
  action,
  toolbar,
  children,
}: {
  title: string;
  subtitle: string;
  action?: React.ReactNode;
  toolbar?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-5 overflow-hidden rounded-[12px] border border-border bg-panel">
      <div className="flex items-start justify-between gap-3 px-[18px] pt-[18px] pb-3 max-[720px]:flex-col">
        <div className="min-w-0">
          <h2 className="m-0 text-workspace-subheading font-semibold tracking-[-0.2px] text-ink">
            {title}
          </h2>
          <p className="m-0 mt-1 text-workspace-caption text-muted">
            {subtitle}
          </p>
        </div>
        {action}
      </div>
      {toolbar ? (
        <div className="flex flex-wrap items-center gap-[11px] border-t border-border px-[18px] py-3.5">
          {toolbar}
        </div>
      ) : null}
      {children}
    </section>
  );
}

function RegisterTable({
  label,
  minWidth,
  columns,
  rows,
  selected,
  empty,
  footer,
  onOpen,
}: {
  label: string;
  minWidth: string;
  columns: [width: string, name: string][];
  rows: {
    id: string;
    removed: boolean;
    cells: React.ReactNode[];
  }[];
  selected: string | null;
  empty: string;
  footer: string;
  onOpen: (id: string) => void;
}) {
  return (
    <>
      <div className="relative overflow-x-auto">
        {rows.length === 0 ? (
          <p className="m-0 px-5 py-10 text-center text-workspace-caption text-muted">
            {empty}
          </p>
        ) : (
          <table
            aria-label={label}
            className="w-full table-fixed border-collapse"
            style={{ minWidth }}
          >
            <colgroup>
              {columns.map(([width, name]) => (
                <col key={name} style={{ width }} />
              ))}
            </colgroup>
            <thead>
              <tr className="border-y border-[var(--pf-border-row)] bg-[var(--pf-table-heading)]">
                {columns.map(([, name], index) => (
                  <th
                    key={name}
                    scope="col"
                    className={cn(
                      "px-3 py-2.5 text-left text-workspace-overline font-bold tracking-[0.4px] text-muted uppercase",
                      index === 0 && "pl-[21px]",
                    )}
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => {
                const isSelected = row.id === selected;
                return (
                  <tr
                    key={row.id}
                    tabIndex={0}
                    aria-selected={isSelected}
                    className={cn(
                      "cursor-pointer border-b border-[var(--pf-border-row)] outline-none [transition:background-color_160ms_ease] hover:bg-[var(--pf-equipment-row-hover)] focus-visible:[box-shadow:inset_0_0_0_2px_var(--pf-action)]",
                      isSelected && "bg-[var(--pf-equipment-row-selected)]",
                      row.removed && "text-muted",
                    )}
                    onClick={(event) => {
                      event.currentTarget.focus();
                      onOpen(row.id);
                    }}
                    onKeyDown={(event) => {
                      if (
                        event.target === event.currentTarget &&
                        (event.key === "Enter" || event.key === " ")
                      ) {
                        event.preventDefault();
                        onOpen(row.id);
                      }
                    }}
                  >
                    {row.cells.map((cell, index) => (
                      <td
                        key={index}
                        className={cn(
                          "px-3 py-3 text-workspace-caption align-top [overflow-wrap:anywhere]",
                          index === 0 && "pl-[21px] text-workspace-body",
                          row.removed && index === 0 && "line-through",
                        )}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-border px-[18px] py-2.5 text-workspace-caption text-muted">
        <span>{footer}</span>
        <span>Click a row for details</span>
      </div>
    </>
  );
}
