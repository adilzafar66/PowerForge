import { apiBaseUrl, apiBaseUrlServer } from "@/lib/health";

export type ApiError = {
  detail: string;
  code?: string;
  /** Set on a `document_already_in_revision` conflict so the UI can offer "Restore". */
  existing_revision_document_id?: string;
  existing_status?: string;
};

type ErrorBody = {
  detail?:
    | string
    | { msg?: string }[]
    | {
        detail?: string;
        code?: string;
        existing_revision_document_id?: string;
        existing_status?: string;
      };
};

export function resolveBase(server = false): string {
  return server ? apiBaseUrlServer() : apiBaseUrl();
}

export async function parseError(response: Response): Promise<ApiError> {
  const fallback = response.statusText || "Request failed";
  try {
    const body = (await response.json()) as ErrorBody;
    const detail = body.detail;
    if (typeof detail === "string") {
      return { detail };
    }
    if (Array.isArray(detail)) {
      const messages = detail.map((item) => item?.msg).filter((msg): msg is string => !!msg);
      return { detail: messages.length > 0 ? messages.join("; ") : fallback };
    }
    if (detail && typeof detail === "object") {
      const error: ApiError = { detail: detail.detail ?? fallback, code: detail.code };
      if (detail.existing_revision_document_id) {
        error.existing_revision_document_id = detail.existing_revision_document_id;
      }
      if (detail.existing_status) {
        error.existing_status = detail.existing_status;
      }
      return error;
    }
    return { detail: fallback };
  } catch {
    return { detail: fallback };
  }
}

export async function request<T>(
  path: string,
  init?: RequestInit,
  options?: { server?: boolean },
): Promise<T> {
  const base = resolveBase(options?.server);
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    const error = await parseError(response);
    throw Object.assign(new Error(error.detail), { apiError: error, status: response.status });
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** The HTTP status and structured error of a failed `request`, or nulls for other errors. */
export function apiErrorOf(err: unknown): {
  status: number | null;
  code: string | null;
  detail: string;
  error: ApiError | null;
} {
  const detail = err instanceof Error ? err.message : "Request failed";
  if (err && typeof err === "object" && "apiError" in err) {
    const { apiError, status } = err as { apiError: ApiError; status?: number };
    return { status: status ?? null, code: apiError.code ?? null, detail, error: apiError };
  }
  return { status: null, code: null, detail, error: null };
}
