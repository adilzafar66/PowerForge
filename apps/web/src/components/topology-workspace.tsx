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
            {data.nodes.filter(visible).map((n) => (
              <Card
                key={n.id}
                className="flex flex-wrap items-center justify-between gap-3 p-4"
              >
                <div>
                  <p className="font-medium">{labels.get(n.id)}</p>
                  <p className="text-xs text-slate-500">
                    {n.kind === "ELECTRICAL_NODE"
                      ? "Electrical node"
                      : "Equipment terminal"}{" "}
                    · {n.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
                  </p>
                </div>
                {writable && n.kind === "ELECTRICAL_NODE" && (
                  <div className="flex gap-2">
                    {n.lifecycle_status === "ACTIVE" && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setNodeEditor(n.id)}
                      >
                        Edit node
                      </Button>
                    )}
                    <ModelAction
                      label={
                        n.lifecycle_status === "ACTIVE"
                          ? "Remove node"
                          : "Restore node"
                      }
                      warning={
                        n.lifecycle_status === "ACTIVE"
                          ? NODE_REMOVE_WARNING
                          : undefined
                      }
                      action={() =>
                        n.lifecycle_status === "ACTIVE"
                          ? removeNode(projectId, revisionId, n.id)
                          : restoreNode(projectId, revisionId, n.id)
                      }
                    />
                  </div>
                )}
              </Card>
            ))}
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
            {data.connections.filter(visible).map((c) => (
              <Card
                key={c.id}
                className={`grid gap-3 p-4 text-sm md:grid-cols-4 ${c.lifecycle_status === "REMOVED" ? "text-slate-400" : "text-slate-700"}`}
              >
                <div>
                  <span className="text-xs text-slate-400">From</span>
                  <p>{labels.get(c.from_node_id) ?? "Unavailable node"}</p>
                  <span className="text-xs text-slate-400">To</span>
                  <p>{labels.get(c.to_node_id) ?? "Unavailable node"}</p>
                </div>
                <div>
                  {c.connection_kind}
                  <p>
                    {c.direction === "UNDIRECTED"
                      ? "Undirected"
                      : "Nominal from → to"}
                  </p>
                </div>
                <div>
                  {c.nominal_voltage == null
                    ? "No voltage specified"
                    : `${c.nominal_voltage} ${c.nominal_voltage_unit}`}
                  <p>{c.phase_configuration || "No phase configuration"}</p>
                  <p>
                    {c.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
                  </p>
                </div>
                {writable && (
                  <div className="flex flex-wrap items-start gap-2">
                    {c.lifecycle_status === "ACTIVE" && (
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setConnectionEditor(c.id)}
                      >
                        Edit connection
                      </Button>
                    )}
                    <ModelAction
                      label={
                        c.lifecycle_status === "ACTIVE"
                          ? "Remove connection"
                          : "Restore connection"
                      }
                      disabled={
                        c.lifecycle_status === "REMOVED" &&
                        !(active(c.from_node_id) && active(c.to_node_id))
                      }
                      action={() =>
                        c.lifecycle_status === "ACTIVE"
                          ? removeConnection(projectId, revisionId, c.id)
                          : restoreConnection(projectId, revisionId, c.id)
                      }
                    />
                    {c.lifecycle_status === "REMOVED" &&
                      !(active(c.from_node_id) && active(c.to_node_id)) && (
                        <p className="text-xs">Restore endpoint nodes first.</p>
                      )}
                  </div>
                )}
              </Card>
            ))}
          </section>
          {writable &&
            nodeEditor &&
            (nodeEditor === "new" ||
              selectedNode?.lifecycle_status === "ACTIVE") && (
              <ModelSheet
                title={
                  nodeEditor === "new"
                    ? "Add Electrical Node"
                    : "Edit Electrical Node"
                }
                onClose={() => setNodeEditor(null)}
              >
                <ModelNodeEditor
                  key={nodeEditor}
                  row={selectedNode}
                  onSaved={() => setNodeEditor(null)}
                />
              </ModelSheet>
            )}
          {writable &&
            connectionEditor &&
            (connectionEditor === "new" ||
              selectedConnection?.lifecycle_status === "ACTIVE") && (
              <ConnectionEditorSheet
                key={connectionEditor}
                row={selectedConnection}
                nodes={data.nodes}
                labels={labels}
                onClose={() => setConnectionEditor(null)}
              />
            )}
        </>
      )}
    </div>
  );
}
