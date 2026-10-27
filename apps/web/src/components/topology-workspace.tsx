"use client";

import { useCallback, useState } from "react";
import { ConnectionEditorSheet } from "@/components/connection-editor-sheet";
import { ModelNodeEditor } from "@/components/model-node-editor";
import {
  LifecycleControl,
  LoadState,
  ModelAction,
  ModelSheet,
  NODE_REMOVE_WARNING,
  useModel,
  useModelQuery,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
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
  const { projectId, revisionId, registry, writable, version } = useModel();
  const [lifecycle, setLifecycle] = useState<LifecycleFilter>("ACTIVE");
  const [nodeEditor, setNodeEditor] = useState<string | null>(null);
  const [connectionEditor, setConnectionEditor] = useState<string | null>(null);
  const load = useCallback(async () => {
    const [nodes, connections, equipment] = await Promise.all([
      listNodes(projectId, revisionId, "ALL"),
      listConnections(projectId, revisionId, "ALL"),
      listEquipment(projectId, revisionId, { lifecycle_status: "ALL" }),
    ]);
    return { nodes, connections, equipment };
  }, [projectId, revisionId]);
  const query = useModelQuery(load, version);
  const data = query.data;
  const labels = data
    ? nodeLabels(data.nodes, data.equipment, registry)
    : new Map<string, string>();
  const ownerLabels = new Map(
    data?.equipment.map((row) => [row.id, equipmentLabel(row, registry)]),
  );
  const visible = (row: { lifecycle_status: string }) =>
    lifecycle === "ALL" || row.lifecycle_status === lifecycle;
  const activeNodeIds = new Set(
    data?.nodes.filter((n) => n.lifecycle_status === "ACTIVE").map((n) => n.id),
  );
  const active = (id: string) => activeNodeIds.has(id);
  const selectedNode = data?.nodes.find((n) => n.id === nodeEditor);
  const selectedConnection = data?.connections.find(
    (c) => c.id === connectionEditor,
  );
  return (
    <div className="space-y-5">
      <LifecycleControl value={lifecycle} onChange={setLifecycle} />
      <LoadState {...query} />
      {data && (
        <>
          <section className="space-y-3" aria-label="Topology nodes">
            <div className="flex flex-wrap justify-between gap-3">
              <h2 className="font-semibold">Nodes</h2>
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
            {data.nodes.filter(visible).length === 0 && (
              <Card className="p-5 text-sm text-slate-500">
                No nodes match this view.
              </Card>
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm" aria-label="Nodes">
                <thead>
                  <tr>
                    {[
                      "Node",
                      "Type",
                      "Equipment / Owner",
                      "Terminal",
                      "Lifecycle",
                    ].map((h) => (
                      <th key={h} className="p-3">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.nodes.filter(visible).map((n) => (
                    <tr
                      key={n.id}
                      tabIndex={0}
                      className="cursor-pointer border-t hover:bg-slate-50 focus:bg-slate-50"
                      onClick={() => setNodeEditor(n.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setNodeEditor(n.id);
                        }
                      }}
                    >
                      <td className="p-3">
                        <button onClick={() => setNodeEditor(n.id)}>
                          {labels.get(n.id)}
                        </button>
                      </td>
                      <td className="p-3">
                        {n.kind === "ELECTRICAL_NODE"
                          ? "Electrical node"
                          : "Equipment terminal"}
                      </td>
                      <td className="p-3">
                        {n.equipment_id
                          ? (ownerLabels.get(n.equipment_id) ??
                            "Unavailable equipment")
                          : "—"}
                      </td>
                      <td className="p-3">
                        {n.terminal_key ?? "—"}
                        {n.managed_by_profile && (
                          <span className="block text-xs text-slate-500">
                            Application-managed
                          </span>
                        )}
                      </td>
                      <td className="p-3">
                        {n.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="space-y-3" aria-label="Topology connections">
            <div className="flex flex-wrap justify-between gap-3">
              <h2 className="font-semibold">Connections</h2>
              {writable && (
                <Button onClick={() => setConnectionEditor("new")}>
                  Add Connection
                </Button>
              )}
            </div>
            {data.connections.filter(visible).length === 0 && (
              <Card className="p-5 text-sm text-slate-500">
                No connections match this view.
              </Card>
            )}
            <div className="overflow-x-auto">
              <table
                className="w-full text-left text-sm"
                aria-label="Connections"
              >
                <thead>
                  <tr>
                    {[
                      "From",
                      "To",
                      "Type",
                      "Direction",
                      "Voltage",
                      "Phase",
                      "Lifecycle",
                    ].map((h) => (
                      <th key={h} className="p-3">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.connections.filter(visible).map((c) => (
                    <tr
                      key={c.id}
                      tabIndex={0}
                      className="cursor-pointer border-t hover:bg-slate-50 focus:bg-slate-50"
                      onClick={() => setConnectionEditor(c.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setConnectionEditor(c.id);
                        }
                      }}
                    >
                      <td className="p-3">
                        <button onClick={() => setConnectionEditor(c.id)}>
                          {labels.get(c.from_node_id) ?? "Unavailable node"}
                        </button>
                      </td>
                      <td className="p-3">
                        {labels.get(c.to_node_id) ?? "Unavailable node"}
                      </td>
                      <td className="p-3">{c.connection_kind}</td>
                      <td className="p-3">
                        {c.direction === "UNDIRECTED"
                          ? "Undirected"
                          : "Nominal from → to"}
                      </td>
                      <td className="p-3">
                        {c.nominal_voltage == null
                          ? "—"
                          : `${c.nominal_voltage} ${c.nominal_voltage_unit}`}
                      </td>
                      <td className="p-3">{c.phase_configuration ?? "—"}</td>
                      <td className="p-3">
                        {c.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
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
