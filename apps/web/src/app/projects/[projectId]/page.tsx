import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ProjectDetail } from "@/components/project-detail";
import { getProject, listRevisions } from "@/lib/projects";
import { ServerState } from "@/components/server-state";
import { keys } from "@/lib/query-keys";
import { apiErrorOf } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function ProjectDetailPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  try {
    const [project, revisions] = await Promise.all([
      getProject(projectId, true),
      listRevisions(projectId, true),
    ]);
    return (
      <ServerState
        entries={[
          [keys.project(projectId), project],
          [keys.revisions(projectId), revisions],
        ]}
      >
        <AppShell project={project} revisions={revisions}>
        <ProjectDetail
          key={project.id}
            initialProject={project}
            initialRevisions={revisions}
          />
        </AppShell>
      </ServerState>
    );
  } catch (error) {
    if (apiErrorOf(error).status === 404) notFound();
    throw error;
  }
}
