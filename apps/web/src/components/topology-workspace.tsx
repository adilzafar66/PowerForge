"use client";

import { useState } from "react";
import { useResource } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { ConnectionEditorSheet } from "@/components/connection-editor-sheet";
import { ModelNodeEditor } from "@/components/model-node-editor";
import {
  LifecycleControl,
  LoadState,
  ModelAction,
  ModelSheet,
  NODE_REMOVE_WARNING,
  useModel,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  revisionTable,
  revisionRowClass,
  revisionPrimaryClass,
  ModelLifecycleState,
} from "@/components/ui/revision-table";
import { cn } from "@/lib/utils";
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

export function TopologyWorkspace() {
  const { projectId, revisionId, registry, writable } = useModel();
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("ACTIVE");
  const [nodeEditor, setNodeEditor] = useState<string | null>(null);
  const [connectionEditor, setConnectionEditor] = useState<string | null>(null);
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
  const query = {
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
  const visible = (row: { lifecycle_status: string }) =>
    lifecycle === "ALL" || row.lifecycle_status === lifecycle;
  const visibleNodes = data?.nodes.filter(visible) ?? [];
  const visibleConnections = data?.connections.filter(visible) ?? [];
  const activeNodeIds = new Set(
    data?.nodes.filter((n) => n.lifecycle_status === "ACTIVE").map((n) => n.id),
  );
  const active = (id: string) => activeNodeIds.has(id);
  const selectedNode = data?.nodes.find((n) => n.id === nodeEditor);
  const selectedConnection = data?.connections.find(
    (c) => c.id === connectionEditor,
  );
  return (
    <div className="space-y-6">
      <LifecycleControl value={lifecycle} onChange={setLifecycle} />
      <LoadState {...query} />
      {data && (
        <>
          <section className="space-y-3" aria-label="Topology nodes">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold">Nodes {visibleNodes.length}</h2>
              {writable && (
                <Button onClick={() => setNodeEditor("new")}>
                  Add Electrical Node
                </Button>
              )}
            </div>
            <p className="text-xs text-slate-500">
              Manage equipment terminals from Equipment details. Restoring a
              node never restores its old connections.
            </p>
            {visibleNodes.length === 0 && (
              <Card className={revisionTable.empty}>
                {lifecycle === "ACTIVE"
                  ? "No active nodes in this revision. Equipment provides its normal terminals; add an electrical node for a junction."
                  : "No nodes match this lifecycle filter."}
              </Card>
            )}
            {visibleNodes.length > 0 && (
              <Card className="overflow-x-auto">
                <table className={revisionTable.table} aria-label="Nodes">
                  <thead className={revisionTable.head}>
                    <tr className={revisionTable.headerRow}>
                      {[
                        "Node",
                        "Type",
                        "Equipment / Owner",
                        "Terminal",
                        "State",
                        "Actions",
                      ].map((h, index) => (
                        <th
                          key={h}
                          scope="col"
                          className={cn(
                            revisionTable.header,
                            index === 0 && "px-5",
                            h === "Actions" && "text-right",
                          )}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody
                    className={cn(
                      "text-slate-700",
                      query.loading && "opacity-60",
                    )}
                  >
                    {visibleNodes.map((n, index) => (
                      <tr
                        key={n.id}
                        tabIndex={0}
                        aria-selected={n.id === nodeEditor}
                        className={revisionRowClass(
                          index === 0,
                          n.id === nodeEditor,
                          n.lifecycle_status === "REMOVED",
                        )}
                        onClick={(event) => {
                          event.currentTarget.focus();
                          setNodeEditor(n.id);
                        }}
                        onKeyDown={(e) => {
                          if (
                            e.target === e.currentTarget &&
                            (e.key === "Enter" || e.key === " ")
                          ) {
                            e.preventDefault();
                            setNodeEditor(n.id);
                          }
                        }}
                      >
                        <td className={revisionTable.primaryCell}>
                          <div
                            className={revisionPrimaryClass(
                              n.lifecycle_status === "REMOVED",
                            )}
                          >
                            {labels.get(n.id)}
                          </div>
                        </td>
                        <td className={revisionTable.cell}>
                          {n.kind === "ELECTRICAL_NODE"
                            ? "Electrical node"
                            : "Equipment terminal"}
                        </td>
                        <td className={revisionTable.cell}>
                          <span className="mr-2 text-xs text-slate-500 md:hidden">
                            Equipment / Owner
                          </span>
                          {n.equipment_id
                            ? (ownerLabels.get(n.equipment_id) ??
                              "Unavailable equipment")
                            : "—"}
                        </td>
                        <td className={revisionTable.cell}>
                          <span className="mr-2 text-xs text-slate-500 md:hidden">
                            Terminal
                          </span>
                          {n.terminal_key ?? "—"}
                          {n.managed_by_profile && (
                            <span
                              className={cn("block", revisionTable.secondary)}
                            >
                              Application-managed
                            </span>
                          )}
                        </td>
                        <td className={revisionTable.cell}>
                          <ModelLifecycleState
                            removed={n.lifecycle_status === "REMOVED"}
                          />
                        </td>
                        <td className={revisionTable.actionsCell}>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              setNodeEditor(n.id);
                            }}
                          >
                            Open
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </section>
          <section className="space-y-3" aria-label="Topology connections">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="font-semibold">
                Connections {visibleConnections.length}
              </h2>
              {writable && (
                <Button onClick={() => setConnectionEditor("new")}>
                  Add Connection
                </Button>
              )}
            </div>
            {visibleConnections.length === 0 && (
              <Card className={revisionTable.empty}>
                {lifecycle === "ACTIVE"
                  ? "No active connections in this revision. Add a connection between two active nodes."
                  : "No connections match this lifecycle filter."}
              </Card>
            )}
            {visibleConnections.length > 0 && (
              <Card className="overflow-x-auto">
                <table className={revisionTable.table} aria-label="Connections">
                  <thead className={revisionTable.head}>
                    <tr className={revisionTable.headerRow}>
                      {[
                        "From",
                        "To",
                        "Type",
                        "Direction",
                        "Voltage",
                        "Phase",
                        "State",
                        "Actions",
                      ].map((h, index) => (
                        <th
                          key={h}
                          scope="col"
                          className={cn(
                            revisionTable.header,
                            index === 0 && "px-5",
                            h === "Actions" && "text-right",
                          )}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody
                    className={cn(
                      "text-slate-700",
                      query.loading && "opacity-60",
                    )}
                  >
                    {visibleConnections.map((c, index) => (
                      <tr
                        key={c.id}
                        tabIndex={0}
                        aria-selected={c.id === connectionEditor}
                        className={revisionRowClass(
                          index === 0,
                          c.id === connectionEditor,
                          c.lifecycle_status === "REMOVED",
                        )}
                        onClick={(event) => {
                          event.currentTarget.focus();
                          setConnectionEditor(c.id);
                        }}
                        onKeyDown={(e) => {
                          if (
                            e.target === e.currentTarget &&
                            (e.key === "Enter" || e.key === " ")
                          ) {
                            e.preventDefault();
                            setConnectionEditor(c.id);
                          }
                        }}
                      >
                        <td className={revisionTable.primaryCell}>
                          <span className="mr-2 text-xs text-slate-500 md:hidden">
                            From
                          </span>
                          <span
                            className={revisionPrimaryClass(
                              c.lifecycle_status === "REMOVED",
                            )}
                          >
                            {labels.get(c.from_node_id) ?? "Unavailable node"}
                          </span>
                        </td>
                        <td className={revisionTable.cell}>
                          <span className="mr-2 text-xs text-slate-500 md:hidden">
                            To
                          </span>
                          <span
                            className={revisionPrimaryClass(
                              c.lifecycle_status === "REMOVED",
                            )}
                          >
                            {labels.get(c.to_node_id) ?? "Unavailable node"}
                          </span>
                        </td>
                        <td className={revisionTable.cell}>
                          <span className="capitalize">
                            {c.connection_kind.toLowerCase()}
                          </span>
                        </td>
                        <td className={revisionTable.cell}>
                          {c.direction === "UNDIRECTED"
                            ? "Undirected"
                            : "Nominal from → to"}
                        </td>
                        <td className={revisionTable.cell}>
                          <span className="mr-2 text-xs text-slate-500 md:hidden">
                            Voltage
                          </span>
                          {c.nominal_voltage == null
                            ? "—"
                            : `${c.nominal_voltage} ${c.nominal_voltage_unit}`}
                        </td>
                        <td className={revisionTable.cell}>
                          <span className="mr-2 text-xs text-slate-500 md:hidden">
                            Phase
                          </span>
                          {c.phase_configuration ?? "—"}
                        </td>
                        <td className={revisionTable.cell}>
                          <ModelLifecycleState
                            removed={c.lifecycle_status === "REMOVED"}
                          />
                        </td>
                        <td className={revisionTable.actionsCell}>
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={(e) => {
                              e.stopPropagation();
                              setConnectionEditor(c.id);
                            }}
                          >
                            Open
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </section>
          {nodeEditor && (nodeEditor !== "new" || writable) && (
            <ModelSheet
              title={
                nodeEditor === "new"
                  ? "Add Electrical Node"
                  : selectedNode?.kind === "EQUIPMENT_TERMINAL"
                    ? "Terminal details"
                    : "Electrical Node details"
              }
              onClose={() => setNodeEditor(null)}
            >
              {selectedNode && (
                <>
                  <p>
                    {labels.get(selectedNode.id)} ·{" "}
                    {selectedNode.lifecycle_status}
                  </p>
                  {selectedNode.managed_by_profile && (
                    <p className="text-sm text-slate-500">
                      Application-managed terminal. Its role is controlled by
                      the owning equipment profile.
                    </p>
                  )}
                  {!selectedNode.managed_by_profile && (
                    <ModelAction
                      label={
                        selectedNode.lifecycle_status === "ACTIVE"
                          ? "Remove node"
                          : "Restore node"
                      }
                      warning={
                        selectedNode.lifecycle_status === "ACTIVE"
                          ? NODE_REMOVE_WARNING
                          : undefined
                      }
                      action={async () => {
                        await (selectedNode.lifecycle_status === "ACTIVE"
                          ? removeNode(projectId, revisionId, selectedNode.id)
                          : restoreNode(
                              projectId,
                              revisionId,
                              selectedNode.id,
                            ));
                        setNodeEditor(null);
                      }}
                    />
                  )}
                </>
              )}
              <ModelNodeEditor
                key={nodeEditor}
                row={selectedNode}
                onSaved={() => setNodeEditor(null)}
              />
            </ModelSheet>
          )}
          {connectionEditor && (connectionEditor !== "new" || writable) && (
            <ConnectionEditorSheet
              key={connectionEditor}
              row={selectedConnection}
              nodes={data.nodes}
              labels={labels}
              onClose={() => setConnectionEditor(null)}
            >
              {selectedConnection && (
                <>
                  <ModelAction
                    label={
                      selectedConnection.lifecycle_status === "ACTIVE"
                        ? "Remove connection"
                        : "Restore connection"
                    }
                    disabled={
                      selectedConnection.lifecycle_status === "REMOVED" &&
                      !(
                        active(selectedConnection.from_node_id) &&
                        active(selectedConnection.to_node_id)
                      )
                    }
                    action={async () => {
                      await (selectedConnection.lifecycle_status === "ACTIVE"
                        ? removeConnection(
                            projectId,
                            revisionId,
                            selectedConnection.id,
                          )
                        : restoreConnection(
                            projectId,
                            revisionId,
                            selectedConnection.id,
                          ));
                      setConnectionEditor(null);
                    }}
                  />
                  {selectedConnection.lifecycle_status === "REMOVED" &&
                    !(
                      active(selectedConnection.from_node_id) &&
                      active(selectedConnection.to_node_id)
                    ) && <p>Restore endpoint nodes first.</p>}
                </>
              )}
            </ConnectionEditorSheet>
          )}
        </>
      )}
    </div>
  );
}
