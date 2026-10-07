import { parseError, request, resolveBase } from "@/lib/api";
import type { Project, Revision } from "@/lib/projects";

export const DOCUMENT_TYPES = [
  "SINGLE_LINE_DIAGRAM",
  "ELECTRICAL_DRAWING",
  "PANEL_SCHEDULE",
  "EQUIPMENT_SCHEDULE",
  "CABLE_SCHEDULE",
  "TRANSFORMER_SHOP_DRAWING",
  "SWITCHGEAR_SHOP_DRAWING",
  "BREAKER_DOCUMENT",
  "MOTOR_DATA",
  "FAULT_DATA",
  "SPECIFICATION",
  "EQUIPMENT_PHOTO",
  "NAMEPLATE_PHOTO",
  "STUDY_DOCUMENT",
  "OTHER",
  "UNKNOWN",
] as const;

export type DocumentType = (typeof DOCUMENT_TYPES)[number];
export type DocumentOrigin = "UPLOADED" | "INHERITED";
export type RevisionDocumentStatus = "INCLUDED" | "REMOVED";
export type DocumentStatusFilter = RevisionDocumentStatus | "ALL";
export type DownloadDisposition = "attachment" | "inline";

/** The immutable file facts of a document. The storage key is never exposed by the API. */
export type DocumentSummary = {
  id: string;
  original_filename: string;
  mime_type: string;
  file_extension: string;
  size_bytes: number;
  sha256: string;
  uploaded_at: string;
};

export type RevisionDocument = {
  id: string;
  revision_id: string;
  document: DocumentSummary;
  origin: DocumentOrigin;
  inherited_from_revision_id: string | null;
  inherited_from_revision_identifier: string | null;
  status: RevisionDocumentStatus;
  document_type: DocumentType;
  document_number: string | null;
  description: string | null;
  notes: string | null;
  added_at: string;
  removed_at: string | null;
};

export type UploadResult = RevisionDocument & {
  duplicate_detected: boolean;
  duplicate_document_ids: string[];
};

export type DownloadUrl = {
  url: string;
  expires_at: string;
  filename: string;
};

export type DocumentListFilters = {
  /** Defaults to INCLUDED on the server. */
  status?: DocumentStatusFilter;
  document_type?: DocumentType | "";
  origin?: DocumentOrigin | "";
  search?: string;
};

/**
 * Keys that are left out are not changed. A text field set to `null` is cleared.
 * `document_type` cannot be null.
 */
export type DocumentUpdateInput = {
  document_type?: DocumentType;
  document_number?: string | null;
  description?: string | null;
  notes?: string | null;
};

/** The source association plus optional metadata overrides, with the same null rules. */
export type ReuseInput = DocumentUpdateInput & {
  source_revision_document_id: string;
};

export const DOCUMENT_TYPE_LABELS: Record<DocumentType, string> = {
  SINGLE_LINE_DIAGRAM: "Single Line Diagram",
  ELECTRICAL_DRAWING: "Electrical Drawing",
  PANEL_SCHEDULE: "Panel Schedule",
  EQUIPMENT_SCHEDULE: "Equipment Schedule",
  CABLE_SCHEDULE: "Cable Schedule",
  TRANSFORMER_SHOP_DRAWING: "Transformer Shop Drawing",
  SWITCHGEAR_SHOP_DRAWING: "Switchgear Shop Drawing",
  BREAKER_DOCUMENT: "Breaker Document",
  MOTOR_DATA: "Motor Data",
  FAULT_DATA: "Fault Data",
  SPECIFICATION: "Specification",
  EQUIPMENT_PHOTO: "Equipment Photo",
  NAMEPLATE_PHOTO: "Nameplate Photo",
  STUDY_DOCUMENT: "Study Document",
  OTHER: "Other",
  UNKNOWN: "Unclassified",
};

