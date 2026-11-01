import { notFound } from "next/navigation";
import { ServerState } from "@/components/server-state";
import { DocumentViewerPage } from "@/components/document-viewer";
import { apiErrorOf } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { getProject, getRevision, listRevisions } from "@/lib/projects";
export const dynamic = "force-dynamic";
export default async function DocumentViewerRoute({
  params,
}: {
  params: Promise<{ projectId: string; revisionId: string; documentId: string }>;
}) {
  const { projectId: p, revisionId: r, documentId: d } = await params;
  try {
    const [project, revision, revisions] = await Promise.all([
      getProject(p, true),
      getRevision(p, r, true),
      listRevisions(p, true),
    ]);
    return (
      <ServerState
        entries={[
          [keys.project(p), project],
          [keys.revision(p, r), revision],
          [keys.revisions(p), revisions],
        ]}
      >
        <DocumentViewerPage
          key={`${r}:${d}`}
          initialProject={project}
          initialRevision={revision}
          initialRevisions={revisions}
          documentId={d}
        />
      </ServerState>
    );
  } catch (error) {
    if (apiErrorOf(error).status === 404) notFound();
    throw error;
  }
}
