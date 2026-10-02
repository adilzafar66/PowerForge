import { AppShell } from "@/components/app-shell";
import { CreateProjectForm } from "@/components/create-project-form";

export const dynamic = "force-dynamic";

export default function NewProjectPage() {
  return (
    <AppShell active="projects">
      <CreateProjectForm />
    </AppShell>
  );
}
