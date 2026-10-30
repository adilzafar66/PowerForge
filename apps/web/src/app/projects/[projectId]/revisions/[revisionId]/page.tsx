import { notFound } from "next/navigation";
import { ServerState } from "@/components/server-state";
import { RevisionPageContent } from "@/components/revision-page-content";
import { apiErrorOf } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { getProject, getRevision, listRevisions } from "@/lib/projects";
export const dynamic = "force-dynamic";
export default async function RevisionPage({
  params,
}: {
  params: Promise<{ projectId: string; revisionId: string }>;
}) {
  const { projectId: p, revisionId: r } = await params;
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
        <RevisionPageContent
          key={r}
          initialProject={project}
          initialRevision={revision}
          initialRevisions={revisions}
        />
      </ServerState>
    );
  } catch (error) {
    if (apiErrorOf(error).status === 404) notFound();
    throw error;
  }
}
