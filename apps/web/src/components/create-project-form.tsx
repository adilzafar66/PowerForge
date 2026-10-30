"use client";
import {
  WorkspaceFormActions,
  WorkspaceCard,
  WorkspaceFormSection,
  WorkspaceCheckboxField,
} from "@/components/ui/workspace-patterns";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

import {
  WorkspaceButton as Button,
  WorkspaceHeader,
} from "@/components/ui-c-workspace";
import { ArrowLeft, Plus } from "lucide-react";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
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
  const [dirty, setDirty] = useState(false);
  const [discard, setDiscard] = useState(false);
  useEffect(() => {
    if (!dirty) return;
    const guard = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
  const cancel = (event: React.MouseEvent) => {
    if (submitting || dirty) {
      event.preventDefault();
      if (!submitting) setDiscard(true);
    }
  };

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
    <div className="ui-c">
      <WorkspaceHeader
        title="Create Project"
        subtitle="Set up an engineering project. You can create its first revision now or later."
        actions={
          <Button asChild variant="ghost">
            <Link href="/" onClick={cancel}>
              <ArrowLeft />
              Back to Projects
            </Link>
          </Button>
        }
      />
      <div className="ui-c-content !max-w-[1100px]">
        <form
          onSubmit={onSubmit}
          onChange={() => setDirty(true)}
          className="ui-c-form ui-c-form-layout"
        >
          <div className="ui-c-stack">
            <fieldset
              disabled={!!createdProject || submitting}
              className="space-y-5"
            >
              <WorkspaceFormSection
                title="Project identity"
                description="These details identify the project across the workspace."
                bodyClassName="space-y-[17px]"
              >
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <Field id="project_number" label="Project Number" required>
                    <Input
                      id="project_number"
                      name="project_number"
                      required
                      placeholder="PF-2024-005"
                    />
                    <p className="text-xs text-muted">
                      Required. Cannot be changed after creation.
                    </p>
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
              </WorkspaceFormSection>

              <WorkspaceFormSection
                title="Scope &amp; description"
                description="Helpful context for engineers and collaborators."
                bodyClassName="space-y-[17px]"
              >
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
              </WorkspaceFormSection>

              <WorkspaceFormSection title="Project team">
                <Field id="engineer_names" label="Engineers">
                  <Input
                    id="engineer_names"
                    name="engineer_names"
                    placeholder="J. Smith, A. Patel"
                  />
                  <small className="text-[10.5px] text-muted">
                    Comma-separated names, matching the existing project API.
                  </small>
                </Field>
              </WorkspaceFormSection>
            </fieldset>
            <WorkspaceFormSection
              title="First revision"
              description="Optional. A project can exist before its engineering revisions."
              footer={
                <>
                  {createdProject && error ? (
                    <p role="status" className="text-sm">
                      Project {createdProject.project_number} was created. The
                      revision could not be created. Retry below or{" "}
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
                  <WorkspaceFormActions>
                    <Button asChild variant="outline">
                      <Link href="/" onClick={cancel}>
                        Cancel
                      </Link>
                    </Button>
                    <Button
                      type="submit"
                      variant="primary"
                      pending={submitting}
                    >
                      <Plus />
                      {submitting
                        ? "Creating…"
                        : createdProject
                          ? createRevisionToo
                            ? "Retry revision"
                            : "Open saved project"
                          : "Create Project"}
                    </Button>
                  </WorkspaceFormActions>
                </>
              }
            >
              <WorkspaceCheckboxField
                label="Also create the first revision"
                description="A revision is created as Draft and may be activated immediately."
                aria-label="Also create the first revision"
                checked={createRevisionToo}
                onChange={(event) => setCreateRevisionToo(event.target.checked)}
                className="rounded border-slate-300"
              />
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
                    <Input
                      id="revision_description"
                      name="revision_description"
                    />
                  </Field>
                  <WorkspaceCheckboxField
                    label="Activate this revision"
                    description="If unchecked, the revision is created as Draft."
                    checked={activateRevision}
                    onChange={(event) =>
                      setActivateRevision(event.target.checked)
                    }
                    className="rounded border-slate-300"
                  />
                </div>
              ) : null}
            </WorkspaceFormSection>
          </div>
          <aside className="ui-c-form-aside">
            <div className="ui-c-tip">
              <h3>Project creation</h3>
              <p>
                The project number and name are required. Other fields can be
                entered later.
              </p>
              <p>
                Creating the first revision is optional and is a separate
                backend operation.
              </p>
            </div>
            <WorkspaceCard as="div" className="ui-c-tip !mt-[14px] !bg-white">
              <h3>What comes next?</h3>
              <p>
                After creation, open the project to manage revisions, documents,
                and the engineering model.
              </p>
              <p>Project metadata can be edited from its Overview page.</p>
            </WorkspaceCard>
          </aside>
        </form>
      </div>
      {discard && (
        <ConfirmDialog
          className="ui-c-dialog"
          title="Discard project details?"
          message={
            createdProject
              ? "The project was already saved. Unsaved first-revision changes will be discarded."
              : "Your unsaved project details will be lost."
          }
          confirmLabel="Discard changes"
          onCancel={() => setDiscard(false)}
          onConfirm={() => {
            setDirty(false);
            router.push("/");
          }}
        />
      )}
    </div>
  );
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}
