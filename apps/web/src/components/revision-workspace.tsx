"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { RevisionDocuments } from "@/components/revision-documents";
import { EngineeringModelWorkspace } from "@/components/engineering-model-workspace";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { clearEquipment } from "@/lib/workspace-navigation";

/** Equipment owns its full page header; navigation reaches it from the shell. */
export function isEquipmentView(params: URLSearchParams) {
  return (
    params.get("workspace") === "model" &&
    params.get("view") !== "topology" &&
    params.get("view") !== "overview"
  );
}

/** Documents owns its page header; navigation reaches it from the shell. */
export function isDocumentsView(params: URLSearchParams) {
  return (
    params.get("workspace") !== "model" && params.get("view") !== "overview"
  );
}

export function isTopologyView(params: URLSearchParams) {
  return (
    params.get("workspace") === "model" && params.get("view") === "topology"
  );
}

export function RevisionWorkspace({
  readOnlyReason,
  activeRevisionId,
  ...props
}: {
  projectId: string;
  revisionId: string;
  canMutate: boolean;
  revisionLabel?: string;
  readOnlyReason?: string | null;
  activeRevisionId?: string | null;
}) {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  const overview = params.get("view") === "overview";
  const model = params.get("workspace") === "model";
  const [visited, setVisited] = useState(model);
  function change(value: string) {
    const next = new URLSearchParams(params.toString());
    next.delete("view");
    if (value === "model") {
      setVisited(true);
      next.set("workspace", "model");
      next.delete("document");
    } else {
      next.delete("workspace");
      clearEquipment(next);
    }
    router.replace(`${path}${next.size ? `?${next}` : ""}`, { scroll: false });
  }
  if (overview)
    return (
      <p className="text-sm text-muted">
        Use Documents, Equipment, or Topology in the navigation to open this
        revision’s workspace.
      </p>
    );
  return (
    <>
      {model && !isEquipmentView(params) && !isTopologyView(params) && (
        <SegmentedControl
          label="Revision workspace"
          className="mb-5 w-fit"
          value={model ? "model" : "documents"}
          onChange={change}
          options={[
            { value: "documents", label: "Documents" },
            { value: "model", label: "Engineering Model" },
          ]}
        />
      )}
      {!model && (
        <RevisionDocuments
          projectId={props.projectId}
          revisionId={props.revisionId}
          canMutate={props.canMutate}
          revisionLabel={props.revisionLabel}
          readOnlyReason={readOnlyReason}
          activeRevisionId={activeRevisionId}
        />
      )}
      {(visited || model) && (
        <div hidden={!model}>
          <EngineeringModelWorkspace
            key={`${props.projectId}:${props.revisionId}`}
            {...props}
            readOnlyReason={readOnlyReason}
            active={model}
          />
        </div>
      )}
    </>
  );
}
