"use client";

import { useCallback, useState } from "react";
import { useRouter, usePathname, useSearchParams } from "next/navigation";
import { EquipmentWorkspace } from "@/components/equipment-workspace";
import { TopologyWorkspace } from "@/components/topology-workspace";
import {
  LoadState,
  ModelContext,
  ModelNotice,
  useModelQuery,
} from "@/components/model-shared";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { apiErrorOf } from "@/lib/api";
import { isReadOnlyErrorCode } from "@/lib/documents";
import { getEngineeringRegistry } from "@/lib/engineering-model";

export function EngineeringModelWorkspace({
  projectId,
  revisionId,
  canMutate,
  active,
}: {
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  active: boolean;
}) {
  const router = useRouter();
  const registry = useModelQuery(getEngineeringRegistry);
  const params = useSearchParams();
  const path = usePathname();
  const view = params.get("view") === "topology" ? "topology" : "equipment";
  function setView(value: string) {
    const next = new URLSearchParams(params.toString());
    next.set("workspace", "model");
    next.set("view", value);
    if (value === "topology") next.delete("equipment");
    router.replace(`${path}?${next}`, { scroll: false });
  }
  const [locked, setLocked] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [version, setVersion] = useState(0);
  const changed = useCallback(() => {
    setVersion((v) => v + 1);
    setMessage("Saved.");
  }, []);
  const failed = useCallback(
    (error: unknown) => {
      const { code, status, detail } = apiErrorOf(error);
      setMessage(detail);
      if (isReadOnlyErrorCode(code)) {
        setLocked(true);
        router.refresh();
      }
      if (status === 404 || status === 409) setVersion((v) => v + 1);
    },
    [router],
  );
  if (!registry.data) return <LoadState {...registry} />;
  return (
    <ModelContext.Provider
      value={{
        projectId,
        revisionId,
        registry: registry.data,
        writable: canMutate && !locked,
        version,
        changed,
        failed,
      }}
    >
      <SegmentedControl
        label="Engineering Model view"
        className="mb-4 w-fit"
        value={view}
        onChange={setView}
        options={[
          { value: "equipment", label: "Equipment" },
          { value: "topology", label: "Topology" },
        ]}
      />
      {message && <ModelNotice>{message}</ModelNotice>}
      {locked && (
        <p role="status" className="mb-3 text-sm text-amber-800">
          This revision is read-only. Further edits are unavailable.
        </p>
      )}
      <div hidden={view !== "equipment"}>
        <EquipmentWorkspace active={active && view === "equipment"} />
      </div>
      {view === "topology" && active && <TopologyWorkspace />}
    </ModelContext.Provider>
  );
}
