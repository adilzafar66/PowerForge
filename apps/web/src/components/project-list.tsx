"use client";
import { WorkspaceCard } from "@/components/ui/workspace-patterns";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Search, RefreshCw, ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AsyncState } from "@/components/ui/async-state";

import {
  WorkspaceButton as Button,
  WorkspaceHeader,
  WorkspaceStatus,
} from "@/components/ui-c-workspace";
import {
  formatDateShort,
  listProjects,
  type Project,
  type ProjectStatus,
} from "@/lib/projects";

type StatusFilter = ProjectStatus | "ALL";
const EMPTY_PROJECTS: Project[] = [];

export function ProjectList({
  initialProjects,
}: {
  initialProjects?: Project[];
}) {
  const router = useRouter();
  const query = useQuery({
    queryKey: keys.projects,
    queryFn: () => listProjects(),
    initialData: initialProjects,
  });
  const projects = query.data ?? EMPTY_PROJECTS;
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("ALL");
  const loading = query.isFetching;

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
      const matchStatus =
        statusFilter === "ALL" || project.status === statusFilter;
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
    await query.refetch();
  }

  return (
    <div className="ui-c">
      <WorkspaceHeader
        title="Projects"
        subtitle={`${projects.length} projects in workspace`}
        actions={
          <Button asChild variant="primary">
            <Link href="/projects/new">
              <Plus />
              New Project
            </Link>
          </Button>
        }
      />
      <div className="ui-c-content !pt-[30px]">
        <AsyncState
          pending={query.isPending}
          error={query.error}
          retry={refresh}
        />
        <WorkspaceCard as="div">
          <div className="ui-c-toolbar">
            <div className="ui-c-toolbar-controls">
              <label className="flex min-h-[41px] items-center gap-[10px] rounded-lg border border-border bg-[#F9FBFC] px-[13px]">
                <Search size={16} className="text-muted" />
                <input
                  className="min-h-[39px] w-[245px] max-w-full border-0 bg-transparent text-xs outline-none"
                  aria-label="Search projects"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search number, name, client, or address"
                />
              </label>
              <div
                className="ui-c-tabs ui-c-project-tabs"
                role="group"
                aria-label="Project status"
              >
                {(
                  ["ALL", "ACTIVE", "PAUSED", "CANCELLED", "ARCHIVED"] as const
                ).map((value) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={statusFilter === value}
                    onClick={() => setStatusFilter(value)}
                  >
                    {value === "ALL"
                      ? "All"
                      : value.charAt(0) + value.slice(1).toLowerCase()}{" "}
                    <span className="ml-1 opacity-70">
                      {statusCounts[value] ?? 0}
                    </span>
                  </button>
                ))}
              </div>
            </div>
            <Button size="sm" disabled={loading} onClick={() => void refresh()}>
              <RefreshCw />
              {loading ? "Refreshing…" : "Refresh"}
            </Button>
          </div>
          <div className="ui-c-table-scroll">
            <table className="ui-c-table ui-c-project-table">
              <colgroup>
                {["12%", "33%", "14%", "13%", "14%", "12%", "2%"].map(
                  (width, index) => (
                    <col key={index} style={{ width }} />
                  ),
                )}
              </colgroup>
              <thead>
                <tr>
                  {[
                    "Number",
                    "Project",
                    "Client",
                    "Active Rev.",
                    "Status",
                    "Updated",
                    "",
                  ].map((label) => (
                    <th key={label} scope="col">
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((project) => (
                  <tr
                    key={project.id}
                    tabIndex={0}
                    aria-label={`Open ${project.project_name}`}
                    onKeyDown={(e) => {
                      if (
                        e.target === e.currentTarget &&
                        (e.key === "Enter" || e.key === " ")
                      ) {
                        e.preventDefault();
                        router.push(`/projects/${project.id}`);
                      }
                    }}
                    onClick={(e) => {
                      if (!(e.target as HTMLElement).closest("a"))
                        router.push(`/projects/${project.id}`);
                    }}
                  >
                    <td className="font-mono !text-[11px]">
                      {project.project_number}
                    </td>
                    <td>
                      <Link
                        className="project-name"
                        href={`/projects/${project.id}`}
                      >
                        {project.project_name}
                      </Link>
                      <small>
                        {project.project_address || "No address specified"}
                      </small>
                    </td>
                    <td>{project.client_name || "—"}</td>
                    <td className="font-mono !text-[11px]">
                      {project.active_revision_identifier || "—"}
                    </td>
                    <td>
                      <WorkspaceStatus status={project.status} />
                    </td>
                    <td className="whitespace-nowrap">
                      {formatDateShort(project.updated_at)}
                    </td>
                    <td>
                      <ChevronRight size={14} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {query.data && filtered.length === 0 && (
            <div className="px-6 py-[70px] text-center">
              <h2 className="mb-2 text-lg font-bold">
                {projects.length ? "No matching projects" : "No projects yet"}
              </h2>
              <p className="text-xs text-muted">
                {projects.length
                  ? "Try a different search or status filter."
                  : "Create the first project to begin."}
              </p>
              {projects.length > 0 && (
                <Button
                  className="mt-4"
                  onClick={() => {
                    setSearch("");
                    setStatusFilter("ALL");
                  }}
                >
                  Clear filters
                </Button>
              )}
            </div>
          )}
          <div className="ui-c-table-footer">
            <span>
              Showing {filtered.length} of {projects.length} projects
            </span>
            <span>Project register</span>
          </div>
        </WorkspaceCard>
        <p className="ui-c-help">
          Select a project to view its overview and edit its metadata. Status
          filters and search update immediately.
        </p>
      </div>
    </div>
  );
}
