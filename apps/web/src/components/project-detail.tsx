"use client";
import { workspaceStyles as ws } from "@/components/ui/workspace-styles";

import {
  WorkspaceCard,
  WorkspaceCardBody,
  WorkspaceDetails,
} from "@/components/ui/workspace-patterns";
import Link from "next/link";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AppShell } from "@/components/app-shell";
import { AsyncState } from "@/components/ui/async-state";
import {
  WorkspaceButton as Button,
  WorkspaceHeader,
  WorkspaceCardHeader,
  WorkspaceStatus,
  WorkspaceStats,
} from "@/components/ui-c-workspace";
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
  { title: string; message: string; confirmLabel: string; danger?: boolean }
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
      <div className={ws.root}>
        <WorkspaceHeader
          title={revisionsPage ? "Revisions" : project.project_name}
          subtitle={
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
              >
                <Plus />
                New revision
              </Button>
            ) : (
              <>
                <Button asChild>
                  <Link href={revisionsHref}>View revisions</Link>
                </Button>
                {active && (
                  <Button asChild variant="primary">
                    <Link href={overviewHref(active.id)}>
                      <ChevronRight />
                      Open active revision
                    </Link>
                  </Button>
                )}
              </>
            )
          }
        />
        <div className={ws.content}>
          <AsyncState
            refreshing={pq.isFetching || rq.isFetching}
            error={pq.error || rq.error}
            retry={() => {
              void pq.refetch();
              void rq.refetch();
            }}
          />
          {error && (
            <p role="alert" className={`${ws.note} mb-4 text-red-700`}>
              {error}
            </p>
          )}
          {message && (
            <p role="status" className={`${ws.note} mb-4`}>
              {message}
            </p>
          )}
          {readOnly && (
            <p role="status" className={`${ws.note} mb-4`}>
              This project is {project.status.toLowerCase()} and is read-only.
            </p>
          )}
          {revisionsPage ? (
            <>
              <WorkspaceCard as="div">
                <RevisionsRegister
                  projectId={project.id}
                  revisions={revisions}
                  filterable
                />
              </WorkspaceCard>
              <p className={`${ws.note} mt-[18px]`}>
                <strong>Revision lifecycle:</strong> Draft revisions may be
                activated if eligible. Activating a newer draft supersedes the
                previously active revision. Historical revisions remain
                available for inspection.
              </p>
            </>
          ) : (
            <>
              <div className={ws.meta}>
                <WorkspaceStatus status={project.status} />
                <span className="font-mono">{project.project_number}</span>
                <span>·</span>
                <span>Updated {formatDateShort(project.updated_at)}</span>
              </div>
              <section className={ws.section} aria-label="Project details">
                <div className={`${ws.columns} ${ws.projectColumns}`}>
                  <WorkspaceCard>
                    <WorkspaceCardHeader
                      title="Project Information"
                      subtitle="Client, location, technical scope and engineers"
                      actions={
                        <Button
                          size="sm"
                          disabled={readOnly || busy}
                          onClick={() => setEditing(true)}
                        >
                          <Pencil />
                          Edit details
                        </Button>
                      }
                    />
                    <WorkspaceCardBody>
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
                    </WorkspaceCardBody>
                  </WorkspaceCard>
                  <aside className={ws.stack}>
                    <WorkspaceCard spacing="rail">
                      <h2>Project lifecycle</h2>
                      <p>
                        Status: <WorkspaceStatus status={project.status} />
                      </p>
                      <p>
                        Changing the status is separate from editing project
                        details.
                      </p>
                      <div className={`${ws.actions} mt-4`}>
                        {lifecycleActions.map((action) => (
                          <Button
                            key={action}
                            size="sm"
                            variant={action === "cancel" ? "danger" : "outline"}
                            disabled={busy}
                            onClick={() => setConfirmAction(action)}
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
                      {busy && <p role="status">Updating project…</p>}
                    </WorkspaceCard>
                    <WorkspaceCard spacing="rail">
                      <h2>Project summary</h2>
                      <dl className={ws.summary}>
                        <dt>Project number</dt>
                        <dd className="font-mono">{project.project_number}</dd>
                        <dt>Revision count</dt>
                        <dd>{revisions.length}</dd>
                        <dt>Last updated</dt>
                        <dd>{formatDateShort(project.updated_at)}</dd>
                      </dl>
                    </WorkspaceCard>
                  </aside>
                </div>
              </section>
              <section className={ws.section} aria-label="Revision activity">
                <div className={`${ws.columns} ${ws.projectColumns}`}>
                  <div className={ws.stack}>
                    <WorkspaceCard spacing="work">
                      <div className={ws.workHead}>
                        <div>
                          <span className={ws.overline}>Current work</span>
                          <h2>
                            {active
                              ? `Continue with ${active.identifier}`
                              : "No active revision"}
                          </h2>
                          <p>
                            {active
                              ? `${active.description || "Active revision"} · Ready for document review and engineering model work.`
                              : "Create or activate a revision to begin engineering work."}
                          </p>
                        </div>
                        {active && <WorkspaceStatus status={active.status} />}
                      </div>
                      <WorkspaceStats
                        action={
                          <Button asChild variant="primary">
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
                    </WorkspaceCard>
                    <WorkspaceCard>
                      <WorkspaceCardHeader
                        title="Revision history"
                        subtitle="Recent revisions for this project"
                        actions={
                          <Button asChild size="sm">
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
                              className={ws.historyRow}
                            >
                              <span>
                                <strong>
                                  {rev.identifier} ·{" "}
                                  {rev.description || "Revision"}
                                </strong>
                                <small>
                                  {rev.based_on_revision_id
                                    ? `Based on ${revisions.find((r) => r.id === rev.based_on_revision_id)?.identifier ?? rev.based_on_identifier ?? "source revision"} · `
                                    : ""}
                                  Updated {formatDateShort(rev.updated_at)}
                                </small>
                              </span>
                              <span className={ws.actions}>
                                <WorkspaceStatus status={rev.status} />
                                <ChevronRight size={14} />
                              </span>
                            </Link>
                          ))
                      ) : (
                        <p className={`${ws.pad} ${ws.subtitle}`}>
                          No revisions yet. Create a revision to begin
                          engineering work.
                        </p>
                      )}
                    </WorkspaceCard>
                  </div>
                  <aside>
                    <WorkspaceCard spacing="rail">
                      <span className={ws.overline}>Active revision</span>
                      {active ? (
                        <>
                          <div className="my-3 font-mono text-[22px] font-bold">
                            {active.identifier}
                          </div>
                          <WorkspaceStatus status={active.status} />
                          <p className="!my-3">{active.description || "—"}</p>
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
                          >
                            <Link href={overviewHref(active.id)}>
                              View revision details
                              <ChevronRight />
                            </Link>
                          </Button>
                        </>
                      ) : (
                        <>
                          <p>There is no active revision.</p>
                          <Button asChild size="sm">
                            <Link href={revisionsHref}>
                              View revisions
                              <ChevronRight />
                            </Link>
                          </Button>
                        </>
                      )}
                    </WorkspaceCard>
                  </aside>
                </div>
              </section>
              <p className={ws.help}>
                Workspace counts are not provided by revision metadata. Open a
                workspace to inspect its records.
              </p>
            </>
          )}
        </div>
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
            className={ws.dialog}
            {...(confirmAction === "unarchive"
              ? unarchiveCopy(project.status_before_archive)
              : ACTION_COPY[confirmAction])}
            onConfirm={() => void runAction(confirmAction)}
            onCancel={() => setConfirmAction(null)}
          />
        )}
      </div>
    </AppShell>
  );
}
