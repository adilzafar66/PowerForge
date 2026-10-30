"use client";

import { Checkbox } from "@/components/ui/checkbox";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { SectionHeader } from "@/components/ui/section-header";
import {
  createProject,
  createRevision,
  parseEngineerNames,
  type Project,
} from "@/lib/projects";

export function CreateProjectForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createRevisionToo, setCreateRevisionToo] = useState(false);
  const [revisionIdentifier, setRevisionIdentifier] = useState("0");
  const [activateRevision, setActivateRevision] = useState(true);
  const [createdProject, setCreatedProject] = useState<Project | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    const form = new FormData(event.currentTarget);
    try {
      const project =
        createdProject ??
        (await createProject({
          project_number: String(form.get("project_number") ?? ""),
          project_name: String(form.get("project_name") ?? ""),
          client_name: emptyToNull(String(form.get("client_name") ?? "")),
          project_address: emptyToNull(
            String(form.get("project_address") ?? ""),
          ),
          project_scope: emptyToNull(String(form.get("project_scope") ?? "")),
          description: emptyToNull(String(form.get("description") ?? "")),
          engineer_names: parseEngineerNames(
            String(form.get("engineer_names") ?? ""),
          ),
        }));
      setCreatedProject(project);
      if (createRevisionToo && revisionIdentifier.trim()) {
        await createRevision(project.id, {
          identifier: revisionIdentifier.trim(),
          description: emptyToNull(
            String(form.get("revision_description") ?? ""),
          ),
          activate: activateRevision,
        });
      }
      router.push(`/projects/${project.id}`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create project");
      setSubmitting(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-6 md:px-8 md:py-8">
      <PageHeader
        title="Create Project"
        description="Project number and name are required. A revision is optional."
        className="mb-7"
      />

      <form onSubmit={onSubmit} className="space-y-5">
        <fieldset disabled={!!createdProject} className="space-y-5">
          <Card className="p-5">
            <SectionHeader>Identity</SectionHeader>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <Field id="project_number" label="Project Number" required>
                  <Input
                    id="project_number"
                    name="project_number"
                    required
                    placeholder="PF-2024-005"
                  />
                </Field>
                <Field id="project_name" label="Project Name" required>
                  <Input
                    id="project_name"
                    name="project_name"
                    required
                    placeholder="Ridgeline Substation"
                  />
                </Field>
              </div>
              <Field id="client_name" label="Client / Owner">
                <Input
                  id="client_name"
                  name="client_name"
                  placeholder="Acme Energy LLC"
                />
              </Field>
              <Field id="project_address" label="Site Address">
                <Input
                  id="project_address"
                  name="project_address"
                  placeholder="123 Power Line Rd, Phoenix, AZ 85001"
                />
              </Field>
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader>Scope & Description</SectionHeader>
            <div className="space-y-4">
              <Field id="project_scope" label="Scope Summary">
                <Textarea
                  id="project_scope"
                  name="project_scope"
                  rows={2}
                  placeholder="One-paragraph description of the electrical scope of work."
                />
              </Field>
              <Field id="description" label="Project Description">
                <Textarea
                  id="description"
                  name="description"
                  rows={3}
                  placeholder="Additional context, background, or technical notes."
                />
              </Field>
            </div>
          </Card>

          <Card className="p-5">
            <SectionHeader>Team</SectionHeader>
            <Field id="engineer_names" label="Engineers (comma-separated)">
              <Input
                id="engineer_names"
                name="engineer_names"
                placeholder="J. Smith, A. Patel"
              />
            </Field>
          </Card>
        </fieldset>
        <Card className="p-5">
          <SectionHeader>First Revision</SectionHeader>
          <label className="flex items-center gap-2 text-[13.5px] text-slate-700">
            <Checkbox
              checked={createRevisionToo}
              onChange={(event) => setCreateRevisionToo(event.target.checked)}
              className="rounded border-slate-300"
            />
            Also create the first revision
          </label>
          {createRevisionToo ? (
            <div className="mt-4 space-y-4 border-t border-slate-100 pt-4">
              <Field
                id="revision_identifier"
                label="Revision Identifier"
                required
              >
                <Input
                  id="revision_identifier"
                  value={revisionIdentifier}
                  onChange={(event) =>
                    setRevisionIdentifier(event.target.value)
                  }
                  required={createRevisionToo}
                />
              </Field>
              <Field id="revision_description" label="Revision Description">
                <Input id="revision_description" name="revision_description" />
              </Field>
              <label className="flex items-center gap-2 text-[13.5px] text-slate-700">
                <Checkbox
                  checked={activateRevision}
                  onChange={(event) =>
                    setActivateRevision(event.target.checked)
                  }
                  className="rounded border-slate-300"
                />
                Activate this revision
              </label>
            </div>
          ) : null}
        </Card>

        {createdProject && error ? (
          <p role="status" className="text-sm">
            Project {createdProject.project_number} was created. The revision
            could not be created. Retry below or{" "}
            <Link
              className="text-accent underline"
              href={`/projects/${createdProject.id}`}
            >
              open the saved project
            </Link>
            .
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="text-[13px] text-red-600">
            {error}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-2 pt-1">
          <Button asChild variant="outline">
            <Link href="/">Cancel</Link>
          </Button>
          <Button type="submit" pending={submitting}>
            {submitting
              ? "Creating…"
              : createdProject
                ? createRevisionToo
                  ? "Retry revision"
                  : "Open saved project"
                : "Create Project"}
          </Button>
        </div>
      </form>
    </div>
  );
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}
