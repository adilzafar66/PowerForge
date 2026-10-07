import { afterEach, describe, expect, it, vi } from "vitest";

import { apiErrorOf } from "./api";
import {
  DOCUMENT_TYPES,
  canMutate,
  canOpenInline,
  readOnlyReason,
  DOCUMENT_TYPE_LABELS,
  DOCUMENT_TYPE_OPTIONS,
  documentTypeLabel,
  formatFileSize,
  getDocument,
  getDownloadUrl,
  listDocuments,
  originLabel,
  removeDocument,
  restoreDocument,
  reuseDocument,
  updateDocument,
} from "./documents";

const P = "11111111-1111-1111-1111-111111111111";
const R = "22222222-2222-2222-2222-222222222222";
const D = "33333333-3333-3333-3333-333333333333";
const BASE = `/api/projects/${P}/revisions/${R}/documents`;

function respond(body: unknown, status = 200) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    status,
    json: async () => body,
  } as Response);
}

function lastCall(fetchMock: ReturnType<typeof respond>) {
  const [url, init] = fetchMock.mock.calls.at(-1)!;
  const text = String(url);
  return {
    path: text.slice(text.indexOf("/api/")),
    method: init?.method ?? "GET",
    body: init?.body === undefined ? undefined : JSON.parse(String(init.body)),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("document labels and formatting", () => {
  it("has a label for every backend document type, with UNKNOWN shown as Unclassified", () => {
    expect(DOCUMENT_TYPES).toHaveLength(16);
    expect(new Set(DOCUMENT_TYPES).size).toBe(16);
    expect(Object.keys(DOCUMENT_TYPE_LABELS).sort()).toEqual([...DOCUMENT_TYPES].sort());
    expect(DOCUMENT_TYPE_OPTIONS.map((option) => option.value)).toEqual([...DOCUMENT_TYPES]);
    expect(documentTypeLabel("UNKNOWN")).toBe("Unclassified");
    expect(documentTypeLabel("SINGLE_LINE_DIAGRAM")).toBe("Single Line Diagram");
  });

  it("labels origins", () => {
    expect(originLabel("UPLOADED")).toBe("Uploaded");
    expect(originLabel("INHERITED")).toBe("Inherited");
  });

  it("formats file sizes", () => {
    expect(formatFileSize(0)).toBe("0 B");
    expect(formatFileSize(1023)).toBe("1023 B");
    expect(formatFileSize(1024)).toBe("1.0 KB");
    expect(formatFileSize(1536)).toBe("1.5 KB");
    expect(formatFileSize(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatFileSize(250 * 1024 * 1024)).toBe("250.0 MB");
    expect(formatFileSize(3 * 1024 ** 3)).toBe("3.0 GB");
  });
});

describe("listDocuments", () => {
  it("requests the revision-scoped list with no query when no filters are given", async () => {
    const fetchMock = respond({ items: [{ id: D }] });

    const items = await listDocuments(P, R);

    expect(items).toEqual([{ id: D }]);
    expect(lastCall(fetchMock)).toEqual({ path: BASE, method: "GET", body: undefined });
  });

  it("passes the filters and drops empty ones", async () => {
    const fetchMock = respond({ items: [] });

    await listDocuments(P, R, {
      status: "ALL",
      document_type: "PANEL_SCHEDULE",
      origin: "INHERITED",
      search: "  sld  ",
    });
    expect(lastCall(fetchMock).path).toBe(
      `${BASE}?status=ALL&document_type=PANEL_SCHEDULE&origin=INHERITED&search=sld`,
    );

    await listDocuments(P, R, { status: "REMOVED", document_type: "", origin: "", search: "  " });
    expect(lastCall(fetchMock).path).toBe(`${BASE}?status=REMOVED`);
  });
});

describe("document actions", () => {
  it("gets one document", async () => {
    const fetchMock = respond({ id: D });
    await getDocument(P, R, D);
    expect(lastCall(fetchMock)).toEqual({ path: `${BASE}/${D}`, method: "GET", body: undefined });
  });

  it("PATCHes only the provided keys and passes null through to clear a field", async () => {
    const fetchMock = respond({ id: D });

    await updateDocument(P, R, D, { notes: null });
    expect(lastCall(fetchMock)).toEqual({
      path: `${BASE}/${D}`,
      method: "PATCH",
      body: { notes: null },
    });

    await updateDocument(P, R, D, { document_type: "FAULT_DATA", document_number: "E-1" });
    expect(lastCall(fetchMock).body).toEqual({ document_type: "FAULT_DATA", document_number: "E-1" });

    await updateDocument(P, R, D, {});
    expect(lastCall(fetchMock).body).toEqual({});
  });

  it("removes and restores with POST and no body", async () => {
    const fetchMock = respond({ id: D });

    await removeDocument(P, R, D);
    expect(lastCall(fetchMock)).toEqual({
      path: `${BASE}/${D}/remove`,
      method: "POST",
      body: undefined,
    });

    await restoreDocument(P, R, D);
    expect(lastCall(fetchMock)).toEqual({
      path: `${BASE}/${D}/restore`,
      method: "POST",
      body: undefined,
    });
  });

  it("reuses a document with optional overrides", async () => {
    const fetchMock = respond({ id: D }, 201);

    await reuseDocument(P, R, { source_revision_document_id: D });
    expect(lastCall(fetchMock)).toEqual({
      path: `${BASE}/reuse`,
      method: "POST",
      body: { source_revision_document_id: D },
    });

    await reuseDocument(P, R, { source_revision_document_id: D, notes: null, document_type: "OTHER" });
    expect(lastCall(fetchMock).body).toEqual({
      source_revision_document_id: D,
      notes: null,
      document_type: "OTHER",
    });
  });

  it("requests an attachment download URL by default and honours inline", async () => {
    const fetchMock = respond({ url: "https://files/x", expires_at: "2026-10-06T00:00:00Z", filename: "a.pdf" });

    const result = await getDownloadUrl(P, R, D);
    expect(result.filename).toBe("a.pdf");
    expect(lastCall(fetchMock).path).toBe(`${BASE}/${D}/download-url?disposition=attachment`);

    await getDownloadUrl(P, R, D, "inline");
    expect(lastCall(fetchMock).path).toBe(`${BASE}/${D}/download-url?disposition=inline`);
  });
});

describe("document errors", () => {
  it.each([
    ["document_removed", { detail: "Restore it first", code: "document_removed" }],
    [
      "document_already_in_revision",
      {
        detail: "Already here",
        code: "document_already_in_revision",
        existing_revision_document_id: D,
        existing_status: "REMOVED",
      },
    ],
    ["revision_read_only", { detail: "Read only", code: "revision_read_only" }],
  ])("exposes %s from a 409", async (code, detail) => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 409,
      statusText: "Conflict",
      json: async () => ({ detail }),
    } as Response);

    const caught = await updateDocument(P, R, D, { notes: "x" }).catch((err: unknown) => err);

    const info = apiErrorOf(caught);
    expect(info.status).toBe(409);
    expect(info.code).toBe(code);
    if (code === "document_already_in_revision") {
      expect(info.error?.existing_revision_document_id).toBe(D);
      expect(info.error?.existing_status).toBe("REMOVED");
    }
  });
});