export const DOCUMENT_TYPE_OPTIONS: { value: DocumentType; label: string }[] = DOCUMENT_TYPES.map(
  (value) => ({ value, label: DOCUMENT_TYPE_LABELS[value] }),
);

export function documentTypeLabel(type: DocumentType): string {
  return DOCUMENT_TYPE_LABELS[type] ?? type;
}

export function originLabel(origin: DocumentOrigin): string {
  return origin === "INHERITED" ? "Inherited" : "Uploaded";
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(1)} KB`;
  }
  if (bytes < 1024 * 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
}

type MutabilityContext = {
  project: Pick<Project, "status">;
  revision: Pick<Revision, "status">;
};

/** Why the document package cannot be changed, or null when it can. The backend is authoritative. */
export function readOnlyReason({ project, revision }: MutabilityContext): string | null {
  if (project.status === "ARCHIVED") {
    return "This project is archived, so its documents are read-only.";
  }
  if (project.status === "CANCELLED") {
    return "This project is cancelled, so its documents are read-only.";
  }
  if (revision.status === "SUPERSEDED") {
    return "This revision is superseded and is read-only.";
  }
  return null;
}

/** The single rule for showing mutation controls (upload, edit, remove, restore, reuse). */
export function canMutate(context: MutabilityContext): boolean {
  return readOnlyReason(context) === null;
}

/** Browsers cannot render TIFF, so it is offered as a download only. */
export function canOpenInline(document: Pick<DocumentSummary, "mime_type">): boolean {
  return document.mime_type.toLowerCase() !== "image/tiff";
}

function documentsPath(projectId: string, revisionId: string): string {
  return `/api/projects/${projectId}/revisions/${revisionId}/documents`;
}

export async function listDocuments(
  projectId: string,
  revisionId: string,
  filters: DocumentListFilters = {},
): Promise<RevisionDocument[]> {
  const query = new URLSearchParams();
  if (filters.status) {
    query.set("status", filters.status);
  }
  if (filters.document_type) {
    query.set("document_type", filters.document_type);
  }
  if (filters.origin) {
    query.set("origin", filters.origin);
  }
  if (filters.search?.trim()) {
    query.set("search", filters.search.trim());
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  const body = await request<{ items: RevisionDocument[] }>(
    `${documentsPath(projectId, revisionId)}${suffix}`,
  );
  return body.items;
}

export async function getDocument(
  projectId: string,
  revisionId: string,
  revisionDocumentId: string,
): Promise<RevisionDocument> {
  return request<RevisionDocument>(
    `${documentsPath(projectId, revisionId)}/${revisionDocumentId}`,
  );
}

export async function updateDocument(
  projectId: string,
  revisionId: string,
  revisionDocumentId: string,
  input: DocumentUpdateInput,
): Promise<RevisionDocument> {
  return request<RevisionDocument>(`${documentsPath(projectId, revisionId)}/${revisionDocumentId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function removeDocument(
  projectId: string,
  revisionId: string,
  revisionDocumentId: string,
): Promise<RevisionDocument> {
  return request<RevisionDocument>(
    `${documentsPath(projectId, revisionId)}/${revisionDocumentId}/remove`,
    { method: "POST" },
  );
}

export async function restoreDocument(
  projectId: string,
  revisionId: string,
  revisionDocumentId: string,
): Promise<RevisionDocument> {
  return request<RevisionDocument>(
    `${documentsPath(projectId, revisionId)}/${revisionDocumentId}/restore`,
    { method: "POST" },
  );
}

export async function reuseDocument(
  projectId: string,
  revisionId: string,
  input: ReuseInput,
): Promise<RevisionDocument> {
  return request<RevisionDocument>(`${documentsPath(projectId, revisionId)}/reuse`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

/** A fresh signed URL on every call; callers must not cache or log it. */
export async function getDownloadUrl(
  projectId: string,
  revisionId: string,
  revisionDocumentId: string,
  disposition: DownloadDisposition = "attachment",
): Promise<DownloadUrl> {
  return request<DownloadUrl>(
    `${documentsPath(projectId, revisionId)}/${revisionDocumentId}/download-url?disposition=${disposition}`,
  );
}

const DEFAULT_MAX_UPLOAD_BYTES = 262_144_000;

function configuredMaxUploadBytes(): number {
  const value = Number(process.env.NEXT_PUBLIC_MAX_UPLOAD_BYTES);
  return Number.isFinite(value) && value > 0 ? value : DEFAULT_MAX_UPLOAD_BYTES;
}

/** Advisory size hint for the browser. The API's own limit is authoritative. */
export const MAX_UPLOAD_BYTES = configuredMaxUploadBytes();

const UPLOAD_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff"];
export const UPLOAD_ACCEPT = UPLOAD_EXTENSIONS.join(",");

/** A quick pre-check so obvious mistakes fail without a round trip. The server still validates. */
export function validateUploadFile(file: File, maxBytes: number = MAX_UPLOAD_BYTES): string | null {
  const name = file.name;
  const dot = name.lastIndexOf(".");
  const extension = dot >= 0 ? name.slice(dot).toLowerCase() : "";
  if (!UPLOAD_EXTENSIONS.includes(extension)) {
    return `${name}: unsupported file type. Use PDF, PNG, JPEG or TIFF.`;
  }
  if (file.size === 0) {
    return `${name}: the file is empty.`;
  }
  if (file.size > maxBytes) {
    return `${name}: larger than the ${formatFileSize(maxBytes)} limit.`;
  }
  return null;
}

export type UploadMetadata = {
  document_type?: DocumentType;
  document_number?: string | null;
  description?: string | null;
  notes?: string | null;
};

export type UploadOptions = {
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
};

/**
 * Uploads one file as its own request. XMLHttpRequest is used because `fetch` cannot report
 * upload progress. Failures are thrown in the same shape as `request`, with status 0 for
 * network errors and an `AbortError` when the signal fires.
 */
export function uploadDocument(
  projectId: string,
  revisionId: string,
  file: File,
  metadata: UploadMetadata = {},
  { onProgress, signal }: UploadOptions = {},
): Promise<UploadResult> {
  return new Promise<UploadResult>((resolve, reject) => {
    if (signal?.aborted) {
      reject(abortError());
      return;
    }

    const form = new FormData();
    form.append("file", file, file.name);
    for (const key of ["document_type", "document_number", "description", "notes"] as const) {
      const value = metadata[key];
      if (value !== undefined && value !== null) {
        form.append(key, value);
      }
    }

    const xhr = new XMLHttpRequest();
    const onAbort = () => xhr.abort();
    const cleanup = () => signal?.removeEventListener("abort", onAbort);

    xhr.open("POST", `${resolveBase()}${documentsPath(projectId, revisionId)}`);
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        onProgress?.(Math.min(100, Math.round((event.loaded / event.total) * 100)));
      }
    };
    xhr.onload = async () => {
      cleanup();
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as UploadResult);
        } catch {
          reject(new Error("The server returned an unreadable response."));
        }
        return;
      }
      const apiError = await parseError(
        new Response(xhr.responseText, { status: xhr.status, statusText: xhr.statusText }),
      );
      reject(Object.assign(new Error(apiError.detail), { apiError, status: xhr.status }));
    };
    xhr.onerror = () => {
      cleanup();
      const detail = "Could not reach the server. Check your connection and retry.";
      reject(Object.assign(new Error(detail), { apiError: { detail }, status: 0 }));
    };
    xhr.onabort = () => {
      cleanup();
      reject(abortError());
    };

    signal?.addEventListener("abort", onAbort, { once: true });
    xhr.send(form);
  });
}

function abortError(): Error {
  const error = new Error("Upload cancelled.");
  error.name = "AbortError";
  return error;
}
