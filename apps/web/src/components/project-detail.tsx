"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Lock, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ChipList } from "@/components/ui/chip";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DropdownMenu, type DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Field } from "@/components/ui/field";
import { Input, Textarea } from "@/components/ui/input";
import { MetaRow } from "@/components/ui/meta-row";
import { Mono } from "@/components/ui/mono";
import { SectionHeader } from "@/components/ui/section-header";
import {
  activateRevision,
  createRevision,
  formatDateShort,
  parseEngineerNames,
  projectAction,
  updateProject,
  type Project,
  type ProjectStatus,
  type Revision,
} from "@/lib/projects";
import { REVISION_STATUS_STYLES } from "@/lib/status-styles";

type ConfirmableAction = "pause" | "resume" | "cancel" | "archive" | "unarchive";

const ACTION_COPY: Record<
  Exclude<ConfirmableAction, "unarchive">,
  { title: string; message: string; confirmLabel: string; danger?: boolean }
> = {
  pause: {
    title: "Pause project?",
    message: "Paused projects cannot be edited until resumed.",
    confirmLabel: "Pause",
  },
  resume: {
    title: "Resume project?",
    message: "Resume active work on this project?",
    confirmLabel: "Resume",
  },
  cancel: {
    title: "Cancel project?",
    message: "Cancelled projects are read-only. This cannot be undone.",
    confirmLabel: "Cancel project",
    danger: true,
  },
  archive: {
    title: "Archive project?",
    message: "Archived projects are read-only. Typically done after closeout.",
    confirmLabel: "Archive",
  },
};

function unarchiveCopy(restoreStatus: ProjectStatus | null): {
  title: string;
  message: string;
  confirmLabel: string;
} {
  const target = restoreStatus ?? "ACTIVE";
  if (target === "CANCELLED") {
    return {
      title: "Unarchive project?",
      message: "Unarchive restores this project to Cancelled. It will stay read-only.",
      confirmLabel: "Unarchive",
    };
  }
  if (target === "PAUSED") {
    return {
      title: "Unarchive project?",
      message: "Unarchive restores this project to Paused.",
      confirmLabel: "Unarchive",
    };
  }
  return {
    title: "Unarchive project?",
    message: "Unarchive restores this project to Active.",
    confirmLabel: "Unarchive",
  };
}