describe("canMutate and readOnlyReason", () => {
  const projectStatuses = ["ACTIVE", "PAUSED", "ARCHIVED", "CANCELLED"] as const;
  const revisionStatuses = ["DRAFT", "ACTIVE", "SUPERSEDED"] as const;

  for (const project of projectStatuses) {
    for (const revision of revisionStatuses) {
      const writable =
        revision !== "SUPERSEDED" && project !== "ARCHIVED" && project !== "CANCELLED";
      it(`project ${project} with revision ${revision} is ${writable ? "writable" : "read-only"}`, () => {
        const context = {
          project: { status: project },
          revision: { status: revision },
        };
        expect(canMutate(context)).toBe(writable);
        expect(readOnlyReason(context) === null).toBe(writable);
      });
    }
  }

  it("explains which state made the package read-only", () => {
    const reason = (
      project: "ACTIVE" | "ARCHIVED" | "CANCELLED",
      revision: "ACTIVE" | "SUPERSEDED",
    ) =>
      readOnlyReason({
        project: { status: project },
        revision: { status: revision },
      });
    expect(reason("ACTIVE", "SUPERSEDED")).toMatch(/revision is superseded/);
    expect(reason("ARCHIVED", "ACTIVE")).toMatch(/project is archived/);
    expect(reason("CANCELLED", "ACTIVE")).toMatch(/project is cancelled/);
  });
});

describe("canOpenInline", () => {
  it.each([
    ["application/pdf", true],
    ["image/png", true],
    ["image/jpeg", true],
    ["image/tiff", false],
  ])("%s -> %s", (mime, expected) => {
    expect(canOpenInline({ mime_type: mime })).toBe(expected);
  });
});
