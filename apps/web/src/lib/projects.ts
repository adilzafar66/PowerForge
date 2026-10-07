import { request, type ApiError } from "@/lib/api";

export type ProjectStatus = "ACTIVE" | "PAUSED" | "CANCELLED" | "ARCHIVED";
export type RevisionStatus = "DRAFT" | "ACTIVE" | "SUPERSEDED";

export type Project = {
  id: string;
  project_number: string;
  project_name: string;
  project_address: string | null;
  project_scope: string | null;
  client_name: string | null;
  description: string | null;
  engineer_names: string[];
  status: ProjectStatus;
  created_at: string;
  updated_at: string;
  archived_at: string | null;
  status_before_archive: ProjectStatus | null;
  created_by: string | null;
  active_revision_identifier: string | null;
};

export type Revision = {
  id: string;
  project_id: string;
  identifier: string;
  description: string | null;
  status: RevisionStatus;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  based_on_revision_id: string | null;
  based_on_identifier: string | null;
  /** Documents inherited at creation. Present only on the create response. */
  inherited_document_count?: number | null;
};

export type ProjectCreateInput = {
  project_number: string;
  project_name: string;
  project_address?: string | null;
  project_scope?: string | null;
  client_name?: string | null;
  description?: string | null;
  engineer_names?: string[];
};

export type ProjectUpdateInput = {
  project_name?: string;
  project_address?: string | null;
  project_scope?: string | null;
  client_name?: string | null;
  description?: string | null;
  engineer_names?: string[];
};

/**
 * Omitted keys are left out of the request body so the server applies its defaults
 * (ACTIVE revision as base, carry forward on). `based_on_revision_id: null` means
 * "no base" explicitly, which is different from omitting it.
 */
export type RevisionCreateInput = {
  identifier: string;
  description?: string | null;
  activate?: boolean;
  based_on_revision_id?: string | null;
  carry_forward_documents?: boolean;
};

export type { ApiError };

export async function listProjects(params?: {
  search?: string;
  status?: ProjectStatus | "";
  server?: boolean;
}): Promise<Project[]> {
  const query = new URLSearchParams();
  if (params?.search?.trim()) {
    query.set("search", params.search.trim());
  }
  if (params?.status) {
    query.set("status", params.status);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const body = await request<{ items: Project[] }>(`/api/projects${suffix}`, undefined, {
    server: params?.server,
  });
  return body.items;
}

export async function getProject(projectId: string, server = false): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}`, undefined, { server });
}

export async function createProject(input: ProjectCreateInput): Promise<Project> {
  return request<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateProject(projectId: string, input: ProjectUpdateInput): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function projectAction(
  projectId: string,
  action: "pause" | "resume" | "cancel" | "archive" | "unarchive",
): Promise<Project> {
  return request<Project>(`/api/projects/${projectId}/${action}`, { method: "POST" });
}

export async function listRevisions(projectId: string, server = false): Promise<Revision[]> {
  const body = await request<{ items: Revision[] }>(
    `/api/projects/${projectId}/revisions`,
    undefined,
    { server },
  );
  return body.items;
}

export async function getRevision(
  projectId: string,
  revisionId: string,
  server = false,
): Promise<Revision> {
  return request<Revision>(`/api/projects/${projectId}/revisions/${revisionId}`, undefined, {
    server,
  });
}

export async function createRevision(
  projectId: string,
  input: RevisionCreateInput,
): Promise<Revision> {
  return request<Revision>(`/api/projects/${projectId}/revisions`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function activateRevision(projectId: string, revisionId: string): Promise<Revision> {
  return request<Revision>(`/api/projects/${projectId}/revisions/${revisionId}/activate`, {
    method: "POST",
  });
}

export function formatDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  // Fixed locale + UTC so SSR and the browser render identical text (avoids hydration mismatch).
  return new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: "UTC",
  }).format(new Date(value));
}

export function formatDateShort(value: string | null): string {
  if (!value) {
    return "—";
  }
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
}

export function projectStatusBadgeVariant(
  status: ProjectStatus,
): "active" | "paused" | "cancelled" | "archived" | "default" {
  switch (status) {
    case "ACTIVE":
      return "active";
    case "PAUSED":
      return "paused";
    case "CANCELLED":
      return "cancelled";
    case "ARCHIVED":
      return "archived";
    default:
      return "default";
  }
}

export function revisionStatusBadgeVariant(
  status: RevisionStatus,
): "active" | "draft" | "superseded" | "default" {
  switch (status) {
    case "ACTIVE":
      return "active";
    case "DRAFT":
      return "draft";
    case "SUPERSEDED":
      return "superseded";
    default:
      return "default";
  }
}

export function parseEngineerNames(value: string): string[] {
  return value
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean);
}
