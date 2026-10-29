"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { RevisionDocuments } from "@/components/revision-documents";
import { EngineeringModelWorkspace } from "@/components/engineering-model-workspace";
import { SegmentedControl } from "@/components/ui/segmented-control";

export function RevisionWorkspace(props: {
  projectId: string;
  revisionId: string;
  canMutate: boolean;
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
      next.delete("equipment");
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
      {!model && <RevisionDocuments {...props} />}
      {(visited || model) && (
        <div hidden={!model}>
          <EngineeringModelWorkspace
            key={`${props.projectId}:${props.revisionId}`}
            {...props}
            active={model}
          />
        </div>
      )}
    </>
  );
}
