import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ProjectDetail } from "@/components/project-detail";
import { getProject, listRevisions } from "@/lib/projects";

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
      <AppShell active="projects">
        <ProjectDetail initialProject={project} initialRevisions={revisions} />
      </AppShell>
    );
  } catch {
    notFound();
  }
}
