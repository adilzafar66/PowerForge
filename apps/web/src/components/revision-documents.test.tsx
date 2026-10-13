/** @vitest-environment jsdom */
import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  listDocuments: vi.fn(),
  getDownloadUrl: vi.fn(),
  uploadDocument: vi.fn(),
  removeDocument: vi.fn(),
  restoreDocument: vi.fn(),
  updateDocument: vi.fn(),
  retryProcessing: vi.fn(),
  listPages: vi.fn(),
  getPageArtifactUrl: vi.fn(),
  acceptClassification: vi.fn(),
  reclassifyDocument: vi.fn(),
  retryClassification: vi.fn(),
  listClassificationPages: vi.fn(),
}));

vi.mock("@/lib/projects", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/projects")>()),
  listRevisions: vi.fn(),
}));

import { RevisionDocuments } from "@/components/revision-documents";
import { listRevisions } from "@/lib/projects";
import {
  acceptClassification,
  getDownloadUrl,
  getPageArtifactUrl,
  listClassificationPages,
  listDocuments,
  listPages,
  reclassifyDocument,
  removeDocument,
  restoreDocument,
  retryClassification,
  retryProcessing,
  updateDocument,
  uploadDocument,
  type ClassificationAttempt,
  type ClassificationSuggestion,
  type ProcessingSummary,
  type RevisionDocument,
} from "@/lib/documents";

const P = "p-1";
const R = "r-2";

function makeRow(overrides: Partial<RevisionDocument> & { name?: string; mime?: string }) {
  const { name = "SLD_RevA.pdf", mime = "application/pdf", ...rest } = overrides;
  return {
    id: `rd-${name}`,
    revision_id: R,
    document: {
      id: `d-${name}`,
      original_filename: name,
      mime_type: mime,
      file_extension: name.split(".").pop() ?? "",
      size_bytes: 2048,
      sha256: "a".repeat(64),
      uploaded_at: "2026-10-01T10:00:00Z",
    },
    origin: "UPLOADED",
    inherited_from_revision_id: null,
    inherited_from_revision_identifier: null,
    status: "INCLUDED",
    document_type: "SINGLE_LINE_DIAGRAM",
    document_number: null,
    description: null,
    notes: null,
    added_at: "2026-10-01T10:00:00Z",
    removed_at: null,
    processing: null,
    classification: { enabled: true, suggestion: null, attempt: null },
    ...rest,
  } as RevisionDocument;
}

function apiError(status: number, detail: string) {
  return Object.assign(new Error(detail), { apiError: { detail }, status });
}

const list = vi.mocked(listDocuments);
const download = vi.mocked(getDownloadUrl);

function renderWorkspace(canMutate = false) {
  return render(<RevisionDocuments projectId={P} revisionId={R} canMutate={canMutate} />);
}

function quickView(name: string) {
  return within(screen.getByRole("group", { name: "Quick views" })).getByRole("button", {
    name: new RegExp(`^${name}\\b`),
  });
}

async function openAddMenu(user: ReturnType<typeof userEvent.setup>) {
  const [button] = await screen.findAllByRole("button", { name: "Add Documents" });
  await user.click(button);
}

beforeEach(() => {
  list.mockResolvedValue([]);
});

afterEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
});

