"use client";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";
import {
  WorkspaceRoot,
  WorkspaceContent,
  WorkspaceNote,
  WorkspaceColumns,
} from "@/components/ui/workspace-layout";
import { WorkspaceDetails } from "@/components/ui/workspace-patterns";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AppShell } from "@/components/app-shell";
import { AsyncState } from "@/components/ui/async-state";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
import {
  WorkspaceCardHeader,
  WorkspaceStats,
} from "@/components/ui/workspace-patterns";
import { ChevronRight, Pencil, Plus, Pause, Play } from "lucide-react";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ProjectEditor } from "@/components/project-editor";
import { RevisionCreateSheet } from "@/components/revision-create-sheet";
import { RevisionsRegister } from "@/components/revisions-register";
import {
  getProject,
  listRevisions,
  projectAction,
  formatDateShort,
  type Project,
  type Revision,
  type ProjectStatus,
} from "@/lib/projects";
import { revisionHref } from "@/lib/workspace-navigation";
type ConfirmableAction =
  "pause" | "resume" | "cancel" | "archive" | "unarchive";
const ACTION_COPY: Record<
  Exclude<ConfirmableAction, "unarchive">,
  {
    title: string;
    message: string;
    confirmLabel: string;
    danger?: boolean;
  }
> = {
  pause: {
    title: "Pause project?",
    message: "Pause active work on this project? Its records remain editable.",
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
      message:
        "Unarchive restores this project to Cancelled. It will stay read-only.",
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
  revisionsPage = false,
}: {
  initialProject: Project;
  initialRevisions: Revision[];
  revisionsPage?: boolean;
}) {
  const client = useQueryClient();
  const pq = useQuery({
    queryKey: keys.project(initialProject.id),
    queryFn: () => getProject(initialProject.id),
    initialData: initialProject,
  });
  const rq = useQuery({
    queryKey: keys.revisions(initialProject.id),
    queryFn: () => listRevisions(initialProject.id),
    initialData: initialRevisions,
  });
  const project = pq.data,
    revisions = rq.data;
  const setProject = (value: Project) =>
    client.setQueryData(keys.project(project.id), value);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirmAction, setConfirmAction] = useState<ConfirmableAction | null>(
    null,
  );
  const readOnly =
    project.status === "ARCHIVED" || project.status === "CANCELLED";
  const active = revisions.find((r) => r.status === "ACTIVE");
  async function runAction(action: ConfirmableAction) {
    setConfirmAction(null);
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await projectAction(project.id, action);
      setProject(updated);
      setMessage(`Project is now ${updated.status}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Action failed");
    } finally {
      setBusy(false);
      setConfirmAction(null);
    }
  }
  const overviewHref = (id: string) =>
    revisionHref(project.id, id, undefined, "", "overview");
  const revisionsHref = `/projects/${project.id}/revisions`;
  const lifecycleActions: ConfirmableAction[] =
    project.status === "ACTIVE"
      ? ["pause", "cancel", "archive"]
      : project.status === "PAUSED"
        ? ["resume", "cancel", "archive"]
        : project.status === "CANCELLED"
          ? ["archive"]
          : ["unarchive"];
  return (
    <AppShell project={project} revisions={revisions}>
      <WorkspaceRoot>
        <PageHeader
          title={revisionsPage ? "Revisions" : project.project_name}
          description={
            revisionsPage
              ? `Review and manage the revision history for ${project.project_name}.`
              : `Project ${project.project_number} · ${project.client_name || "Client not specified"}`
          }
          actions={
            revisionsPage ? (
              <Button
                variant="primary"
                disabled={readOnly || busy}
                onClick={() => setCreating(true)}
                presentation="workspace"
              >
                <Plus />
                New revision
              </Button>
            ) : (
              <>
                <Button asChild presentation="workspace" variant="outline">
                  <Link href={revisionsHref}>View revisions</Link>
                </Button>
                {active && (
                  <Button asChild variant="primary" presentation="workspace">
                    <Link href={overviewHref(active.id)}>
                      <ChevronRight />
                      Open active revision
                    </Link>
                  </Button>
                )}
              </>
            )
          }
          presentation="workspace"
        />
        <WorkspaceContent>
          <AsyncState
            refreshing={pq.isFetching || rq.isFetching}
            error={pq.error || rq.error}
            retry={() => {
              void pq.refetch();
              void rq.refetch();
            }}
          />
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
          {readOnly && (
            <WorkspaceNote role="status" className="mb-4">
              This project is {project.status.toLowerCase()} and is read-only.
            </WorkspaceNote>
          )}
          {revisionsPage ? (
            <>
              <Card presentation="workspace" as="div">
                <RevisionsRegister
                  projectId={project.id}
                  revisions={revisions}
                  filterable
                />
              </Card>
              <WorkspaceNote className="mt-[18px]">
                <strong className="text-ink">Revision lifecycle:</strong> Draft
                revisions may be activated if eligible. Activating a newer draft
                supersedes the previously active revision. Historical revisions
                remain available for inspection.
              </WorkspaceNote>
            </>
          ) : (
            <>
              <div className="flex items-center gap-[9px] mb-[17px] text-muted">
                <Badge status={project.status} presentation="workspace" />
                <span className="font-mono">{project.project_number}</span>
                <span>·</span>
                <span>Updated {formatDateShort(project.updated_at)}</span>
              </div>
              <section className="mb-[22px]" aria-label="Project details">
                <WorkspaceColumns variant="project">
                  <Card presentation="workspace" as="article">
                    <WorkspaceCardHeader
                      title="Project Information"
                      subtitle="Client, location, technical scope and engineers"
                      actions={
                        <Button
                          size="sm"
                          disabled={readOnly || busy}
                          onClick={() => setEditing(true)}
                          presentation="workspace"
                          variant="outline"
                        >
                          <Pencil />
                          Edit details
                        </Button>
                      }
                    />
                    <CardContent presentation="workspace">
                      <WorkspaceDetails
                        variant="project"
                        items={[
                          {
                            label: "Project Number",
                            value: project.project_number,
                            mono: true,
                          },
                          {
                            label: "Project Name",
                            value: project.project_name,
                          },
                          {
                            label: "Client / Owner",
                            value: project.client_name || "—",
                          },
                          {
                            label: "Site Address",
                            value: project.project_address || "—",
                          },
                          {
                            label: "Scope Summary",
                            value: project.project_scope || "—",
                          },
                          {
                            label: "Project Description",
                            value: project.description || "—",
                          },
                          {
                            label: "Engineers",
                            value: project.engineer_names.join(", ") || "—",
                          },
                        ]}
                      />
                    </CardContent>
                  </Card>
                  <aside className="flex flex-col gap-5 min-w-0">
                    <Card presentation="workspace" as="article" spacing="rail">
                      <h2 className="text-workspace-body font-semibold mt-0 mx-0 mb-3">
                        Project lifecycle
                      </h2>
                      <p className="my-[5px] mx-0 text-muted text-workspace-label leading-[var(--pf-leading-relaxed)]">
                        Status:{" "}
                        <Badge
                          status={project.status}
                          presentation="workspace"
                        />
                      </p>
                      <p className="my-[5px] mx-0 text-muted text-workspace-label leading-[var(--pf-leading-relaxed)]">
                        Changing the status is separate from editing project
                        details.
                      </p>
                      <div className="flex items-center gap-[10px] flex-wrap mt-4">
                        {lifecycleActions.map((action) => (
                          <Button
                            key={action}
                            size="sm"
                            variant={action === "cancel" ? "danger" : "outline"}
                            disabled={busy}
                            onClick={() => setConfirmAction(action)}
                            presentation="workspace"
                          >
                            {action === "pause" ? (
                              <Pause />
                            ) : action === "resume" ? (
                              <Play />
                            ) : null}
                            {action.charAt(0).toUpperCase() + action.slice(1)}
                          </Button>
                        ))}
                      </div>
                      {busy && (
                        <p
                          role="status"
                          className="my-[5px] mx-0 text-muted text-workspace-label leading-[var(--pf-leading-relaxed)]"
                        >
                          Updating project…
                        </p>
                      )}
                    </Card>
                    <Card presentation="workspace" as="article" spacing="rail">
                      <h2 className="text-workspace-body font-semibold mt-0 mx-0 mb-3">
                        Project summary
                      </h2>
                      <dl className="grid grid-cols-[1fr_auto] gap-[13px] text-workspace-label">
                        <dt className="text-muted">Project number</dt>
                        <dd
                          className={cn(
                            "font-mono",
                            "m-0 text-right font-semibold",
                          )}
                        >
                          {project.project_number}
                        </dd>
                        <dt className="text-muted">Revision count</dt>
                        <dd className="m-0 text-right font-semibold">
                          {revisions.length}
                        </dd>
                        <dt className="text-muted">Last updated</dt>
                        <dd className="m-0 text-right font-semibold">
                          {formatDateShort(project.updated_at)}
                        </dd>
                      </dl>
                    </Card>
                  </aside>
                </WorkspaceColumns>
              </section>
              <section className="mb-[22px]" aria-label="Revision activity">
                <WorkspaceColumns variant="project">
                  <div className="flex flex-col gap-5 min-w-0">
                    <Card presentation="workspace" as="article" spacing="work">
                      <div className="flex items-start justify-between gap-[14px] max-[530px]:flex-col">
                        <div>
                          <span className="text-workspace-overline tracking-[var(--pf-tracking-overline)] text-[var(--pf-text-tertiary)] font-bold uppercase">
                            Current work
                          </span>
                          <h2 className="text-workspace-subheading font-semibold tracking-[-0.4px] mt-[6px] mx-0 mb-[7px]">
                            {active
                              ? `Continue with ${active.identifier}`
                              : "No active revision"}
                          </h2>
                          <p className="text-muted text-workspace-label leading-[var(--pf-leading-relaxed)] m-0">
                            {active
                              ? `${active.description || "Active revision"} · Ready for document review and engineering model work.`
                              : "Create or activate a revision to begin engineering work."}
                          </p>
                        </div>
                        {active && (
                          <Badge
                            status={active.status}
                            presentation="workspace"
                          />
                        )}
                      </div>
                      <WorkspaceStats
                        action={
                          <Button
                            asChild
                            variant="primary"
                            presentation="workspace"
                          >
                            <Link
                              href={
                                active
                                  ? revisionHref(
                                      project.id,
                                      active.id,
                                      undefined,
                                      "",
                                      "documents",
                                    )
                                  : revisionsHref
                              }
                            >
                              {active ? "Open workspace" : "Manage revisions"}
                              <ChevronRight />
                            </Link>
                          </Button>
                        }
                      />
                    </Card>
                    <Card presentation="workspace" as="article">
                      <WorkspaceCardHeader
                        title="Revision history"
                        subtitle="Recent revisions for this project"
                        actions={
                          <Button
                            asChild
                            size="sm"
                            presentation="workspace"
                            variant="outline"
                          >
                            <Link href={revisionsHref}>
                              All revisions
                              <ChevronRight />
                            </Link>
                          </Button>
                        }
                      />
                      {revisions.length ? (
                        [...revisions]
                          .sort(
                            (a, b) =>
                              Date.parse(b.created_at) -
                              Date.parse(a.created_at),
                          )
                          .map((rev) => (
                            <Link
                              key={rev.id}
                              href={overviewHref(rev.id)}
                              className="flex items-center justify-between gap-[15px] py-[15px] px-[22px] border-b border-[var(--pf-border-history)] [transition:background-color_var(--pf-transition-fast)] last:border-0 hover:bg-[var(--pf-option-hover)]"
                            >
                              <span>
                                <strong className="text-workspace-label font-semibold">
                                  {rev.identifier} ·{" "}
                                  {rev.description || "Revision"}
                                </strong>
                                <small className="block text-muted text-workspace-caption mt-[5px]">
                                  {rev.based_on_revision_id
                                    ? `Based on ${revisions.find((r) => r.id === rev.based_on_revision_id)?.identifier ?? rev.based_on_identifier ?? "source revision"} · `
                                    : ""}
                                  Updated {formatDateShort(rev.updated_at)}
                                </small>
                              </span>
                              <span className="flex items-center gap-[10px] flex-wrap">
                                <Badge
                                  status={rev.status}
                                  presentation="workspace"
                                />
                                <ChevronRight size={14} />
                              </span>
                            </Link>
                          ))
                      ) : (
                        <p className="p-6 max-[530px]:p-[18px] text-workspace-body text-muted leading-[var(--pf-leading-copy)] m-0">
                          No revisions yet. Create a revision to begin
                          engineering work.
                        </p>
                      )}
                    </Card>
                  </div>
                  <aside>
                    <Card presentation="workspace" as="article" spacing="rail">
                      <span className="text-workspace-overline tracking-[var(--pf-tracking-overline)] text-[var(--pf-text-tertiary)] font-bold uppercase">
                        Active revision
                      </span>
                      {active ? (
                        <>
                          <div className="my-3 font-mono text-[22px] font-bold">
                            {active.identifier}
                          </div>
                          <Badge
                            status={active.status}
                            presentation="workspace"
                          />
                          <p
                            className={cn(
                              "!my-3",
                              "my-[5px] mx-0 text-muted text-workspace-label leading-[var(--pf-leading-relaxed)]",
                            )}
                          >
                            {active.description || "—"}
                          </p>
                          <div className="flex justify-between border-t border-border pt-3 text-xs">
                            <span className="text-muted">Updated</span>
                            <strong>
                              {formatDateShort(active.updated_at)}
                            </strong>
                          </div>
                          <Button
                            asChild
                            size="sm"
                            className="mt-[17px] w-full"
                            presentation="workspace"
                            variant="outline"
                          >
                            <Link href={overviewHref(active.id)}>
                              View revision details
                              <ChevronRight />
                            </Link>
                          </Button>
                        </>
                      ) : (
                        <>
                          <p className="my-[5px] mx-0 text-muted text-workspace-label leading-[var(--pf-leading-relaxed)]">
                            There is no active revision.
                          </p>
                          <Button
                            asChild
                            size="sm"
                            presentation="workspace"
                            variant="outline"
                          >
                            <Link href={revisionsHref}>
                              View revisions
                              <ChevronRight />
                            </Link>
                          </Button>
                        </>
                      )}
                    </Card>
                  </aside>
                </WorkspaceColumns>
              </section>
              <p className="text-muted text-workspace-caption leading-[var(--pf-leading-hint)] mt-4">
                Workspace counts are not provided by revision metadata. Open a
                workspace to inspect its records.
              </p>
            </>
          )}
        </WorkspaceContent>
        {editing && (
          <ProjectEditor
            project={project}
            onClose={() => setEditing(false)}
            onSaved={() => {
              setEditing(false);
              setMessage("Project updated.");
            }}
          />
        )}
        {creating && (
          <RevisionCreateSheet
            project={project}
            revisions={revisions}
            onClose={() => setCreating(false)}
            setMessage={setMessage}
          />
        )}
        {confirmAction && (
          <ConfirmDialog
            {...(confirmAction === "unarchive"
              ? unarchiveCopy(project.status_before_archive)
              : ACTION_COPY[confirmAction])}
            onConfirm={() => void runAction(confirmAction)}
            onCancel={() => setConfirmAction(null)}
            presentation="workspace"
          />
        )}
      </WorkspaceRoot>
    </AppShell>
  );
}
