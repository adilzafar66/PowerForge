"use client";
import type { ReactNode } from "react";
import { Card, CardContent } from "@/components/ui/card";
import {
  WorkspaceRoot,
  WorkspaceContent,
  WorkspaceNote,
  WorkspaceColumns,
} from "@/components/ui/workspace-layout";
import { WorkspaceDetails } from "@/components/ui/workspace-patterns";
import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import {
  WorkspaceCardHeader,
  WorkspaceStats,
} from "@/components/ui/workspace-patterns";
import {
  ArrowLeft,
  ChevronRight,
  Check,
  Pencil,
  Files,
  Cpu,
} from "lucide-react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { RevisionEditor } from "@/components/revision-editor";
import {
  activateRevision,
  formatDateShort,
  type Project,
  type Revision,
} from "@/lib/projects";
import { revisionHref } from "@/lib/workspace-navigation";
export function RevisionOverview({
  project,
  revision,
  revisions,
}: {
  project: Project;
  revision: Revision;
  revisions: Revision[];
}) {
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const locked =
    project.status === "ARCHIVED" || project.status === "CANCELLED";
  const active = revisions.find((r) => r.status === "ACTIVE");
  const eligible =
    !locked &&
    revision.status === "DRAFT" &&
    (!active ||
      new Date(revision.created_at).getTime() >
        new Date(active.created_at).getTime());
  async function activate() {
    if (!eligible || pending) return;
    setConfirm(false);
    setPending(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await activateRevision(project.id, revision.id);
      client.setQueryData(keys.revision(project.id, revision.id), updated);
      client.setQueryData<Revision[]>(keys.revisions(project.id), (items) =>
        (items ?? revisions).map((item) =>
          item.id === updated.id
            ? updated
            : item.status === "ACTIVE"
              ? { ...item, status: "SUPERSEDED" }
              : item,
        ),
      );
      if (active)
        client.setQueryData<Revision>(
          keys.revision(project.id, active.id),
          (old) => (old ? { ...old, status: "SUPERSEDED" } : old),
        );
      client.setQueryData<Project>(keys.project(project.id), (old) => ({
        ...(old ?? project),
        active_revision_identifier: updated.identifier,
      }));
      setMessage(`Revision ${updated.identifier} is now ACTIVE.`);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Could not activate revision.",
      );
    } finally {
      setPending(false);
    }
  }
  const href = (
    destination: "overview" | "documents" | "equipment" | "topology",
  ) => revisionHref(project.id, revision.id, undefined, "", destination);
  const source =
    revisions.find((r) => r.id === revision.based_on_revision_id)?.identifier ??
    revision.based_on_identifier;
  return (
    <WorkspaceRoot>
      <PageHeader
        title={
          <>
            {revision.identifier}
            <Badge status={revision.status} presentation="workspace" />
          </>
        }
        description={`${revision.description || "Revision"} · ${project.project_name}`}
        actions={
          <>
            <Button asChild presentation="workspace" variant="outline">
              <Link href={`/projects/${project.id}/revisions`}>
                <ArrowLeft />
                All revisions
              </Link>
            </Button>
            {revision.status === "DRAFT" && (
              <Button
                variant="primary"
                pending={pending}
                disabled={!eligible}
                onClick={() => setConfirm(true)}
                presentation="workspace"
              >
                <Check />
                Activate revision
              </Button>
            )}
            <Button asChild variant="primary" presentation="workspace">
              <Link href={href("documents")}>
                Open revision workspace
                <ChevronRight />
              </Link>
            </Button>
          </>
        }
        presentation="workspace"
      />
      <WorkspaceContent>
        {error && (
          <WorkspaceNote role="alert" className="mb-4 text-red-700">
            {error}
          </WorkspaceNote>
        )}
        {message && (
          <WorkspaceNote role="status" className="mb-4">
            {message}
          </WorkspaceNote>
        )}
        <WorkspaceColumns>
          <div className="flex flex-col gap-5 min-w-0">
            {(locked || revision.status !== "ACTIVE") && (
              <WorkspaceNote as="div">
                <strong className="text-ink">
                  {locked
                    ? "Project read-only"
                    : revision.status === "SUPERSEDED"
                      ? "Historical revision — engineering data read-only"
                      : "Draft revision"}
                </strong>
                <p className="mt-1">
                  {locked
                    ? "This project's records are read-only."
                    : revision.status === "SUPERSEDED"
                      ? "You can inspect documents and engineering data. Descriptive revision metadata remains editable."
                      : eligible
                        ? "This revision can be developed independently. Activation is a separate, deliberate lifecycle action."
                        : "Only a draft created after the current active revision can be activated."}
                </p>
              </WorkspaceNote>
            )}
            <Card presentation="workspace" as="article" spacing="body">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-workspace-overline tracking-[var(--pf-tracking-overline)] text-[var(--pf-text-tertiary)] font-bold uppercase mb-[9px]">
                    Revision summary
                  </div>
                  <h2 className="mb-2 text-[22px] font-bold">
                    {revision.description || revision.identifier}
                  </h2>
                  <p className="text-workspace-body text-muted leading-[var(--pf-leading-copy)] m-0">
                    {revision.identifier} ·{" "}
                    {formatDateShort(revision.created_at)} ·{" "}
                    {project.project_number}
                  </p>
                </div>
                <Badge status={revision.status} presentation="workspace" />
              </div>
              <WorkspaceStats />
            </Card>
            <Card presentation="workspace" as="article">
              <WorkspaceCardHeader
                title="Revision workspaces"
                subtitle="Move into the working areas for this revision"
              />
              <CardContent presentation="workspace" className="!py-2">
                <Link
                  className="flex items-center justify-between gap-[10px] py-[13px] px-0 border-b border-[var(--pf-border-item)] last:border-0 hover:text-accent"
                  href={href("documents")}
                >
                  <span className="flex items-center gap-2">
                    <Files size={19} />
                    <span>
                      <strong className="block text-workspace-label mb-1">
                        Documents
                      </strong>
                      <small className="text-muted text-workspace-caption">
                        Source drawings and document processing
                      </small>
                    </span>
                  </span>
                  <ChevronRight size={16} />
                </Link>
                <Link
                  className="flex items-center justify-between gap-[10px] py-[13px] px-0 border-b border-[var(--pf-border-item)] last:border-0 hover:text-accent"
                  href={href("equipment")}
                >
                  <span className="flex items-center gap-2">
                    <Cpu size={19} />
                    <span>
                      <strong className="block text-workspace-label mb-1">
                        Engineering Model
                      </strong>
                      <small className="text-muted text-workspace-caption">
                        Equipment, attributes, terminals and topology
                      </small>
                    </span>
                  </span>
                  <ChevronRight size={16} />
                </Link>
              </CardContent>
            </Card>
            <Card presentation="workspace" as="article">
              <WorkspaceCardHeader
                title="Revision Information"
                subtitle="Lifecycle and ancestry of the selected revision"
                actions={
                  <Button
                    size="sm"
                    aria-label="Edit revision information"
                    disabled={locked || pending}
                    onClick={() => setEditing(true)}
                    presentation="workspace"
                    variant="outline"
                  >
                    <Pencil />
                    Edit
                  </Button>
                }
              />
              <CardContent presentation="workspace">
                <WorkspaceDetails
                  items={[
                    {
                      label: "Identifier",
                      value: revision.identifier,
                      mono: true,
                    },
                    {
                      label: "Status",
                      value: (
                        <Badge
                          status={revision.status}
                          presentation="workspace"
                        />
                      ),
                    },
                    {
                      label: "Description",
                      value: revision.description || "—",
                    },
                    {
                      label: "System frequency",
                      value:
                        revision.system_frequency == null
                          ? "Not set"
                          : `${revision.system_frequency} Hz`,
                    },
                    {
                      label: "System phase count",
                      value:
                        revision.system_phase_count == null
                          ? "Not set"
                          : `${revision.system_phase_count} phase`,
                    },
                    {
                      label: "Based on",
                      value: revision.based_on_revision_id ? (
                        <Link
                          className="font-bold text-accent"
                          href={revisionHref(
                            project.id,
                            revision.based_on_revision_id,
                            undefined,
                            "",
                            "overview",
                          )}
                        >
                          {source || "Source revision"} ›
                        </Link>
                      ) : (
                        "—"
                      ),
                    },
                    {
                      label: "Created",
                      value: formatDateShort(revision.created_at),
                    },
                    {
                      label: "Updated",
                      value: formatDateShort(revision.updated_at),
                    },
                    ...(revision.created_by
                      ? [{ label: "Created by", value: revision.created_by }]
                      : []),
                  ]}
                />
              </CardContent>
            </Card>
          </div>
          <aside className="flex flex-col gap-5 min-w-0">
            <Card presentation="workspace" as="article" spacing="body">
              <h2 className="mb-4 text-sm font-bold">Revision history</h2>
              <div className="relative mt-[3px] mx-0 mb-[5px] pl-[21px] before:content-[''] before:absolute before:left-[7px] before:top-[10px] before:bottom-[5px] before:w-[1px] before:bg-[var(--pf-timeline-line)]">
                <RevisionHistoryEvent
                  title={
                    <>
                      {revision.status === "ACTIVE"
                        ? "Currently active"
                        : revision.status === "DRAFT"
                          ? "Draft created"
                          : "Superseded"}
                    </>
                  }
                >
                  Last updated {formatDateShort(revision.updated_at)}
                </RevisionHistoryEvent>
                {revision.based_on_revision_id && (
                  <RevisionHistoryEvent
                    title={<>Based on {source || "source revision"}</>}
                  >
                    Inherited document and model snapshots where selected at
                    creation.
                  </RevisionHistoryEvent>
                )}
                <RevisionHistoryEvent title={<>Revision created</>}>
                  {formatDateShort(revision.created_at)}
                </RevisionHistoryEvent>
              </div>
            </Card>
            <Card presentation="workspace" as="article" spacing="body">
              <h2 className="mb-4 text-sm font-bold">Carry-forward history</h2>
              {["Documents", "Engineering model"].map((label) => (
                <div
                  key={label}
                  className="flex items-center justify-between gap-[10px] py-[13px] px-0 border-b border-[var(--pf-border-item)] last:border-0 hover:text-accent"
                >
                  <span className="text-muted">{label}</span>
                  <strong className="block text-workspace-label mb-1">
                    {revision.based_on_revision_id
                      ? "Not recorded"
                      : "Not inherited"}
                  </strong>
                </div>
              ))}
              <WorkspaceNote className="mt-4">
                Individual carry-forward choices are not included in revision
                metadata. Workspace counts are also unavailable here.
              </WorkspaceNote>
            </Card>
          </aside>
        </WorkspaceColumns>
      </WorkspaceContent>
      {editing && (
        <RevisionEditor
          project={project}
          revision={revision}
          onClose={() => setEditing(false)}
          onSaved={() => {
            setEditing(false);
            setMessage("Revision updated.");
          }}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title="Activate revision?"
          message={
            active
              ? `Revision ${active.identifier} will be superseded after Revision ${revision.identifier} is successfully activated.`
              : `Make Revision ${revision.identifier} the active revision?`
          }
          confirmLabel="Activate"
          onCancel={() => setConfirm(false)}
          onConfirm={() => void activate()}
          presentation="workspace"
        />
      )}
    </WorkspaceRoot>
  );
}

/** History presentation stays local to the overview that owns these events. */
function RevisionHistoryEvent({
  title,
  children,
}: {
  title: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="relative pb-[19px] last:p-0 before:content-[''] before:absolute before:left-[-18px] before:top-[5px] before:border-2 before:border-panel before:bg-accent before:w-2 before:h-2 before:rounded-[50%] before:shadow-[0_0_0_1px_var(--pf-timeline-ring)]">
      <h3 className="text-workspace-label font-semibold mt-0 mx-0 mb-[5px]">
        {title}
      </h3>
      <p className="text-muted text-workspace-caption m-0 leading-[var(--pf-leading-hint)]">
        {children}
      </p>
    </div>
  );
}