describe("RevisionDocuments rows", () => {
  it("renders type labels, origin badges and the inherited-from link", async () => {
    list.mockResolvedValue([
      makeRow({ name: "SLD_RevB.pdf" }),
      makeRow({
        name: "Scan.pdf",
        origin: "INHERITED",
        inherited_from_revision_id: "r-1",
        inherited_from_revision_identifier: "1",
        document_type: "UNKNOWN",
        document_number: "E-101",
      }),
    ]);
    renderWorkspace();

    expect(await screen.findByText("SLD_RevB.pdf")).toBeInTheDocument();
    const [uploaded, inherited] = within(screen.getByRole("table")).getAllByRole("row").slice(1);
    expect(within(uploaded).getByText("Single Line Diagram")).toBeInTheDocument();
    expect(within(uploaded).getByText("Uploaded")).toBeInTheDocument();
    expect(within(uploaded).queryByText("Inherited")).toBeNull();
    expect(within(inherited).getByText("Unclassified")).toBeInTheDocument();
    expect(within(inherited).getByText("Inherited")).toBeInTheDocument();
    expect(screen.getByText("E-101")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revision 1" })).toHaveAttribute(
      "href",
      `/projects/${P}/revisions/r-1`,
    );
  });

  it("shows the empty state, and a filtered empty state with Clear filters", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.queryByText("Clear filters")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.selectOptions(screen.getByLabelText("Origin"), "INHERITED");
    expect(await screen.findByText("No documents match your filters.")).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Clear filters" })[0]);
    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.getByLabelText("Origin")).toHaveValue("");
  });

  it("offers Download but not Open for a TIFF row", async () => {
    list.mockResolvedValue([
      makeRow({ name: "plan.tif", mime: "image/tiff" }),
      makeRow({ name: "plan.pdf" }),
    ]);
    renderWorkspace();
    await screen.findByText("plan.tif");

    expect(screen.getByRole("button", { name: "Download plan.tif" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open plan.tif" })).toBeNull();
    expect(screen.getByRole("button", { name: "Open plan.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download plan.pdf" })).toBeInTheDocument();
  });
});

describe("RevisionDocuments filters", () => {
  it("loads every document once and leaves type and origin to the client", async () => {
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    expect(list).toHaveBeenCalledWith(P, R, { status: "ALL", search: "" });
  });

  it("filters type, origin, processing, and classification without another request", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "local.pdf" }),
      makeRow({
        name: "shop.pdf",
        origin: "INHERITED",
        document_type: "CABLE_SCHEDULE",
        processing: {
          status: "COMPLETED",
          attempt_count: 1,
          pages_processed: 2,
          pages_total: 2,
          error_code: null,
          error_message: null,
        },
        classification: {
          enabled: true,
          suggestion: {
            prediction_id: "pred",
            predicted_type: "CABLE_SCHEDULE",
            confidence_band: "HIGH",
            accepted: true,
            requires_page_classification: false,
          },
          attempt: {
            id: "run",
            status: "COMPLETED",
            stage: "DOCUMENT",
            pages_total: 2,
            pages_classified: 2,
            error_code: null,
          },
        },
      }),
    ]);
    renderWorkspace();
    expect(await screen.findByText("local.pdf")).toBeInTheDocument();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "Filters" }));
    await user.selectOptions(screen.getByLabelText("Document type"), "CABLE_SCHEDULE");
    await user.selectOptions(screen.getByLabelText("Origin"), "INHERITED");
    await user.selectOptions(screen.getByLabelText("Processing state"), "COMPLETED");
    await user.selectOptions(screen.getByLabelText("Classification state"), "ready");

    expect(screen.getByRole("button", { name: "Filters (4)" })).toBeInTheDocument();
    expect(screen.queryByText("local.pdf")).toBeNull();
    expect(screen.getByText("shop.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByRole("button", { name: "Filters" })).toBeInTheDocument();
    expect(screen.getByText("local.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("debounces search and sends a single request for the final text", async () => {
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    const input = screen.getByLabelText("Search");

    fireEvent.change(input, { target: { value: "s" } });
    fireEvent.change(input, { target: { value: "sl" } });
    fireEvent.change(input, { target: { value: "sld" } });
    expect(list).toHaveBeenCalledTimes(1);

    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(P, R, { status: "ALL", search: "sld" }),
    );
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("ignores a slow earlier response that finishes after a newer one", async () => {
    let resolveFirst: (rows: RevisionDocument[]) => void = () => {};
    list.mockImplementationOnce(
      () => new Promise<RevisionDocument[]>((resolve) => (resolveFirst = resolve)),
    );
    list.mockResolvedValueOnce([makeRow({ name: "fresh.pdf" })]);
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "fresh" } });
    expect(await screen.findByText("fresh.pdf")).toBeInTheDocument();

    await act(async () => {
      resolveFirst([makeRow({ name: "stale.pdf" })]);
    });
    expect(screen.getByText("fresh.pdf")).toBeInTheDocument();
    expect(screen.queryByText("stale.pdf")).toBeNull();
  });

  it("keeps classification, page, and download actions on the row", async () => {
    list.mockResolvedValue([
      makeRow({
        name: "ready.pdf",
        document_type: "PANEL_SCHEDULE",
        processing: {
          status: "COMPLETED",
          attempt_count: 1,
          pages_processed: 2,
          pages_total: 2,
          error_code: null,
          error_message: null,
        },
        classification: {
          enabled: true,
          suggestion: {
            prediction_id: "pred",
            predicted_type: "PANEL_SCHEDULE",
            confidence_band: "HIGH",
            accepted: false,
            requires_page_classification: false,
          },
          attempt: {
            id: "run",
            status: "COMPLETED",
            stage: "DOCUMENT",
            pages_total: 2,
            pages_classified: 2,
            error_code: null,
          },
        },
      }),
    ]);
    renderWorkspace(true);

    expect(await screen.findByRole("button", { name: "Accept" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "View pages" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download ready.pdf" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Actions for ready.pdf" })).toBeInTheDocument();
  });
});

describe("RevisionDocuments errors", () => {
  it("refreshes once and tells the user when the list returns 409", async () => {
    list.mockRejectedValueOnce(apiError(409, "Revision state changed."));
    list.mockResolvedValueOnce([makeRow({ name: "after.pdf" })]);
    renderWorkspace();

    expect(await screen.findByText("after.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status")).toHaveTextContent("Revision state changed.");
  });

  it("shows other errors with Retry", async () => {
    const user = userEvent.setup();
    list.mockRejectedValueOnce(apiError(500, "Server exploded"));
    renderWorkspace();

    expect(await screen.findByRole("alert")).toHaveTextContent("Server exploded");
    list.mockResolvedValueOnce([makeRow({ name: "ok.pdf" })]);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("ok.pdf")).toBeInTheDocument();
  });
});

