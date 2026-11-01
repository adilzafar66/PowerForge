"use client";
import { Card } from "@/components/ui/card";
import { SegmentedControl } from "@/components/ui/segmented-control";
import { cn } from "@/lib/utils";
import {
  RegisterToolbar,
  RegisterTable,
  RegisterHeader,
  RegisterRow,
  RegisterCell,
  RegisterFooter,
} from "@/components/ui/register-table";
import {
  WorkspaceRoot,
  WorkspaceContent,
} from "@/components/ui/workspace-layout";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Plus, Search, RefreshCw, ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { keys } from "@/lib/query-keys";
import { AsyncState } from "@/components/ui/async-state";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { Badge } from "@/components/ui/badge";
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
    <WorkspaceRoot>
      <PageHeader
        title="Projects"
        description={`${projects.length} projects in workspace`}
        actions={
          <Button asChild variant="primary" presentation="workspace">
            <Link href="/projects/new">
              <Plus />
              New Project
            </Link>
          </Button>
        }
        presentation="workspace"
      />
      <WorkspaceContent className="!pt-[30px]">
        <AsyncState
          pending={query.isPending}
          error={query.error}
          retry={refresh}
        />
        <Card presentation="workspace" as="div">
          <RegisterToolbar>
            <div className="flex gap-[10px] flex-wrap items-center">
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
              <SegmentedControl
                presentation="projects"
                label="Project status"
                value={statusFilter}
                onChange={setStatusFilter}
                options={(
                  ["ALL", "ACTIVE", "PAUSED", "CANCELLED", "ARCHIVED"] as const
                ).map((value) => ({
                  value,
                  label:
                    value === "ALL"
                      ? "All"
                      : value.charAt(0) + value.slice(1).toLowerCase(),
                  count: statusCounts[value] ?? 0,
                }))}
              />
            </div>
            <Button
              size="sm"
              disabled={loading}
              onClick={() => void refresh()}
              presentation="workspace"
              variant="outline"
            >
              <RefreshCw />
              {loading ? "Refreshing…" : "Refresh"}
            </Button>
          </RegisterToolbar>
          <div className="overflow-x-auto">
            <RegisterTable>
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
                    <RegisterHeader key={label} scope="col" variant="projects">
                      {label}
                    </RegisterHeader>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((project) => (
                  <RegisterRow
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
                    <RegisterCell
                      className="font-mono !text-[11px]"
                      variant="projects"
                    >
                      {project.project_number}
                    </RegisterCell>
                    <RegisterCell variant="projects">
                      <Link
                        href={`/projects/${project.id}`}
                        className={cn(
                          "project-name",
                          "text-workspace-body text-ink font-semibold",
                        )}
                      >
                        {project.project_name}
                      </Link>
                      <small className="block text-muted text-workspace-micro mt-[5px]">
                        {project.project_address || "No address specified"}
                      </small>
                    </RegisterCell>
                    <RegisterCell variant="projects">
                      {project.client_name || "—"}
                    </RegisterCell>
                    <RegisterCell
                      className="font-mono !text-[11px]"
                      variant="projects"
                    >
                      {project.active_revision_identifier || "—"}
                    </RegisterCell>
                    <RegisterCell variant="projects">
                      <Badge status={project.status} presentation="workspace" />
                    </RegisterCell>
                    <RegisterCell
                      className="whitespace-nowrap"
                      variant="projects"
                    >
                      {formatDateShort(project.updated_at)}
                    </RegisterCell>
                    <RegisterCell variant="projects">
                      <ChevronRight size={14} />
                    </RegisterCell>
                  </RegisterRow>
                ))}
              </tbody>
            </RegisterTable>
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
                  presentation="workspace"
                  variant="outline"
                >
                  Clear filters
                </Button>
              )}
            </div>
          )}
          <RegisterFooter>
            <span>
              Showing {filtered.length} of {projects.length} projects
            </span>
            <span>Project register</span>
          </RegisterFooter>
        </Card>
        <p className="text-muted text-workspace-caption leading-[var(--pf-leading-hint)] mt-4">
          Select a project to view its overview and edit its metadata. Status
          filters and search update immediately.
        </p>
      </WorkspaceContent>
    </WorkspaceRoot>
  );
}
