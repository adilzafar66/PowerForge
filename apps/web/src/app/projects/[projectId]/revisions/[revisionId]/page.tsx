import Link from "next/link";
import { ArrowLeft, FileText } from "lucide-react";
import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { Badge } from "@/components/ui/badge";
import { Breadcrumb } from "@/components/ui/breadcrumb";
import { Card } from "@/components/ui/card";
import { Mono } from "@/components/ui/mono";
import { formatDateShort, getProject, getRevision } from "@/lib/projects";

export const dynamic = "force-dynamic";

export default async function RevisionPlaceholderPage({
  params,
}: {
  params: Promise<{ projectId: string; revisionId: string }>;
}) {
  const { projectId, revisionId } = await params;
  try {
    const [project, revision] = await Promise.all([
      getProject(projectId, true),
      getRevision(projectId, revisionId, true),
    ]);

    return (
      <AppShell active="projects">
        <div className="mx-auto max-w-screen-lg px-8 py-8">
          <Breadcrumb
            items={[
              { label: "Projects", href: "/" },
              { label: project.project_name, href: `/projects/${project.id}` },
              { label: revision.identifier },
            ]}
          />

          <div className="mb-7 flex items-start justify-between gap-4">
            <div>
              <div className="mb-1.5 flex items-center gap-2.5">
                <Mono className="text-slate-400">{project.project_number}</Mono>
                <span className="text-slate-200">·</span>
                <Mono className="text-slate-400">{revision.identifier}</Mono>
                <Badge status={revision.status} kind="revision" />
              </div>
              <h1 className="text-[22px] font-bold tracking-tight text-slate-900">
                {revision.description || revision.identifier}
              </h1>
              <p className="mt-1 text-[14px] font-medium text-slate-500">{project.project_name}</p>
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
              <p className="text-[13.5px] leading-relaxed text-slate-700">{revision.description}</p>
            </Card>
          ) : null}

          <div className="mb-8 grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              { label: "Created By", value: revision.created_by || "—" },
              { label: "Created", value: formatDateShort(revision.created_at) },
              { label: "Last Updated", value: formatDateShort(revision.updated_at) },
            ].map(({ label, value }) => (
              <Card key={label} className="px-4 py-3.5">
                <p className="mb-1.5 text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                  {label}
                </p>
                <p className="text-[14px] font-semibold text-slate-700">{value}</p>
              </Card>
            ))}
          </div>

          <div className="flex flex-col items-center justify-center gap-4 rounded-2xl border-2 border-dashed border-slate-200 bg-white p-16 text-center">
            <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
              <FileText className="h-5 w-5" strokeWidth={1.4} />
            </div>
            <div>
              <p className="text-[15px] font-semibold text-slate-600">Documents & Models</p>
              <p className="mt-1 text-[13px] text-slate-400">
                Single-line diagrams, studies, and reports will appear here.
              </p>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-[11.5px] font-bold tracking-widest text-slate-400 uppercase">
              Coming Soon
            </span>
          </div>
        </div>
      </AppShell>
    );
  } catch {
    notFound();
  }
}
