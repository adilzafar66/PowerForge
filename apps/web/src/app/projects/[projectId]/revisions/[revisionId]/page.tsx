import Link from "next/link";
import { Suspense } from "react";
import { ArrowLeft } from "lucide-react";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ReadOnlyBanner } from "@/components/read-only-banner";
import { RevisionWorkspace } from "@/components/revision-workspace";
import { RevisionLineage } from "@/components/revision-lineage";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Mono } from "@/components/ui/mono";
import { canMutate } from "@/lib/documents";
import {
  formatDateShort,
  getProject,
  getRevision,
  listRevisions,
} from "@/lib/projects";

export const dynamic = "force-dynamic";

export default async function RevisionPage({
  params,
}: {
  params: Promise<{ projectId: string; revisionId: string }>;
}) {
  const { projectId, revisionId } = await params;
  try {
    const [project, revision, revisions] = await Promise.all([
      getProject(projectId, true),
      getRevision(projectId, revisionId, true),
      listRevisions(projectId, true),
    ]);

    return (
      <AppShell project={project} revision={revision} revisions={revisions}>
        <div className="w-full min-w-0 px-4 py-6 md:px-8 md:py-8">
          <div className="mb-7 flex items-start justify-between gap-4">
            <div>
              <div className="mb-1.5 flex items-center gap-2.5">
                <Mono className="text-slate-400">{project.project_number}</Mono>
                <span className="text-slate-200">·</span>
                <Mono className="text-slate-400">{revision.identifier}</Mono>
                <Badge status={revision.status} kind="revision" />
              </div>
              <h1 className="text-[29px] font-bold tracking-tight text-slate-900">
                {revision.description || revision.identifier}
              </h1>
              <p className="mt-1 text-[14px] font-medium text-slate-500">
                {project.project_name}
              </p>
              {revision.based_on_revision_id ? (
                <RevisionLineage
                  basedOnIdentifier={revision.based_on_identifier}
                  href={`/projects/${project.id}/revisions/${revision.based_on_revision_id}`}
                  className="mt-1 block text-[13px]"
                />
              ) : null}
            </div>
            <Link
              href={`/projects/${project.id}`}
              className="mt-1.5 flex items-center gap-1.5 text-[13px] font-medium text-slate-400 transition-colors hover:text-slate-700"
            >
              <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.7} />
              Back to project
            </Link>
          </div>

          {revision.description ? (
            <Card className="mb-5 px-5 py-4">
              <p className="mb-2 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Notes
              </p>
              <p className="text-[13.5px] leading-relaxed text-slate-700">
                {revision.description}
              </p>
            </Card>
          ) : null}

          <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { label: "Created By", value: revision.created_by || "—" },
              { label: "Created", value: formatDateShort(revision.created_at) },
              {
                label: "Last Updated",
                value: formatDateShort(revision.updated_at),
              },
            ].map(({ label, value }) => (
              <Card key={label} className="px-4 py-3.5">
                <p className="mb-1.5 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                  {label}
                </p>
                <p className="text-[14px] font-semibold text-slate-700">
                  {value}
                </p>
              </Card>
            ))}
          </div>

          <ReadOnlyBanner project={project} revision={revision} />
          <Suspense fallback={null}>
            <RevisionWorkspace
              projectId={project.id}
              revisionId={revision.id}
              canMutate={canMutate({ project, revision })}
            />
          </Suspense>
        </div>
      </AppShell>
    );
  } catch {
    notFound();
  }
}