describe("RevisionDocuments download actions", () => {
  const url = "http://localhost:9000/bucket/key?sig=1";

  it("Open requests an inline URL and navigates the pre-opened tab", async () => {
    const user = userEvent.setup();
    const tab = { opener: "x", location: { href: "" }, close: vi.fn() };
    const open = vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    download.mockResolvedValue({
      url,
      expires_at: "2026-10-01T10:05:00Z",
      filename: "a.pdf",
    });
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: "Open a.pdf" }));

    await waitFor(() => expect(tab.location.href).toBe(url));
    expect(open).toHaveBeenCalledWith("", "_blank");
    expect(download).toHaveBeenCalledWith(P, R, "rd-a.pdf", "inline");
    expect(tab.opener).toBeNull();
    expect(tab.close).not.toHaveBeenCalled();
  });

  it("Download requests an attachment URL and assigns the location", async () => {
    const user = userEvent.setup();
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    download.mockResolvedValue({
      url,
      expires_at: "2026-10-01T10:05:00Z",
      filename: "a.tif",
    });
    list.mockResolvedValue([makeRow({ name: "a.tif", mime: "image/tiff" })]);
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: "Download a.tif" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith(url));
    expect(download).toHaveBeenCalledWith(P, R, "rd-a.tif", "attachment");
  });

  it("closes the pre-opened tab and shows the error when the URL request fails", async () => {
    const user = userEvent.setup();
    const tab = { opener: "x", location: { href: "" }, close: vi.fn() };
    vi.spyOn(window, "open").mockReturnValue(tab as unknown as Window);
    download.mockRejectedValue(apiError(502, "Storage unavailable"));
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: "Open a.pdf" }));

    expect(await screen.findByText("Storage unavailable")).toBeInTheDocument();
    expect(tab.close).toHaveBeenCalled();
    expect(tab.location.href).toBe("");
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("refreshes the list when a download reports the state changed (404)", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "open").mockReturnValue(null);
    download.mockRejectedValue(apiError(404, "Document not found"));
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    list.mockResolvedValueOnce([]);
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: "Open a.pdf" }));

    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Document not found");
    expect(list).toHaveBeenCalledTimes(2);
  });
});

describe("RevisionDocuments upload area", () => {
  const upload = vi.mocked(uploadDocument);

  function choose(file: File) {
    fireEvent.change(screen.getByLabelText("Choose files"), { target: { files: [file] } });
  }
  const pdf = () => new File([new Uint8Array(10)], "new.pdf", { type: "application/pdf" });

  it("is absent when the revision cannot be changed and opens from Add Documents when it can", async () => {
    const user = userEvent.setup();
    const first = renderWorkspace(false);
    await waitFor(() => expect(list).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Add Documents" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    first.unmount();

    renderWorkspace(true);
    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    await openAddMenu(user);
    expect(screen.getByRole("menuitem", { name: "Upload files" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Add from another revision" })).toBeInTheDocument();
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    expect(await screen.findByRole("button", { name: "Upload Documents" })).toBeInTheDocument();
  });

  it("reloads the list when an upload completes", async () => {
    const user = userEvent.setup();
    upload.mockResolvedValue({ duplicate_detected: false, duplicate_document_ids: [] } as never);
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    list.mockResolvedValue([makeRow({ name: "new.pdf" })]);

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());

    expect(await screen.findByRole("cell", { name: /new\.pdf/ })).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("shows a notice, refreshes the page and reloads the list on a read-only 409", async () => {
    const user = userEvent.setup();
    upload.mockRejectedValue(
      Object.assign(new Error("Revision is superseded."), {
        apiError: { detail: "Revision is superseded.", code: "revision_read_only" },
        status: 409,
      }),
    );
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Upload files" }));
    choose(pdf());

    expect(await screen.findByRole("status")).toHaveTextContent("Revision is superseded.");
    expect(refresh).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });
});

describe("RevisionDocuments quick views", () => {
  const reviewClassification = {
    enabled: true,
    suggestion: {
      prediction_id: "pred",
      predicted_type: "PANEL_SCHEDULE" as const,
      confidence_band: "HIGH" as const,
      accepted: false,
      requires_page_classification: false,
    },
    attempt: {
      id: "run",
      status: "COMPLETED" as const,
      stage: "DOCUMENT" as const,
      pages_total: 1,
      pages_classified: 1,
      error_code: null,
    },
  };
  const failedProcessing = {
    status: "FAILED" as const,
    attempt_count: 1,
    pages_processed: 0,
    pages_total: 4,
    error_code: "RENDER_FAILED",
    error_message: "Could not read the file",
  };

  function loadMixed() {
    list.mockResolvedValue([
      makeRow({ name: "ready.pdf" }),
      makeRow({
        name: "review.pdf",
        document_type: "UNKNOWN",
        classification: reviewClassification,
      }),
      makeRow({ name: "bad.pdf", processing: failedProcessing }),
      makeRow({ name: "gone.pdf", status: "REMOVED" }),
    ]);
  }

  it("counts Needs Review and Issues inside All, and Removed outside it", async () => {
    loadMixed();
    renderWorkspace();

    expect(await screen.findByText("ready.pdf")).toBeInTheDocument();
    expect(quickView("All")).toHaveTextContent("3");
    expect(quickView("Needs Review")).toHaveTextContent("1");
    expect(quickView("Issues")).toHaveTextContent("1");
    expect(quickView("Removed")).toHaveTextContent("1");
    expect(screen.getByRole("heading", { name: "Documents 3" })).toBeInTheDocument();
    expect(screen.queryByText("gone.pdf")).toBeNull();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("filters All, Needs Review, Issues, and Removed in the client", async () => {
    const user = userEvent.setup();
    loadMixed();
    renderWorkspace();
    expect(await screen.findByText("ready.pdf")).toBeInTheDocument();
    expect(screen.getByText("review.pdf")).toBeInTheDocument();
    expect(screen.getByText("bad.pdf")).toBeInTheDocument();

    await user.click(quickView("Needs Review"));
    expect(screen.getByText("review.pdf")).toBeInTheDocument();
    expect(screen.queryByText("ready.pdf")).toBeNull();
    expect(screen.queryByText("bad.pdf")).toBeNull();
    expect(screen.queryByText("gone.pdf")).toBeNull();

    await user.click(quickView("Issues"));
    expect(screen.getByText("bad.pdf")).toBeInTheDocument();
    expect(screen.queryByText("review.pdf")).toBeNull();

    await user.click(quickView("Removed"));
    expect(screen.getByText("gone.pdf")).toBeInTheDocument();
    expect(screen.queryByText("bad.pdf")).toBeNull();

    await user.click(quickView("All"));
    expect(screen.getByText("ready.pdf")).toBeInTheDocument();
    expect(screen.queryByText("gone.pdf")).toBeNull();
    expect(list).toHaveBeenCalledTimes(1);
  });

  it("uses a distinct empty message for each quick view", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "ready.pdf" })]);
    renderWorkspace();
    expect(await screen.findByText("ready.pdf")).toBeInTheDocument();

    await user.click(quickView("Needs Review"));
    expect(screen.getByText("No documents need review")).toBeInTheDocument();
    await user.click(quickView("Issues"));
    expect(screen.getByText("No document issues")).toBeInTheDocument();
    await user.click(quickView("Removed"));
    expect(screen.getByText("No removed documents")).toBeInTheDocument();
  });

  it("says when search matches nothing", async () => {
    list.mockImplementation(async (_project, _revision, filters) =>
      filters?.search ? [] : [makeRow({ name: "sld.pdf" })],
    );
    renderWorkspace();
    expect(await screen.findByText("sld.pdf")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "missing" } });
    expect(await screen.findByText("No documents match your search")).toBeInTheDocument();
  });

  it("treats a revision that only has removed documents as empty in All", async () => {
    list.mockResolvedValue([makeRow({ name: "gone.pdf", status: "REMOVED" })]);
    renderWorkspace();

    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.queryByText("gone.pdf")).toBeNull();
  });
});

