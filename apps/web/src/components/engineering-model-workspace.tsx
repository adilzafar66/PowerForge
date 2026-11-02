"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { EquipmentWorkspace } from "@/components/equipment-workspace";
import { TopologyWorkspace } from "@/components/topology-workspace";
import {
  LoadState,
  ModelContext,
  ModelNotice,
} from "@/components/model-shared";
import { apiErrorOf } from "@/lib/api";
import { isReadOnlyErrorCode } from "@/lib/documents";
import { getEngineeringRegistry } from "@/lib/engineering-model";
import { useQueryClient } from "@tanstack/react-query";
import { useResource } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";

export function EngineeringModelWorkspace({
  projectId,
  revisionId,
  revisionLabel,
  canMutate,
  readOnlyReason,
  active,
}: {
  projectId: string;
  revisionId: string;
  revisionLabel?: string;
  canMutate: boolean;
  readOnlyReason?: string | null;
  active: boolean;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const registry = useResource(keys.registry, getEngineeringRegistry, active);
  const params = useSearchParams();
  const view = params.get("view") === "topology" ? "topology" : "equipment";
  const [locked, setLocked] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const changed = useCallback(() => {
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
      if (status === 404 || status === 409)
        void client.invalidateQueries({
          queryKey: keys.model(projectId, revisionId),
        });
    },
    [router, client, projectId, revisionId],
  );
  const toast = view === "equipment" && message === "Saved.";
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setMessage(null), 2600);
    return () => clearTimeout(timer);
  }, [toast, message]);
  if (!registry.data) return <LoadState {...registry} />;
  return (
    <ModelContext.Provider
      value={{
        projectId,
        revisionId,
        revisionLabel,
        registry: registry.data,
        writable: canMutate && !locked,
        changed,
        failed,
      }}
    >
      <LoadState {...registry} />
      {message &&
        view !== "topology" &&
        (message === "Saved." ? (
          toast ? (
            <p
              role="status"
              className="fixed right-6 bottom-6 z-[90] m-0 rounded-[var(--pf-radius-md)] bg-ink px-[18px] py-3 text-workspace-caption text-white shadow-workspace-toast animate-[workspace-appear_var(--pf-motion-feedback)_ease-out] motion-reduce:animate-none"
            >
              Changes saved.
            </p>
          ) : (
            <p role="status" className="my-3 text-sm text-positive">
              {message}
            </p>
          )
        ) : (
          <ModelNotice>{message}</ModelNotice>
        ))}
      {locked && view !== "topology" && (
        <p role="status" className="mb-3 text-sm text-amber-800">
          This revision is read-only. Further edits are unavailable.
        </p>
      )}
      <div hidden={view !== "equipment"}>
        <EquipmentWorkspace active={active && view === "equipment"} />
      </div>
      {view === "topology" && active && (
        <TopologyWorkspace
          readOnlyReason={
            locked
              ? "This revision is read-only. Further edits are unavailable."
              : readOnlyReason
          }
        />
      )}
    </ModelContext.Provider>
  );
}
