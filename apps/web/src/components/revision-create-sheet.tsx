"use client";
import { cn } from "@/lib/utils";
import { WorkspaceDrawerBody } from "@/components/ui/workspace-patterns";
import { WorkspaceNote } from "@/components/ui/workspace-layout";
import {
  WorkspaceFormActions,
  WorkspaceDrawerHeader,
  WorkspaceCheckboxField,
} from "@/components/ui/workspace-patterns";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { Sheet } from "@/components/ui/sheet";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Select } from "@/components/ui/select";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Plus } from "lucide-react";
import {
  createRevision,
  type Project,
  type Revision,
  type RevisionCreateInput,
} from "@/lib/projects";
import { REVISION_STATUS_STYLES } from "@/lib/status-styles";
export function RevisionCreateSheet({
  project,
  revisions,
  onClose,
  setMessage,
}: {
  project: Project;
  revisions: Revision[];
  onClose: () => void;
  setMessage: (message: string) => void;
}) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmActivation, setConfirmActivation] = useState(false);
  const setProject = (value: (current: Project) => Project) =>
    client.setQueryData<Project>(keys.project(project.id), (old) =>
      value(old ?? project),
    );
  const setRevisions = (value: (current: Revision[]) => Revision[]) =>
    client.setQueryData<Revision[]>(keys.revisions(project.id), (old) =>
      value(old ?? revisions),
    );
  const [newRevision, setNewRevision] = useState({
    identifier: "",
    description: "",
    activate: false,
  });
  // undefined means the user has not chosen, so the server's defaults apply and the key is omitted.
  const [baseChoice, setBaseChoice] = useState<string | undefined>(undefined);
  const [carryChoice, setCarryChoice] = useState<boolean | undefined>(
    undefined,
  );
  const [carryModelChoice, setCarryModelChoice] = useState<boolean | undefined>(
    undefined,
  );
  const activeRevision =
    revisions.find((item) => item.status === "ACTIVE") ?? null;
  // "" stands for "None (start fresh)".
  const selectedBaseId = baseChoice ?? activeRevision?.id ?? "";
  const selectedBase =
    revisions.find((item) => item.id === selectedBaseId) ?? null;
  const carryForward = selectedBase ? (carryChoice ?? true) : false;
  const carryModelForward = selectedBase ? (carryModelChoice ?? true) : false;
  const baseIsNotActive =
    selectedBase !== null && selectedBase.id !== activeRevision?.id;
  function revisionCreateInput(): RevisionCreateInput {
    const input: RevisionCreateInput = {
      identifier: newRevision.identifier.trim(),
      description: emptyToNull(newRevision.description),
      activate: newRevision.activate,
    };
    if (baseChoice !== undefined) {
      input.based_on_revision_id = baseChoice === "" ? null : baseChoice;
    }
    if (selectedBase === null) {
      if (baseChoice !== undefined) {
        input.carry_forward_documents = false;
        input.carry_forward_model = false;
      }
    } else if (carryChoice !== undefined) {
      input.carry_forward_documents = carryChoice;
    }
    if (selectedBase !== null && carryModelChoice !== undefined) {
      input.carry_forward_model = carryModelChoice;
    }
    return input;
  }
  async function onCreateRevision() {
    if (!newRevision.identifier.trim()) {
      return;
    }
    setBusy(true);
    setConfirmActivation(false);
    setError(null);
    setMessage("");
    try {
      const revision = await createRevision(project.id, revisionCreateInput());
      setRevisions((current) => {
        const next = current.map((item) =>
          revision.status === "ACTIVE" && item.status === "ACTIVE"
            ? { ...item, status: "SUPERSEDED" as const }
            : item,
        );
        return [revision, ...next.filter((item) => item.id !== revision.id)];
      });
      if (revision.status === "ACTIVE") {
        setProject((current) => ({
          ...current,
          active_revision_identifier: revision.identifier,
        }));
      }
      const inherited = revision.inherited_document_count ?? 0;
      const inheritedEquipment = revision.inherited_model_equipment_count ?? 0;
      const carried = [
        inherited > 0
          ? `${inherited} ${inherited === 1 ? "document" : "documents"}`
          : null,
        inheritedEquipment > 0
          ? `${inheritedEquipment} equipment ${inheritedEquipment === 1 ? "item" : "items"}`
          : null,
      ].filter(Boolean);
      setMessage(
        carried.length > 0
          ? `Revision ${revision.identifier} created. ${carried.join(" and ")} carried forward.`
          : `Revision ${revision.identifier} created.`,
      );
      onClose();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not create revision",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <Sheet
      autoFocusFirst
      labelledBy="create-revision-heading"
      onClose={() => {
        if (!busy) onClose();
      }}
      presentation="workspace-revision"
    >
      <WorkspaceDrawerHeader
        titleId="create-revision-heading"
        title="Create revision"
        subtitle="Create a new, separately versioned working snapshot."
        closeLabel="Close revision form"
        pending={busy}
        onClose={onClose}
      />
      <form
        className="flex min-h-0 flex-1 flex-col"
        onSubmit={(event) => {
          event.preventDefault();
          if (!busy && newRevision.identifier.trim()) {
            if (newRevision.activate) setConfirmActivation(true);
            else void onCreateRevision();
          }
        }}
      >
        <WorkspaceDrawerBody>
          {error && (
            <WorkspaceNote role="alert" className="mb-4 text-red-700">
              {error}
            </WorkspaceNote>
          )}
          <fieldset
            disabled={
              busy ||
              project.status === "ARCHIVED" ||
              project.status === "CANCELLED"
            }
            className="space-y-[17px]"
          >
            <Field
              id="identifier"
              label="Revision Identifier"
              required
              presentation="workspace"
            >
              <Input
                id="identifier"
                value={newRevision.identifier}
                onChange={(e) =>
                  setNewRevision({ ...newRevision, identifier: e.target.value })
                }
                placeholder="e.g. IFC 125"
                maxLength={128}
                required
                presentation="workspace"
              />
              <small className="text-[11px] text-muted">
                Must be unique within the project.
              </small>
            </Field>
            <Field
              id="rev-description"
              label="Description"
              presentation="workspace"
            >
              <Textarea
                id="rev-description"
                value={newRevision.description}
                onChange={(e) =>
                  setNewRevision({
                    ...newRevision,
                    description: e.target.value,
                  })
                }
                placeholder="Summary of what changed in this revision"
                presentation="workspace-editor"
              />
            </Field>
            <Field id="base-revision" label="Based on" presentation="workspace">
              <Select
                id="base-revision"
                value={selectedBaseId}
                onValueChange={(value) => {
                  setBaseChoice(value);
                  setCarryChoice(undefined);
                  setCarryModelChoice(undefined);
                }}
                presentation="workspace"
              >
                <option value="">None (start fresh)</option>
                {revisions.map((item) => (
                  <option
                    key={item.id}
                    value={item.id}
                  >{`Revision ${item.identifier} (${REVISION_STATUS_STYLES[item.status].label})`}</option>
                ))}
              </Select>
              <small className="text-[11px] text-muted">
                Revisions may inherit selected snapshots from the base.
              </small>
            </Field>
            {baseIsNotActive && (
              <p className="text-xs text-muted">
                Based on a revision other than the active one.
              </p>
            )}
            <div>
              <span className="text-[11px] font-bold text-muted">
                Carry forward
              </span>
              <WorkspaceCheckboxField
                label="Documents"
                description="Carry forward document membership from the base revision."
                aria-label={
                  selectedBase
                    ? `Carry forward documents from Revision ${selectedBase.identifier}`
                    : "Carry forward documents"
                }
                checked={carryForward}
                disabled={!selectedBase}
                onChange={(e) => setCarryChoice(e.target.checked)}
              />
              <WorkspaceCheckboxField
                label="Engineering model"
                description="Carry forward the equipment/model snapshot independently."
                aria-label={
                  selectedBase
                    ? `Carry forward engineering model from Revision ${selectedBase.identifier}`
                    : "Carry forward engineering model"
                }
                checked={carryModelForward}
                disabled={!selectedBase}
                onChange={(e) => setCarryModelChoice(e.target.checked)}
              />
            </div>
            <WorkspaceCheckboxField
              label="Activate on creation"
              description="Supersedes the currently active revision. Leave unchecked to create a draft."
              aria-label="Activate on create"
              checked={newRevision.activate}
              onChange={(e) =>
                setNewRevision({ ...newRevision, activate: e.target.checked })
              }
            />
            <WorkspaceNote>
              <strong className={cn("text-ink")}>Important:</strong> The new
              revision is saved as a separate snapshot. Activation requires
              confirmation.
            </WorkspaceNote>
          </fieldset>
        </WorkspaceDrawerBody>
        <WorkspaceFormActions>
          <Button
            type="button"
            disabled={busy}
            onClick={onClose}
            presentation="workspace"
            variant="outline"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            pending={busy}
            disabled={
              !newRevision.identifier.trim() ||
              project.status === "ARCHIVED" ||
              project.status === "CANCELLED"
            }
            presentation="workspace"
          >
            <Plus />
            Create revision
          </Button>
        </WorkspaceFormActions>
      </form>
      {confirmActivation && (
        <ConfirmDialog
          title="Create and activate revision?"
          message={
            activeRevision
              ? `Creating this revision as active will supersede Revision ${activeRevision.identifier} after the server confirms success.`
              : "Create this revision and make it active?"
          }
          confirmLabel="Create and activate"
          onCancel={() => setConfirmActivation(false)}
          onConfirm={() => void onCreateRevision()}
          presentation="workspace"
        />
      )}
    </Sheet>
  );
}
function emptyToNull(value: string) {
  return value.trim() || null;
}
