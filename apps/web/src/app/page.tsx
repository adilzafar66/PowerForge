import { AppShell } from "@/components/app-shell";
import { ProjectList } from "@/components/project-list";
import { listProjects, type Project } from "@/lib/projects";
import { ServerState } from "@/components/server-state";
import { keys } from "@/lib/query-keys";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let projects: Project[] | undefined;
  try {
    projects = await listProjects({ server: true });
  } catch {
    // The client query renders a recoverable load error, never a false empty dataset.
  }

  return (
    <ServerState entries={[[keys.projects, projects]]}>
      <AppShell active="projects">
        <ProjectList initialProjects={projects} />
      </AppShell>
    </ServerState>
  );
}
