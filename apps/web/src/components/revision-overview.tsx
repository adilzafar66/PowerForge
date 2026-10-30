"use client";
import {
  WorkspaceCard,
  WorkspaceCardBody,
  WorkspaceDetails,
} from "@/components/ui/workspace-patterns";
import Link from "next/link";
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import {
  WorkspaceButton as Button,
  WorkspaceHeader,
  WorkspaceCardHeader,
  WorkspaceStatus,
  WorkspaceStats,
} from "@/components/ui-c-workspace";
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
    <div className="ui-c">
      <WorkspaceHeader
        title={
          <>
            {revision.identifier}
            <WorkspaceStatus status={revision.status} />
          </>
        }
        subtitle={`${revision.description || "Revision"} · ${project.project_name}`}
        actions={
          <>
            <Button asChild>
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
              >
                <Check />
                Activate revision
              </Button>
            )}
            <Button asChild variant="primary">
              <Link href={href("documents")}>
                Open revision workspace
                <ChevronRight />
              </Link>
            </Button>
          </>
        }
      />
      <div className="ui-c-content">
        {error && (
          <p role="alert" className="ui-c-note mb-4 text-red-700">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="ui-c-note mb-4">
            {message}
          </p>
        )}
        <div className="ui-c-columns">
          <div className="ui-c-stack">
            {(locked || revision.status !== "ACTIVE") && (
              <div className="ui-c-note">
                <strong>
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
              </div>
            )}
            <WorkspaceCard spacing="body">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="ui-c-overline mb-[9px]">Revision summary</div>
                  <h2 className="mb-2 text-[22px] font-bold">
                    {revision.description || revision.identifier}
                  </h2>
                  <p className="ui-c-subtitle">
                    {revision.identifier} ·{" "}
                    {formatDateShort(revision.created_at)} ·{" "}
                    {project.project_number}
                  </p>
                </div>
                <WorkspaceStatus status={revision.status} />
              </div>
              <WorkspaceStats />
            </WorkspaceCard>
            <WorkspaceCard>
              <WorkspaceCardHeader
                title="Revision workspaces"
                subtitle="Move into the working areas for this revision"
              />
              <WorkspaceCardBody className="!py-2">
                <Link className="ui-c-item-row" href={href("documents")}>
                  <span className="flex items-center gap-2">
                    <Files size={19} />
                    <span>
                      <strong>Documents</strong>
                      <small>Source drawings and document processing</small>
                    </span>
                  </span>
                  <ChevronRight size={16} />
                </Link>
                <Link className="ui-c-item-row" href={href("equipment")}>
                  <span className="flex items-center gap-2">
                    <Cpu size={19} />
                    <span>
                      <strong>Engineering Model</strong>
                      <small>
                        Equipment, attributes, terminals and topology
                      </small>
                    </span>
                  </span>
                  <ChevronRight size={16} />
                </Link>
              </WorkspaceCardBody>
            </WorkspaceCard>
            <WorkspaceCard>
              <WorkspaceCardHeader
                title="Revision Information"
                subtitle="Lifecycle and ancestry of the selected revision"
                actions={
                  <Button
                    size="sm"
                    aria-label="Edit revision information"
                    disabled={locked || pending}
                    onClick={() => setEditing(true)}
                  >
                    <Pencil />
                    Edit
                  </Button>
                }
              />
              <WorkspaceCardBody>
                <WorkspaceDetails
                  items={[
                    {
                      label: "Identifier",
                      value: revision.identifier,
                      mono: true,
                    },
                    {
                      label: "Status",
                      value: <WorkspaceStatus status={revision.status} />,
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
              </WorkspaceCardBody>
            </WorkspaceCard>
          </div>
          <aside className="ui-c-stack">
            <WorkspaceCard spacing="body">
              <h2 className="mb-4 text-sm font-bold">Revision history</h2>
              <div className="ui-c-timeline">
                <div>
                  <h3>
                    {revision.status === "ACTIVE"
                      ? "Currently active"
                      : revision.status === "DRAFT"
                        ? "Draft created"
                        : "Superseded"}
                  </h3>
                  <p>Last updated {formatDateShort(revision.updated_at)}</p>
                </div>
                {revision.based_on_revision_id && (
                  <div>
                    <h3>Based on {source || "source revision"}</h3>
                    <p>
                      Inherited document and model snapshots where selected at
                      creation.
                    </p>
                  </div>
                )}
                <div>
                  <h3>Revision created</h3>
                  <p>{formatDateShort(revision.created_at)}</p>
                </div>
              </div>
            </WorkspaceCard>
            <WorkspaceCard spacing="body">
              <h2 className="mb-4 text-sm font-bold">Carry-forward history</h2>
              {["Documents", "Engineering model"].map((label) => (
                <div key={label} className="ui-c-item-row">
                  <span className="text-muted">{label}</span>
                  <strong>
                    {revision.based_on_revision_id
                      ? "Not recorded"
                      : "Not inherited"}
                  </strong>
                </div>
              ))}
              <p className="ui-c-note mt-4">
                Individual carry-forward choices are not included in revision
                metadata. Workspace counts are also unavailable here.
              </p>
            </WorkspaceCard>
          </aside>
        </div>
      </div>
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
          className="ui-c-dialog"
          title="Activate revision?"
          message={
            active
              ? `Revision ${active.identifier} will be superseded after Revision ${revision.identifier} is successfully activated.`
              : `Make Revision ${revision.identifier} the active revision?`
          }
          confirmLabel="Activate"
          onCancel={() => setConfirm(false)}
          onConfirm={() => void activate()}
        />
      )}
    </div>
  );
}
