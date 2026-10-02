"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, Plus } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Mono } from "@/components/ui/mono";
import { PageHeader } from "@/components/ui/page-header";
import { SearchField } from "@/components/ui/search-field";
import { SegmentedControl } from "@/components/ui/segmented-control";
import {
  formatDateShort,
  listProjects,
  type Project,
  type ProjectStatus,
} from "@/lib/projects";

type StatusFilter = ProjectStatus | "ALL";

export function ProjectList({ initialProjects }: { initialProjects: Project[] }) {
  const router = useRouter();
  const [projects, setProjects] = useState(initialProjects);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { ALL: projects.length };
    for (const project of projects) {
      counts[project.status] = (counts[project.status] ?? 0) + 1;
    }
    return counts;
  }, [projects]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return projects.filter((project) => {
      const matchStatus = statusFilter === "ALL" || project.status === statusFilter;
      const matchSearch =
        !query ||
        project.project_number.toLowerCase().includes(query) ||
        project.project_name.toLowerCase().includes(query) ||
        (project.client_name ?? "").toLowerCase().includes(query) ||
        (project.project_address ?? "").toLowerCase().includes(query);
      return matchStatus && matchSearch;
    });
  }, [projects, search, statusFilter]);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const items = await listProjects();
      setProjects(items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-screen-xl px-8 py-8">
      <PageHeader
        title="Projects"
        description={`${projects.length} projects in workspace`}
        actions={
          <Button asChild>
            <Link href="/projects/new">
              <Plus className="h-[13px] w-[13px]" strokeWidth={2} />
              New Project
            </Link>
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <SearchField
          value={search}
          onChange={setSearch}
          placeholder="Search by number, name, client, or address…"
        />
        <SegmentedControl
          value={statusFilter}
          onChange={setStatusFilter}
          options={[
            { value: "ALL", label: "All", count: statusCounts.ALL ?? 0 },
            { value: "ACTIVE", label: "Active", count: statusCounts.ACTIVE ?? 0 },
            { value: "PAUSED", label: "Paused", count: statusCounts.PAUSED ?? 0 },
            { value: "CANCELLED", label: "Cancelled", count: statusCounts.CANCELLED ?? 0 },
            { value: "ARCHIVED", label: "Archived", count: statusCounts.ARCHIVED ?? 0 },
          ]}
        />
        <Button type="button" variant="ghost" size="sm" disabled={loading} onClick={() => void refresh()}>
          {loading ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {error ? <p className="mb-4 text-[13px] text-red-600">{error}</p> : null}

      <Card className="overflow-hidden">
        <table className="w-full text-[13.5px]">
          <thead>
            <tr className="border-b border-slate-100">
              <th className="w-36 px-5 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Number
              </th>
              <th className="px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Project
              </th>
              <th className="w-44 px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Client
              </th>
              <th className="hidden w-40 px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase xl:table-cell">
                Active Rev.
              </th>
              <th className="w-28 px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase">
                Status
              </th>
              <th className="hidden w-32 px-4 py-3 text-left text-[11px] font-bold tracking-widest text-slate-400 uppercase lg:table-cell">
                Updated
              </th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7}>
                  <div className="flex flex-col items-center gap-2 py-20">
                    <span className="text-[28px] opacity-20">◎</span>
                    <p className="text-[13.5px] font-medium text-slate-400">
                      {projects.length === 0
                        ? "No projects yet. Create the first project to begin."
                        : "No projects match your filter."}
                    </p>
                    {projects.length > 0 ? (
                      <button
                        type="button"
                        onClick={() => {
                          setSearch("");
                          setStatusFilter("ALL");
                        }}
                        className="mt-1 cursor-pointer text-[12.5px] text-accent hover:underline"
                      >
                        Clear filters
                      </button>
                    ) : null}
                  </div>
                </td>
              </tr>
            ) : (
              filtered.map((project, index) => (
                <tr
                  key={project.id}
                  onClick={() => router.push(`/projects/${project.id}`)}
                  className={`group cursor-pointer transition-colors hover:bg-blue-50/50 ${
                    index !== 0 ? "border-t border-slate-100" : ""
                  }`}
                >
                  <td className="px-5 py-3.5">
                    <Mono className="tracking-tight text-slate-400">{project.project_number}</Mono>
                  </td>
                  <td className="px-4 py-3.5">
                    <span className="font-semibold text-slate-900 transition-colors group-hover:text-accent">
                      {project.project_name}
                    </span>
                    {project.project_address ? (
                      <p className="mt-0.5 max-w-xs truncate text-[12px] text-slate-400">
                        {project.project_address}
                      </p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3.5 font-medium text-slate-600">
                    {project.client_name || "—"}
                  </td>
                  <td className="hidden px-4 py-3.5 xl:table-cell">
                    {project.active_revision_identifier ? (
                      <Mono className="text-slate-400">{project.active_revision_identifier}</Mono>
                    ) : (
                      <span className="text-slate-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3.5">
                    <Badge status={project.status} />
                  </td>
                  <td className="hidden px-4 py-3.5 text-[12.5px] text-slate-400 lg:table-cell">
                    {formatDateShort(project.updated_at)}
                  </td>
                  <td className="px-3 py-3.5 text-slate-300 transition-colors group-hover:text-accent">
                    <ChevronRight className="h-[13px] w-[13px]" strokeWidth={1.8} />
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