export function ProjectDetail({
  initialProject,
  initialRevisions,
}: {
  initialProject: Project;
  initialRevisions: Revision[];
}) {
  const router = useRouter();
  const [project, setProject] = useState(initialProject);
  const [revisions, setRevisions] = useState(initialRevisions);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showAddRevision, setShowAddRevision] = useState(false);
  const [confirmAction, setConfirmAction] = useState<ConfirmableAction | null>(null);
  const [editForm, setEditForm] = useState({
    project_name: initialProject.project_name,
    client_name: initialProject.client_name ?? "",
    project_address: initialProject.project_address ?? "",
    project_scope: initialProject.project_scope ?? "",
    description: initialProject.description ?? "",
    engineer_names: initialProject.engineer_names.join(", "),
  });
  const [newRevision, setNewRevision] = useState({
    identifier: "",
    description: "",
    activate: false,
  });

  const archived = project.status === "ARCHIVED";
  const readOnly = archived || project.status === "CANCELLED";
  const activeRevision = revisions.find((item) => item.status === "ACTIVE") ?? null;

  function canActivate(revision: Revision): boolean {
    if (readOnly || revision.status !== "DRAFT") {
      return false;
    }
    if (!activeRevision) {
      return true;
    }
    return new Date(revision.created_at).getTime() > new Date(activeRevision.created_at).getTime();
  }

  async function runAction(action: ConfirmableAction) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await projectAction(project.id, action);
      setProject(updated);
      setMessage(`Project is now ${updated.status}.`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }

  async function onSaveMetadata(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await updateProject(project.id, {
        project_name: editForm.project_name,
        client_name: emptyToNull(editForm.client_name),
        project_address: emptyToNull(editForm.project_address),
        project_scope: emptyToNull(editForm.project_scope),
        description: emptyToNull(editForm.description),
        engineer_names: parseEngineerNames(editForm.engineer_names),
      });
      setProject(updated);
      setEditing(false);
      setMessage("Project updated.");
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateRevision() {
    if (!newRevision.identifier.trim()) {
      return;
    }
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const revision = await createRevision(project.id, {
        identifier: newRevision.identifier.trim(),
        description: emptyToNull(newRevision.description),
        activate: newRevision.activate,
      });
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
      setMessage(`Revision ${revision.identifier} created.`);
      setNewRevision({ identifier: "", description: "", activate: false });
      setShowAddRevision(false);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create revision");
    } finally {
      setBusy(false);
    }
  }

  async function onActivate(revisionId: string) {
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const activated = await activateRevision(project.id, revisionId);
      setRevisions((current) =>
        current.map((item) => {
          if (item.id === activated.id) {
            return activated;
          }
          if (item.status === "ACTIVE") {
            return { ...item, status: "SUPERSEDED" };
          }
          return item;
        }),
      );
      setProject((current) => ({
        ...current,
        active_revision_identifier: activated.identifier,
      }));
      setMessage(`Revision ${activated.identifier} is now ACTIVE.`);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not activate revision");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-screen-lg px-8 py-8">
      <Breadcrumb
        items={[
          { label: "Projects", href: "/" },
          { label: project.project_name },
        ]}
      />

      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="mb-1.5 flex items-center gap-2.5">
            <Mono className="text-slate-400">{project.project_number}</Mono>
            <Badge status={project.status} />
          </div>
          <h1 className="text-[22px] leading-tight font-bold tracking-tight text-slate-900">
            {project.project_name}
          </h1>
          <p className="mt-1 text-[14px] font-medium text-slate-500">
            {project.client_name || "No client set"}
          </p>
        </div>
        <div className="pt-1">
          <ProjectActionsMenu
            editing={editing}
            busy={busy}
            readOnly={readOnly}
            status={project.status}
            onEdit={() => setEditing((value) => !value)}
            onAction={setConfirmAction}
          />
        </div>
      </div>

      {readOnly ? (
        <div className="mb-5 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-[13px] font-medium text-slate-500">
          <span className="text-slate-400">
            <Lock className="h-[13px] w-[13px]" strokeWidth={1.5} />
          </span>
          This project is {project.status.toLowerCase()} and is read-only.
        </div>
      ) : null}

      {error ? <p className="mb-4 text-[13px] text-red-600">{error}</p> : null}
      {message ? <p className="mb-4 text-[13px] text-emerald-600">{message}</p> : null}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          {!editing || readOnly ? (
            <Card className="divide-y divide-slate-100">
              <MetaRow label="Address">
                {project.project_address || <span className="text-slate-300">—</span>}
              </MetaRow>
              <MetaRow label="Scope">
                {project.project_scope || <span className="text-slate-300">—</span>}
              </MetaRow>
              <MetaRow label="Description">
                {project.description || <span className="text-slate-300">—</span>}
              </MetaRow>
              <MetaRow label="Engineers">
                <ChipList items={project.engineer_names} />
              </MetaRow>
              <MetaRow label="Updated">{formatDateShort(project.updated_at)}</MetaRow>
            </Card>
          ) : (
            <Card className="space-y-4 p-5">
              <SectionHeader>Editing Project</SectionHeader>
              <form onSubmit={onSaveMetadata} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <Field id="project_name" label="Project Name" required>
                    <Input
                      id="project_name"
                      value={editForm.project_name}
                      onChange={(event) =>
                        setEditForm((current) => ({
                          ...current,
                          project_name: event.target.value,
                        }))
                      }
                      required
                    />
                  </Field>
                  <Field id="client_name" label="Client / Owner">
                    <Input
                      id="client_name"
                      value={editForm.client_name}
                      onChange={(event) =>
                        setEditForm((current) => ({
                          ...current,
                          client_name: event.target.value,
                        }))
                      }
                    />
                  </Field>
                </div>
                <Field id="project_address" label="Site Address">
                  <Input
                    id="project_address"
                    value={editForm.project_address}
                    onChange={(event) =>
                      setEditForm((current) => ({
                        ...current,
                        project_address: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field id="project_scope" label="Scope Summary">
                  <Textarea
                    id="project_scope"
                    value={editForm.project_scope}
                    onChange={(event) =>
                      setEditForm((current) => ({
                        ...current,
                        project_scope: event.target.value,
                      }))
                    }
                    rows={2}
                  />
                </Field>
                <Field id="description" label="Description">
                  <Textarea
                    id="description"
                    value={editForm.description}
                    onChange={(event) =>
                      setEditForm((current) => ({
                        ...current,
                        description: event.target.value,
                      }))
                    }
                    rows={3}
                  />
                </Field>
                <Field id="engineer_names" label="Engineers (comma-separated)">
                  <Input
                    id="engineer_names"
                    value={editForm.engineer_names}
                    onChange={(event) =>
                      setEditForm((current) => ({
                        ...current,
                        engineer_names: event.target.value,
                      }))
                    }
                  />
                </Field>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setEditing(false);
                      setEditForm({
                        project_name: project.project_name,
                        client_name: project.client_name ?? "",
                        project_address: project.project_address ?? "",
                        project_scope: project.project_scope ?? "",
                        description: project.description ?? "",
                        engineer_names: project.engineer_names.join(", "),
                      });
                    }}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" size="sm" disabled={busy}>
                    Save Changes
                  </Button>
                </div>
              </form>
            </Card>
          )}

          <Card className="overflow-hidden">
            <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
              <p className="text-[13px] font-bold tracking-wider text-slate-700 uppercase">
                Revision History
              </p>
              {!readOnly ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowAddRevision((value) => !value)}
                >
                  <Plus className="h-[13px] w-[13px]" strokeWidth={2} />
                  Add Revision
                </Button>
              ) : null}
            </div>

            {showAddRevision && !readOnly ? (
              <div className="space-y-3 border-b border-slate-100 bg-slate-50/80 px-5 py-4">
                <div className="grid grid-cols-2 gap-3">
                  <Field id="identifier" label="Revision Identifier" required>
                    <Input
                      id="identifier"
                      value={newRevision.identifier}
                      onChange={(event) =>
                        setNewRevision((current) => ({
                          ...current,
                          identifier: event.target.value,
                        }))
                      }
                      placeholder="Rev D"
                    />
                  </Field>
                  <Field id="rev-description" label="Description">
                    <Input
                      id="rev-description"
                      value={newRevision.description}
                      onChange={(event) =>
                        setNewRevision((current) => ({
                          ...current,
                          description: event.target.value,
                        }))
                      }
                      placeholder="90% Design"
                    />
                  </Field>
                </div>
                <label className="flex items-center gap-2 text-[13px] text-slate-700">
                  <input
                    type="checkbox"
                    checked={newRevision.activate}
                    onChange={(event) =>
                      setNewRevision((current) => ({
                        ...current,
                        activate: event.target.checked,
                      }))
                    }
                    className="rounded border-slate-300"
                  />
                  Activate on create
                </label>
                <div className="flex justify-end gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setShowAddRevision(false)}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    disabled={busy || !newRevision.identifier.trim()}
                    onClick={() => void onCreateRevision()}
                  >
                    Add
                  </Button>
                </div>
              </div>
            ) : null}

            {readOnly ? (
              <p className="px-5 py-4 text-[13px] text-slate-500">
                {archived
                  ? "Archived projects cannot receive new revisions. Unarchive to continue work."
                  : "Cancelled projects cannot be edited or receive new revisions."}
              </p>
            ) : null}

            {revisions.length === 0 ? (
              <div className="flex flex-col items-center gap-2 py-12">
                <span className="text-[22px] opacity-20">◫</span>
                <p className="text-[13px] text-slate-400">No revisions yet.</p>
              </div>
            ) : (
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="w-20 px-5 py-2.5 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                      Rev
                    </th>
                    <th className="px-4 py-2.5 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                      Description
                    </th>
                    <th className="w-28 px-4 py-2.5 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                      Status
                    </th>
                    <th className="w-28 px-4 py-2.5 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                      Updated
                    </th>
                    <th className="w-32" />
                  </tr>
                </thead>
                <tbody>
                  {revisions.map((revision, index) => (
                    <tr
                      key={revision.id}
                      className={`group transition-colors hover:bg-blue-50/40 ${
                        index !== 0 ? "border-t border-slate-100" : ""
                      }`}
                    >
                      <td className="px-5 py-3">
                        <Mono className="font-semibold text-slate-400">{revision.identifier}</Mono>
                      </td>
                      <td className="px-4 py-3">
                        <Link
                          href={`/projects/${project.id}/revisions/${revision.id}`}
                          className="text-left font-semibold text-slate-800 transition-colors hover:text-accent"
                        >
                          {revision.description || revision.identifier}
                        </Link>
                      </td>
                      <td className="px-4 py-3">
                        <Badge status={revision.status} kind="revision" />
                      </td>
                      <td className="px-4 py-3 text-[12px] text-slate-400">
                        {formatDateShort(revision.updated_at)}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <div className="flex items-center justify-end gap-1 opacity-100 sm:opacity-0 sm:group-hover:opacity-100">
                          {canActivate(revision) ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              disabled={busy}
                              onClick={() => void onActivate(revision.id)}
                            >
                              Activate
                            </Button>
                          ) : null}
                          <Button asChild variant="ghost" size="sm">
                            <Link href={`/projects/${project.id}/revisions/${revision.id}`}>
                              Open →
                            </Link>
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>

          <div className="rounded-2xl border-2 border-dashed border-slate-200 bg-white p-8 text-center">
            <p className="text-[14px] font-semibold text-slate-600">Future sections</p>
            <p className="mt-1 text-[13px] text-slate-400">
              Documents, Engineering Model, Extraction, SLD, Studies, and Reports arrive in later
              phases.
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <Card className="overflow-hidden">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Active Revision
              </p>
            </div>
            <div className="px-4 py-3">
              {activeRevision ? (
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <Mono className="font-semibold text-accent">{activeRevision.identifier}</Mono>
                    <Badge status="ACTIVE" kind="revision" />
                  </div>
                  <p className="text-[13.5px] font-semibold text-slate-800">
                    {activeRevision.description || activeRevision.identifier}
                  </p>
                  <p className="mt-1 text-[12px] text-slate-400">
                    Updated {formatDateShort(activeRevision.updated_at)}
                  </p>
                </div>
              ) : (
                <p className="text-[13px] text-slate-400">No active revision</p>
              )}
            </div>
          </Card>

          <Card className="overflow-hidden">
            <div className="border-b border-slate-100 px-4 py-3">
              <p className="text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Revisions
              </p>
            </div>
            <div className="space-y-2.5 px-4 py-3">
              {(["ACTIVE", "DRAFT", "SUPERSEDED"] as const).map((status) => {
                const count = revisions.filter((item) => item.status === status).length;
                const style = REVISION_STATUS_STYLES[status];
                return (
                  <div key={status} className="flex items-center justify-between">
                    <span
                      className={`flex items-center gap-1.5 text-[12.5px] font-medium ${style.text}`}
                    >
                      <span className={`h-1.5 w-1.5 rounded-full ${style.dot}`} />
                      {style.label}
                    </span>
                    <span className="text-[12.5px] font-semibold text-slate-400">{count}</span>
                  </div>
                );
              })}
              {revisions.length === 0 ? (
                <p className="text-[12.5px] text-slate-400">No revisions yet.</p>
              ) : null}
            </div>
          </Card>
        </div>
      </div>

      {confirmAction ? (
        <ConfirmDialog
          {...(confirmAction === "unarchive"
            ? unarchiveCopy(project.status_before_archive)
            : ACTION_COPY[confirmAction])}
          onConfirm={() => void runAction(confirmAction)}
          onCancel={() => setConfirmAction(null)}
        />
      ) : null}
    </div>
  );
}

function emptyToNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function ProjectActionsMenu({
  editing,
  busy,
  readOnly,
  status,
  onEdit,
  onAction,
}: {
  editing: boolean;
  busy: boolean;
  readOnly: boolean;
  status: ProjectStatus;
  onEdit: () => void;
  onAction: (action: ConfirmableAction) => void;
}) {
  const items: DropdownMenuItem[] = [];

  if (!readOnly) {
    items.push({
      id: "edit",
      label: editing ? "Close editor" : "Edit",
      onSelect: onEdit,
      disabled: busy,
    });
  }

  if (status === "ACTIVE") {
    items.push({
      id: "pause",
      label: "Pause",
      onSelect: () => onAction("pause"),
      disabled: busy,
      separatorBefore: items.length > 0,
    });
  }

  if (status === "PAUSED") {
    items.push({
      id: "resume",
      label: "Resume",
      onSelect: () => onAction("resume"),
      disabled: busy,
      separatorBefore: items.length > 0,
    });
  }

  if (status === "ACTIVE" || status === "PAUSED") {
    items.push({
      id: "cancel",
      label: "Cancel",
      onSelect: () => onAction("cancel"),
      disabled: busy,
      destructive: true,
    });
  }

  if (status !== "ARCHIVED") {
    items.push({
      id: "archive",
      label: "Archive",
      onSelect: () => onAction("archive"),
      disabled: busy,
      separatorBefore: true,
    });
  } else {
    items.push({
      id: "unarchive",
      label: "Unarchive",
      onSelect: () => onAction("unarchive"),
      disabled: busy,
      separatorBefore: items.length > 0,
    });
  }

  return <DropdownMenu items={items} label="Project actions" align="right" disabled={busy} />;
}