describe("RevisionDocuments row actions", () => {
  const remove = vi.mocked(removeDocument);
  const restore = vi.mocked(restoreDocument);
  const update = vi.mocked(updateDocument);

  async function openMenu(user: ReturnType<typeof userEvent.setup>, name: string) {
    await user.click(await screen.findByRole("button", { name: `Actions for ${name}` }));
  }

  it("offers only View details when the revision cannot be changed", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace(false);

    await openMenu(user, "a.pdf");
    expect(screen.getByRole("menuitem", { name: "View details" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Remove from this revision" })).toBeNull();
    expect(screen.queryByRole("menuitem", { name: "Edit details" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add from another revision" })).toBeNull();
  });

  it("offers Edit and Remove for an included row, and Restore for a removed one", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "a.pdf" }),
      makeRow({ name: "b.pdf", status: "REMOVED" }),
    ]);
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    expect(screen.getByRole("menuitem", { name: "Edit details" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Remove from this revision" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Restore" })).toBeNull();
    await user.keyboard("{Escape}");
    await user.click(quickView("Removed"));

    await openMenu(user, "b.pdf");
    expect(screen.getByRole("menuitem", { name: "Restore" })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Remove from this revision" })).toBeNull();
  });

  it("removes only after confirmation and reloads the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    remove.mockResolvedValue({} as never);
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Remove from this revision" }));
    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent("Remove document from this revision?");

    list.mockResolvedValueOnce([]);
    await user.click(screen.getByRole("button", { name: "Remove" }));

    expect(remove).toHaveBeenCalledWith(P, R, "rd-a.pdf");
    expect(await screen.findByText("No documents in this revision")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Removed a.pdf from this revision.");
  });

  it("does nothing when the confirmation is cancelled", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "a.pdf" })]);
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Remove from this revision" }));
    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(remove).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("restores a removed row without confirmation", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([makeRow({ name: "b.pdf", status: "REMOVED" })]);
    restore.mockResolvedValue({} as never);
    renderWorkspace(true);
    await user.click(quickView("Removed"));

    await openMenu(user, "b.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Restore" }));

    expect(restore).toHaveBeenCalledWith(P, R, "rd-b.pdf");
    expect(await screen.findByText("Restored b.pdf.")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("explains a 409 on remove and refreshes the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    remove.mockRejectedValue(
      Object.assign(new Error("Document state changed."), {
        status: 409,
        apiError: { code: "document_removed", detail: "Document state changed." },
      }),
    );
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Remove from this revision" }));
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf", status: "REMOVED" })]);
    await user.click(screen.getByRole("button", { name: "Remove" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Document state changed.");
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });

  it("saves edited details and reloads the list", async () => {
    const user = userEvent.setup();
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf" })]);
    update.mockResolvedValue(makeRow({ name: "a.pdf", document_number: "E-7" }));
    renderWorkspace(true);

    await openMenu(user, "a.pdf");
    await user.click(screen.getByRole("menuitem", { name: "Edit details" }));
    await user.type(screen.getByLabelText("Document number"), "E-7");
    list.mockResolvedValueOnce([makeRow({ name: "a.pdf", document_number: "E-7" })]);
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(update).toHaveBeenCalledWith(P, R, "rd-a.pdf", { document_number: "E-7" });
    expect(await screen.findByText("E-7")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Saved changes to a.pdf.");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("opens the reuse dialog from Add from another revision", async () => {
    const user = userEvent.setup();
    vi.mocked(listRevisions).mockResolvedValue([]);
    renderWorkspace(true);

    await openAddMenu(user);
    await user.click(screen.getByRole("menuitem", { name: "Add from another revision" }));
    expect(await screen.findByText("This project has no other revisions.")).toBeInTheDocument();
  });
});

function summary(
  overrides: Partial<ProcessingSummary> & Pick<ProcessingSummary, "status">,
): ProcessingSummary {
  return {
    attempt_count: 1,
    pages_processed: 0,
    pages_total: null,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

describe("processing column and page viewer", () => {
  const retry = vi.mocked(retryProcessing);
  const pages = vi.mocked(listPages);
  const artifactUrl = vi.mocked(getPageArtifactUrl);

  it("renders each state from the list and does not call processing routes", async () => {
    list.mockResolvedValue([
      makeRow({ name: "none.pdf" }),
      makeRow({ name: "wait.pdf", processing: summary({ status: "PENDING" }) }),
      makeRow({
        name: "run.pdf",
        processing: summary({ status: "RUNNING", pages_processed: 1, pages_total: 4 }),
      }),
      makeRow({
        name: "done.pdf",
        processing: summary({ status: "COMPLETED", pages_processed: 4, pages_total: 4 }),
      }),
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Could not read the file" }),
      }),
    ]);
    renderWorkspace(true);

    expect(await screen.findByText("Not started")).toBeInTheDocument();
    expect(screen.getByText("Pending")).toBeInTheDocument();
    expect(screen.getByText("Processing 1/4")).toBeInTheDocument();
    expect(screen.getByText("Ready")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(screen.getByText("Could not read the file")).toBeInTheDocument();
    expect(pages).not.toHaveBeenCalled();
    expect(retry).not.toHaveBeenCalled();
    expect(artifactUrl).not.toHaveBeenCalled();
  });

  it("retries only a failed row, including on a read-only revision", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "wait.pdf", processing: summary({ status: "PENDING" }) }),
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Corrupt" }),
      }),
    ]);
    retry.mockResolvedValue({
      processing: summary({ status: "PENDING", attempt_count: 2 }),
      processor_version: "1",
      profile_version: "engineering-default-v1",
      profile_hash: "abc",
    });
    renderWorkspace(false);

    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add from another revision" })).toBeNull();
    expect(screen.queryByRole("button", { name: "View pages" })).toBeNull();
    const retryButton = await screen.findByRole("button", { name: "Retry processing" });
    expect(screen.getAllByRole("button", { name: "Retry processing" })).toHaveLength(1);
    await user.click(retryButton);

    expect(retry).toHaveBeenCalledWith(P, R, "rd-bad.pdf");
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "Retry processing" })).toBeNull(),
    );
    expect(screen.queryByText("Corrupt")).toBeNull();
  });

  it("opens the viewer only for a ready document and loads the analysis image", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      makeRow({ name: "done.pdf", processing: summary({ status: "COMPLETED" }) }),
      makeRow({
        name: "bad.pdf",
        processing: summary({ status: "FAILED", error_message: "Corrupt" }),
      }),
    ]);
    pages.mockResolvedValue([
      {
        id: "page-1",
        page_number: 1,
        source_width: "612",
        source_height: "792",
        source_unit: "POINTS",
        rotation_degrees: 0,
        native_text_char_count: 12,
        artifacts: [
          {
            artifact_type: "ANALYSIS_IMAGE",
            mime_type: "image/png",
            width_px: 1000,
            height_px: 1400,
          },
          {
            artifact_type: "THUMBNAIL",
            mime_type: "image/webp",
            width_px: 400,
            height_px: 560,
          },
        ],
      },
    ]);
    artifactUrl.mockImplementation(async (_project, _revision, _document, pageId, type) => ({
      url: `https://files.example/${type}/${pageId}`,
      expires_at: "2026-10-10T00:00:00Z",
      filename: type === "ANALYSIS_IMAGE" ? "analysis.png" : "thumbnail.webp",
    }));
    renderWorkspace(false);

    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add from another revision" })).toBeNull();
    const view = await screen.findByRole("button", { name: "View pages" });
    expect(screen.getAllByRole("button", { name: "View pages" })).toHaveLength(1);
    await user.click(view);

    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("612 × 792 pt")).toBeInTheDocument();
    expect(screen.getByText("1000 × 1400 px")).toBeInTheDocument();
    expect(screen.getByText("Native text")).toBeInTheDocument();
    await waitFor(() =>
      expect(artifactUrl).toHaveBeenCalledWith(P, R, "rd-done.pdf", "page-1", "ANALYSIS_IMAGE"),
    );
    expect(screen.getByRole("img", { name: "Page 1 analysis" })).toHaveAttribute(
      "src",
      "https://files.example/ANALYSIS_IMAGE/page-1",
    );
  });
});

