import { AppShell } from "@/components/app-shell";
import { ProjectList } from "@/components/project-list";
import { listProjects, type Project } from "@/lib/projects";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  let projects: Project[] = [];
  try {
    projects = await listProjects({ server: true });
  } catch {
    projects = [];
  }

  return (
    <AppShell active="projects">
      <ProjectList initialProjects={projects} />
    </AppShell>
  );
}
