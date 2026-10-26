"use client";

import { useCallback, useState } from "react";
import { ModelNodeEditor } from "@/components/model-node-editor";
import {
  LoadState,
  ModelAction,
  NODE_REMOVE_WARNING,
  useModel,
  useModelQuery,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  listNodes,
  removeNode,
  restoreNode,
  type Equipment,
} from "@/lib/engineering-model";

export function EquipmentTerminalsPanel({ row }: { row: Equipment }) {
  const { projectId, revisionId, writable, version } = useModel();
  const [editing, setEditing] = useState<string | null>(null);
  const load = useCallback(
    () => listNodes(projectId, revisionId, "ALL"),
    [projectId, revisionId],
  );
  const query = useModelQuery(load, version);
  const editable = writable && row.lifecycle_status === "ACTIVE";
  const nodes =
    query.data?.filter(
      (n) => n.kind === "EQUIPMENT_TERMINAL" && n.equipment_id === row.id,
    ) ?? [];
  return (
    <div className="space-y-4">
      <LoadState {...query} />
      {row.lifecycle_status === "REMOVED" && (
        <p className="text-sm text-slate-500">
          Restore equipment before changing its terminals.
        </p>
      )}
      {editable && (
        <Button onClick={() => setEditing(editing === "new" ? null : "new")}>
          Add Terminal
        </Button>
      )}
      {editing === "new" && editable && (
        <ModelNodeEditor
          equipmentId={row.id}
          onSaved={() => setEditing(null)}
        />
      )}
      {!query.loading && nodes.length === 0 && (
        <p className="text-sm text-slate-500">
          No terminals. Add each terminal explicitly.
        </p>
      )}
      {nodes.map((n) => (
        <Card key={n.id} className="p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span>
              {n.terminal_key}
              {n.label ? ` · ${n.label}` : ""} ·{" "}
              {n.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
            </span>
            {editable && (
              <div className="flex gap-2">
                {n.lifecycle_status === "ACTIVE" && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setEditing(editing === n.id ? null : n.id)}
                  >
                    Edit terminal
                  </Button>
                )}
                <ModelAction
                  label={
                    n.lifecycle_status === "ACTIVE"
                      ? "Remove terminal"
                      : "Restore terminal"
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
          </div>
          {editing === n.id && editable && n.lifecycle_status === "ACTIVE" && (
            <ModelNodeEditor
              key={n.updated_at}
              row={n}
              onSaved={() => setEditing(null)}
            />
          )}
        </Card>
      ))}
    </div>
  );
}
