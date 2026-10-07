import { Lock } from "lucide-react";

import { readOnlyReason } from "@/lib/documents";
import type { Project, Revision } from "@/lib/projects";

export function ReadOnlyBanner({
  project,
  revision,
}: {
  project: Pick<Project, "status">;
  revision: Pick<Revision, "status">;
}) {
  const reason = readOnlyReason({ project, revision });
  if (!reason) {
    return null;
  }
  return (
    <div
      role="status"
      className="mb-5 flex items-start gap-2.5 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800"
    >
      <Lock className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.8} />
      <p>
        <span className="font-semibold">Read-only.</span> {reason} Documents can still be viewed,
        filtered and downloaded.
      </p>
    </div>
  );
}
