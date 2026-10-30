"use client";
import { workspaceStyles as ws } from "@/components/ui/workspace-styles";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WorkspaceEditor } from "@/components/workspace-editor";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { keys } from "@/lib/query-keys";
import {
  updateProject,
  parseEngineerNames,
  type Project,
  type ProjectUpdateInput,
} from "@/lib/projects";

export function ProjectEditor({
  project,
  onClose,
  onSaved,
}: {
  project: Project;
  onClose: () => void;
  onSaved: () => void;
}) {
  const client = useQueryClient();
  const [baseline] = useState(() => ({
    project_name: project.project_name,
    client_name: project.client_name ?? "",
    project_address: project.project_address ?? "",
    project_scope: project.project_scope ?? "",
    description: project.description ?? "",
    engineer_names: project.engineer_names.join(", "),
  }));
  const [draft, setDraft] = useState(baseline);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const locked =
    project.status === "ARCHIVED" || project.status === "CANCELLED";
  async function save() {
    setPending(true);
    setError(null);
    const input: ProjectUpdateInput = {};
    for (const key of Object.keys(draft) as (keyof typeof draft)[]) {
      if (draft[key] === baseline[key]) continue;
      if (key === "engineer_names") input[key] = parseEngineerNames(draft[key]);
      else if (key === "project_name") input[key] = draft[key].trim();
      else input[key] = draft[key].trim() || null;
    }
    try {
      const updated = await updateProject(project.id, input);
      client.setQueryData(keys.project(project.id), updated);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save project.");
    } finally {
      setPending(false);
    }
  }
  return (
    <WorkspaceEditor
      title="Edit project"
      subtitle={`${project.project_number} · ${project.project_name}`}
      dirty={dirty}
      pending={pending}
      disabled={locked || !draft.project_name.trim()}
      error={error}
      onClose={onClose}
      onSave={() => void save()}
    >
      <p className={ws.editHint}>
        <strong>Project number {project.project_number} is fixed.</strong>
        <br />
        Edit the project information below. Status and revisions are managed
        separately.
      </p>
      {locked && <p role="status">This project is read-only.</p>}
      {(
        Object.entries({
          project_name: "Project Name",
          client_name: "Client / Owner",
          project_address: "Site Address",
          project_scope: "Scope Summary",
          description: "Description",
          engineer_names: "Engineers (comma-separated)",
        }) as [keyof typeof draft, string][]
      ).map(([key, label]) => {
        const Control =
          key === "description" || key === "project_scope" ? Textarea : Input;
        return (
          <Field
            key={key}
            id={`edit-${key}`}
            label={label}
            required={key === "project_name"}
          >
            <Control
              id={`edit-${key}`}
              value={draft[key]}
              required={key === "project_name"}
              disabled={locked}
              onChange={(event) =>
                setDraft({ ...draft, [key]: event.target.value })
              }
            />
          </Field>
        );
      })}
    </WorkspaceEditor>
  );
}
