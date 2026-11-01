"use client";
import { WorkspaceNote } from "@/components/ui/workspace-layout";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { WorkspaceEditor } from "@/components/workspace-editor";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { keys } from "@/lib/query-keys";
import {
  updateRevision,
  type Project,
  type Revision,
  type RevisionUpdateInput,
} from "@/lib/projects";
// Check the decimal's syntax and sign without ever rounding it through Number.
export function positiveDecimal(value: string) {
  return (
    /^\+?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/.test(value) &&
    /[1-9]/.test(value.split(/[eE]/)[0])
  );
}
export function RevisionEditor({
  project,
  revision,
  onClose,
  onSaved,
}: {
  project: Project;
  revision: Revision;
  onClose: () => void;
  onSaved: () => void;
}) {
  const client = useQueryClient();
  const [baseline] = useState(() => ({
    identifier: revision.identifier,
    description: revision.description ?? "",
    system_frequency:
      revision.system_frequency == null
        ? ""
        : String(revision.system_frequency),
    system_phase_count:
      revision.system_phase_count == null
        ? ""
        : String(revision.system_phase_count),
  }));
  const [draft, setDraft] = useState(baseline);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const locked =
    project.status === "ARCHIVED" || project.status === "CANCELLED";
  const settingsLocked = locked || revision.status === "SUPERSEDED";
  const frequency = draft.system_frequency.trim();
  const invalidFrequency = frequency !== "" && !positiveDecimal(frequency);
  const dirty = JSON.stringify(draft) !== JSON.stringify(baseline);
  const settingsChanged =
    draft.system_frequency !== baseline.system_frequency ||
    draft.system_phase_count !== baseline.system_phase_count;
  async function save() {
    const input: RevisionUpdateInput = {};
    if (draft.identifier !== baseline.identifier)
      input.identifier = draft.identifier.trim();
    if (draft.description !== baseline.description)
      input.description = draft.description.trim() || null;
    if (draft.system_frequency !== baseline.system_frequency)
      input.system_frequency = frequency || null;
    if (draft.system_phase_count !== baseline.system_phase_count)
      input.system_phase_count =
        draft.system_phase_count === "1"
          ? 1
          : draft.system_phase_count === "3"
            ? 3
            : null;
    setPending(true);
    setError(null);
    try {
      const updated = await updateRevision(project.id, revision.id, input);
      client.setQueryData(keys.revision(project.id, revision.id), updated);
      client.setQueryData<Revision[]>(keys.revisions(project.id), (items) =>
        items?.map((item) =>
          item.id === updated.id
            ? updated
            : item.based_on_revision_id === updated.id
              ? { ...item, based_on_identifier: updated.identifier }
              : item,
        ),
      );
      // Other mounted labels and ancestry come from the authoritative refreshed queries.
      void client.invalidateQueries({ queryKey: keys.revisions(project.id) });
      void client.invalidateQueries({ queryKey: ["revision", project.id] });
      void client.invalidateQueries({ queryKey: keys.project(project.id) });
      void client.invalidateQueries({ queryKey: keys.projects });
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save revision.");
    } finally {
      setPending(false);
    }
  }
  return (
    <WorkspaceEditor
      presentation="revision"
      title="Edit revision"
      subtitle={`Update metadata for ${revision.identifier}`}
      dirty={dirty}
      pending={pending}
      disabled={
        locked ||
        !draft.identifier.trim() ||
        invalidFrequency ||
        (settingsLocked && settingsChanged)
      }
      error={error}
      onClose={onClose}
      onSave={() => void save()}
    >
      {locked && <p role="status">This project is read-only.</p>}
      <div className="text-workspace-caption uppercase tracking-[var(--pf-tracking-overline)] text-[var(--pf-text-tertiary)] font-bold pt-3 border-t border-border !border-0 !pt-0">
        Revision information
      </div>
      <Field
        id="revision-identifier"
        label="Revision Identifier"
        required
        presentation="workspace"
      >
        <Input
          id="revision-identifier"
          required
          maxLength={128}
          disabled={locked}
          value={draft.identifier}
          onChange={(e) => setDraft({ ...draft, identifier: e.target.value })}
          presentation="workspace"
        />
        <small className="text-[11px] text-muted">
          Must be unique within the project. Changing this label does not create
          a new revision.
        </small>
      </Field>
      <Field
        id="revision-description"
        label="Description"
        presentation="workspace"
      >
        <Textarea
          id="revision-description"
          disabled={locked}
          value={draft.description}
          onChange={(e) => setDraft({ ...draft, description: e.target.value })}
          presentation="workspace-editor"
        />
        <small className="text-[11px] text-muted">
          A short summary of the work, scope or design changes.
        </small>
      </Field>
      <div className="text-workspace-caption uppercase tracking-[var(--pf-tracking-overline)] text-[var(--pf-text-tertiary)] font-bold pt-3 border-t border-border">
        System-wide engineering metadata
      </div>
      <p className="bg-[var(--pf-editor-hint-surface)] border border-border rounded-[var(--pf-radius-md)] py-[13px] px-[14px] text-muted text-workspace-hint leading-[var(--pf-leading-relaxed)]">
        <strong>Manual fields only.</strong> Frequency and phase count are
        optional model-level settings. AI extraction does not populate or change
        them. Equipment-specific phase attributes remain separate.
      </p>
      {revision.status === "SUPERSEDED" && (
        <p className="text-sm text-muted">
          Historical engineering settings are read-only. Identifier and
          description may still be edited.
        </p>
      )}
      <div className="grid grid-cols-[repeat(2,_minmax(0,_1fr))] gap-[18px] max-[790px]:grid-cols-[1fr]">
        <Field
          id="revision-frequency"
          label="System frequency (Hz)"
          presentation="workspace"
        >
          <Input
            id="revision-frequency"
            inputMode="decimal"
            placeholder="e.g. 60"
            disabled={settingsLocked}
            value={draft.system_frequency}
            aria-invalid={invalidFrequency}
            onChange={(e) =>
              setDraft({ ...draft, system_frequency: e.target.value })
            }
            presentation="workspace"
          />
          <small className="text-[11px] text-muted">
            Positive decimal value; leave blank for unset.
          </small>
          {invalidFrequency && (
            <p role="alert" className="text-sm text-red-600">
              Enter a positive, finite decimal value.
            </p>
          )}
        </Field>
        <Field
          id="revision-phase"
          label="System phase count"
          presentation="workspace"
        >
          <Select
            id="revision-phase"
            value={draft.system_phase_count}
            disabled={settingsLocked}
            onValueChange={(value) =>
              setDraft({ ...draft, system_phase_count: value })
            }
            presentation="workspace"
          >
            <option value="">Not set</option>
            <option value="1">1 phase</option>
            <option value="3">3 phases</option>
          </Select>
          <small className="text-[11px] text-muted">
            Optional common assumption.
          </small>
        </Field>
      </div>
      <WorkspaceNote>
        <strong className="text-ink">Unchanged by this edit:</strong>{" "}
        revision lifecycle status, creation date, source revision, and
        carry-forward history. Activation has its own confirmation workflow.
      </WorkspaceNote>
    </WorkspaceEditor>
  );
}
