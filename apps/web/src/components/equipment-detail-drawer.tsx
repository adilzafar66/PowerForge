"use client";

import { useEffect, useRef, useState } from "react";
import { EquipmentGeneralPanel } from "@/components/equipment-general-panel";
import { EquipmentAttributesPanel } from "@/components/equipment-attributes-panel";
import { EquipmentTerminalsPanel } from "@/components/equipment-terminals-panel";
import {
  EQUIPMENT_REMOVE_WARNING,
  ModelAction,
  ModelNotice,
  ModelSheet,
  useModel,
} from "@/components/model-shared";
import { Button } from "@/components/ui/button";
import { Chip } from "@/components/ui/chip";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { apiErrorOf } from "@/lib/api";
import {
  equipmentLabel,
  getEquipment,
  removeEquipment,
  restoreEquipment,
  typeLabel,
  type Equipment,
} from "@/lib/engineering-model";

export function EquipmentDetailDrawer({
  id,
  onClose,
}: {
  id: string;
  onClose: () => void;
}) {
  const { projectId, revisionId, registry, version, failed } = useModel();
  const [row, setRow] = useState<Equipment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState("general");
  const [retry, setRetry] = useState(0);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const failedRef = useRef(failed);
  failedRef.current = failed;
  useEffect(() => {
    let current = true;
    setError(null);
    getEquipment(projectId, revisionId, id)
      .then((value) => {
        if (current) setRow(value);
      })
      .catch((err) => {
        if (!current) return;
        if (apiErrorOf(err).status === 404) {
          closeRef.current();
          failedRef.current(err);
        } else setError(apiErrorOf(err).detail);
      });
    return () => {
      current = false;
    };
  }, [projectId, revisionId, id, version, retry]);
  return (
    <ModelSheet
      title={row ? equipmentLabel(row, registry) : "Equipment details"}
      onClose={onClose}
    >
      {error && (
        <ModelNotice>
          {error} <Button onClick={() => setRetry((v) => v + 1)}>Retry</Button>
        </ModelNotice>
      )}
      {!row && !error && <p role="status">Loading equipment…</p>}
      {row && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <span>{typeLabel(registry, row.equipment_type)}</span>
            <Chip>
              {row.lifecycle_status === "ACTIVE" ? "Active" : "Removed"}
            </Chip>
            <ModelAction
              label={
                row.lifecycle_status === "ACTIVE"
                  ? "Remove equipment"
                  : "Restore equipment"
              }
              warning={
                row.lifecycle_status === "ACTIVE"
                  ? EQUIPMENT_REMOVE_WARNING
                  : undefined
              }
              action={() =>
                row.lifecycle_status === "ACTIVE"
                  ? removeEquipment(projectId, revisionId, id)
                  : restoreEquipment(projectId, revisionId, id)
              }
            />
          </div>
          <p className="text-xs text-slate-500">
            Origin: {row.origin} · Verification: {row.verification_state}
          </p>
          <SegmentedControl
            label="Equipment detail"
            value={tab}
            onChange={setTab}
            options={[
              { value: "general", label: "General" },
              { value: "attributes", label: "Attributes" },
              { value: "terminals", label: "Terminals" },
            ]}
          />
          {tab === "general" && (
            <EquipmentGeneralPanel
              key={`${row.id}:${row.updated_at}`}
              row={row}
              onSaved={setRow}
            />
          )}
          {tab === "attributes" && <EquipmentAttributesPanel row={row} />}
          {tab === "terminals" && <EquipmentTerminalsPanel row={row} />}
        </>
      )}
    </ModelSheet>
  );
}