function suggestion(
  overrides: Partial<ClassificationSuggestion> = {},
): ClassificationSuggestion {
  return {
    prediction_id: "pred-1",
    predicted_type: "TRANSFORMER_SHOP_DRAWING",
    confidence_band: "HIGH",
    accepted: false,
    requires_page_classification: false,
    ...overrides,
  };
}

function attempt(
  overrides: Partial<ClassificationAttempt> & { status: ClassificationAttempt["status"] },
): ClassificationAttempt {
  return {
    id: "run-1",
    stage: "DOCUMENT",
    pages_total: 2,
    pages_classified: 0,
    error_code: null,
    ...overrides,
  };
}

function classified(
  name: string,
  classification: RevisionDocument["classification"],
  extra: Partial<RevisionDocument> = {},
) {
  return makeRow({ name, classification, ...extra });
}

function page(id: string, pageNumber: number) {
  return {
    id,
    page_number: pageNumber,
    source_width: "612",
    source_height: "792",
    source_unit: "POINTS" as const,
    rotation_degrees: 0,
    native_text_char_count: 0,
    artifacts: [],
  };
}

describe("AI suggestion column", () => {
  const accept = vi.mocked(acceptClassification);
  const reclassify = vi.mocked(reclassifyDocument);
  const retry = vi.mocked(retryClassification);
  const classificationPages = vi.mocked(listClassificationPages);
  const update = vi.mocked(updateDocument);
  const pages = vi.mocked(listPages);
  const artifactUrl = vi.mocked(getPageArtifactUrl);

  beforeEach(() => {
    accept.mockReset();
    reclassify.mockReset();
    retry.mockReset();
    classificationPages.mockReset();
  });

  it("renders each attempt state from the list payload without calling classification", async () => {
    list.mockResolvedValue([
      classified("none.pdf", { enabled: true, suggestion: null, attempt: null }),
      classified("off.pdf", {
        enabled: false,
        suggestion: suggestion({ predicted_type: "PANEL_SCHEDULE", confidence_band: "MEDIUM" }),
        attempt: attempt({ status: "FAILED", error_code: "PROVIDER_TIMEOUT" }),
      }),
      classified("wait.pdf", {
        enabled: true,
        suggestion: null,
        attempt: attempt({ status: "PENDING" }),
      }),
      classified("run.pdf", {
        enabled: true,
        suggestion: null,
        attempt: attempt({ status: "RUNNING" }),
      }),
      classified(
        "ready.pdf",
        {
          enabled: true,
          suggestion: suggestion({ confidence_band: "HIGH" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "TRANSFORMER_SHOP_DRAWING" },
      ),
      classified("bad.pdf", {
        enabled: true,
        suggestion: null,
        attempt: attempt({ status: "FAILED", error_code: "PROVIDER_TIMEOUT" }),
      }),
    ]);
    renderWorkspace();

    const none = await screen.findByRole("row", { name: /none.pdf/ });
    expect(within(none).getByText("Not classified")).toBeInTheDocument();
    const off = screen.getByRole("row", { name: /off.pdf/ });
    expect(within(off).getByText("AI classification disabled")).toBeInTheDocument();
    expect(within(off).getByText(/Panel Schedule/)).toBeInTheDocument();
    expect(within(off).queryByRole("button", { name: "Reclassify" })).toBeNull();
    expect(within(off).queryByRole("button", { name: "Retry classification" })).toBeNull();
    expect(within(screen.getByRole("row", { name: /wait.pdf/ })).getByText("Pending")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /run.pdf/ })).getByText("Classifying")).toBeInTheDocument();
    const ready = screen.getByRole("row", { name: /ready.pdf/ });
    expect(within(ready).getByText("Ready")).toBeInTheDocument();
    expect(within(ready).getByText("High")).toBeInTheDocument();
    expect(within(ready).queryByLabelText("Accepted")).toBeNull();
    const bad = screen.getByRole("row", { name: /bad.pdf/ });
    expect(within(bad).getByText("Failed")).toBeInTheDocument();
    expect(within(bad).getByText("The classification provider timed out.")).toBeInTheDocument();
    expect(accept).not.toHaveBeenCalled();
    expect(reclassify).not.toHaveBeenCalled();
    expect(retry).not.toHaveBeenCalled();
    expect(classificationPages).not.toHaveBeenCalled();
  });

  it("shows Retry only for a failed attempt and Reclassify only for a settled suggestion", async () => {
    list.mockResolvedValue([
      classified("pending.pdf", {
        enabled: true,
        suggestion: suggestion({ predicted_type: "SPECIFICATION" }),
        attempt: attempt({ status: "PENDING" }),
      }),
      classified("running.pdf", {
        enabled: true,
        suggestion: suggestion({ predicted_type: "MOTOR_DATA" }),
        attempt: attempt({ status: "RUNNING" }),
      }),
      classified("failed-empty.pdf", {
        enabled: true,
        suggestion: null,
        attempt: attempt({ status: "FAILED", error_code: "CLASSIFICATION_TASK_TIMEOUT" }),
      }),
      classified("done.pdf", {
        enabled: true,
        suggestion: suggestion({ predicted_type: "CABLE_SCHEDULE" }),
        attempt: attempt({ status: "COMPLETED" }),
      }),
      classified("failed-keep.pdf", {
        enabled: true,
        suggestion: suggestion({ predicted_type: "SINGLE_LINE_DIAGRAM" }),
        attempt: attempt({ status: "FAILED", error_code: "CLASSIFICATION_TASK_TIMEOUT" }),
      }),
    ]);
    renderWorkspace();

    const pending = await screen.findByRole("row", { name: /pending.pdf/ });
    expect(within(pending).queryByRole("button", { name: "Reclassify" })).toBeNull();
    expect(within(pending).queryByRole("button", { name: "Retry classification" })).toBeNull();
    expect(within(pending).getByText(/Specification/)).toBeInTheDocument();
    const running = screen.getByRole("row", { name: /running.pdf/ });
    expect(within(running).queryByRole("button", { name: "Reclassify" })).toBeNull();
    expect(within(running).queryByRole("button", { name: "Retry classification" })).toBeNull();
    const empty = screen.getByRole("row", { name: /failed-empty.pdf/ });
    expect(within(empty).getByRole("button", { name: "Retry classification" })).toBeInTheDocument();
    expect(within(empty).queryByRole("button", { name: "Reclassify" })).toBeNull();
    expect(within(empty).getByText("Classification timed out.")).toBeInTheDocument();
    const done = screen.getByRole("row", { name: /done.pdf/ });
    expect(within(done).getByRole("button", { name: "Reclassify" })).toBeInTheDocument();
    expect(within(done).queryByRole("button", { name: "Retry classification" })).toBeNull();
    const kept = screen.getByRole("row", { name: /failed-keep.pdf/ });
    expect(within(kept).getByRole("button", { name: "Retry classification" })).toBeInTheDocument();
    expect(within(kept).getByRole("button", { name: "Reclassify" })).toBeInTheDocument();
    expect(within(kept).getAllByText(/Single Line Diagram/).length).toBeGreaterThan(0);
  });

  it("accepts an unaccepted suggestion and replaces the row", async () => {
    const user = userEvent.setup();
    const accepted = classified(
      "tx.pdf",
      {
        enabled: true,
        suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING", accepted: true }),
        attempt: attempt({ status: "COMPLETED" }),
      },
      { document_type: "TRANSFORMER_SHOP_DRAWING" },
    );
    list.mockResolvedValue([
      classified(
        "tx.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "TRANSFORMER_SHOP_DRAWING" },
      ),
    ]);
    accept.mockResolvedValue(accepted);
    renderWorkspace(true);

    await user.click(await screen.findByRole("button", { name: "Accept" }));

    expect(accept).toHaveBeenCalledWith(P, R, "rd-tx.pdf", "pred-1");
    expect(await screen.findByLabelText("Accepted")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Accept" })).toBeNull();
  });

  it("uses the same accept route when the confirmed type differs", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      classified(
        "tx.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "ELECTRICAL_DRAWING" },
      ),
    ]);
    accept.mockResolvedValue(
      classified(
        "tx.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING", accepted: true }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "TRANSFORMER_SHOP_DRAWING" },
      ),
    );
    renderWorkspace(true);

    const row = await screen.findByRole("row", { name: /tx.pdf/ });
    expect(within(row).getAllByText("Electrical Drawing").length).toBeGreaterThan(0);
    expect(within(row).getByText(/Transformer Shop Drawing/)).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Use AI Suggestion" }));

    expect(accept).toHaveBeenCalledWith(P, R, "rd-tx.pdf", "pred-1");
    expect(await screen.findByLabelText("Accepted")).toBeInTheDocument();
  });

  it("opens the existing editor to choose another type", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      classified(
        "tx.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "TRANSFORMER_SHOP_DRAWING" },
      ),
    ]);
    renderWorkspace(true);

    await user.click(await screen.findByRole("button", { name: "Choose another type" }));

    expect(await screen.findByRole("dialog", { name: "Edit document details" })).toBeInTheDocument();
    expect(update).not.toHaveBeenCalled();
  });

  it("keeps the current type without patching", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      classified(
        "tx.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "TRANSFORMER_SHOP_DRAWING" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "ELECTRICAL_DRAWING" },
      ),
    ]);
    renderWorkspace(true);

    await user.click(await screen.findByRole("button", { name: "Keep Current" }));

    expect(update).not.toHaveBeenCalled();
    expect(accept).not.toHaveBeenCalled();
    expect(screen.getAllByText("Electrical Drawing").length).toBeGreaterThan(0);
  });

  it("shows the checkmark only when the suggestion is accepted", async () => {
    list.mockResolvedValue([
      classified(
        "open.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "SPECIFICATION", accepted: false }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "SPECIFICATION" },
      ),
      classified(
        "yes.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "SPECIFICATION", accepted: true }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "SPECIFICATION" },
      ),
      classified(
        "differ.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "MOTOR_DATA", accepted: true }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { document_type: "CABLE_SCHEDULE" },
      ),
    ]);
    renderWorkspace();

    const open = await screen.findByRole("row", { name: /open.pdf/ });
    expect(within(open).queryByLabelText("Accepted")).toBeNull();
    expect(within(screen.getByRole("row", { name: /yes.pdf/ })).getByLabelText("Accepted")).toBeInTheDocument();
    expect(within(screen.getByRole("row", { name: /differ.pdf/ })).getByLabelText("Accepted")).toBeInTheDocument();
  });

  it("keeps the previous suggestion when reclassify fails", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      classified("sld.pdf", {
        enabled: true,
        suggestion: suggestion({ predicted_type: "SINGLE_LINE_DIAGRAM", confidence_band: "MEDIUM" }),
        attempt: attempt({ status: "FAILED", error_code: "CLASSIFICATION_TASK_TIMEOUT" }),
      }),
    ]);
    reclassify.mockResolvedValue({
      enabled: true,
      suggestion: suggestion({ predicted_type: "SINGLE_LINE_DIAGRAM", confidence_band: "MEDIUM" }),
      attempt: attempt({ id: "run-2", status: "FAILED", error_code: "PROVIDER_TIMEOUT" }),
    });
    renderWorkspace();

    const row = await screen.findByRole("row", { name: /sld.pdf/ });
    expect(within(row).getAllByText(/Single Line Diagram/).length).toBeGreaterThan(0);
    expect(within(row).getByText("Classification timed out.")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Reclassify" }));

    expect(reclassify).toHaveBeenCalledWith(P, R, "rd-sld.pdf");
    expect(await screen.findByText("The classification provider timed out.")).toBeInTheDocument();
    expect(screen.getAllByText(/Single Line Diagram/).length).toBeGreaterThan(0);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("retries a failed run and merges the returned attempt", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      classified("bad.pdf", {
        enabled: true,
        suggestion: null,
        attempt: attempt({ id: "run-7", status: "FAILED", error_code: "PROVIDER_TIMEOUT" }),
      }),
    ]);
    retry.mockResolvedValue({
      enabled: true,
      suggestion: null,
      attempt: attempt({ id: "run-8", status: "PENDING" }),
    });
    renderWorkspace();

    await user.click(await screen.findByRole("button", { name: "Retry classification" }));

    expect(retry).toHaveBeenCalledWith(P, R, "rd-bad.pdf", "run-7");
    expect(await screen.findByText("Pending")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Retry classification" })).toBeNull();
  });

  it("loads mixed page predictions on demand and opens that page", async () => {
    const user = userEvent.setup();
    list.mockResolvedValue([
      classified("mixed.pdf", {
        enabled: true,
        suggestion: suggestion({
          predicted_type: "MIXED_DOCUMENT",
          confidence_band: "LOW",
          requires_page_classification: true,
        }),
        attempt: attempt({ status: "COMPLETED" }),
      }),
    ]);
    classificationPages.mockResolvedValue([
      { page_number: 1, predicted_type: "SINGLE_LINE_DIAGRAM", confidence_band: "HIGH" },
      { page_number: 2, predicted_type: "PANEL_SCHEDULE", confidence_band: "LOW" },
    ]);
    pages.mockResolvedValue([page("page-1", 1), page("page-2", 2)]);
    artifactUrl.mockResolvedValue({
      url: "https://files.example/page",
      expires_at: "2026-10-10T00:00:00Z",
      filename: "page.png",
    });
    renderWorkspace();

    const row = await screen.findByRole("row", { name: /mixed.pdf/ });
    expect(within(row).getByRole("button", { name: "View page types" })).toBeInTheDocument();
    expect(classificationPages).not.toHaveBeenCalled();
    await user.click(within(row).getByRole("button", { name: "View page types" }));

    expect(classificationPages).toHaveBeenCalledTimes(1);
    expect(classificationPages).toHaveBeenCalledWith(P, R, "rd-mixed.pdf");
    expect(await within(row).findByRole("cell", { name: "Panel Schedule" })).toBeInTheDocument();
    expect(within(row).getAllByText("Low").length).toBeGreaterThan(0);
    await user.click(within(row).getByRole("button", { name: "2" }));

    expect(await screen.findByRole("button", { name: /Page 2/, pressed: true })).toBeInTheDocument();
    expect(pages).toHaveBeenCalledWith(P, R, "rd-mixed.pdf");
  });

  it("hides accept and choose-type on a read-only revision while the suggestion stays", async () => {
    list.mockResolvedValue([
      classified(
        "open.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "SPECIFICATION" }),
          attempt: attempt({ status: "FAILED", error_code: "OTHER" }),
        },
        { document_type: "SPECIFICATION" },
      ),
    ]);
    renderWorkspace(false);

    const open = await screen.findByRole("row", { name: /open.pdf/ });
    expect(within(open).getAllByText(/Specification/).length).toBeGreaterThan(0);
    expect(within(open).queryByRole("button", { name: "Accept" })).toBeNull();
    expect(within(open).queryByRole("button", { name: "Choose another type" })).toBeNull();
    expect(within(open).getByRole("button", { name: "Retry classification" })).toBeInTheDocument();
    expect(within(open).getByRole("button", { name: "Reclassify" })).toBeInTheDocument();
  });

  it("keeps a removed row's suggestion visible without accept or choose-type", async () => {
    list.mockResolvedValue([
      classified(
        "gone.pdf",
        {
          enabled: true,
          suggestion: suggestion({ predicted_type: "MOTOR_DATA", confidence_band: "LOW" }),
          attempt: attempt({ status: "COMPLETED" }),
        },
        { status: "REMOVED", document_type: "MOTOR_DATA" },
      ),
    ]);
    const user = userEvent.setup();
    renderWorkspace(true);
    await user.click(quickView("Removed"));

    const gone = await screen.findByRole("row", { name: /gone.pdf/ });
    expect(within(gone).getAllByText(/Motor Data/).length).toBeGreaterThan(0);
    expect(within(gone).queryByRole("button", { name: "Accept" })).toBeNull();
    expect(within(gone).queryByRole("button", { name: "Choose another type" })).toBeNull();
    expect(within(gone).getByRole("button", { name: "Reclassify" })).toBeInTheDocument();
  });
});
