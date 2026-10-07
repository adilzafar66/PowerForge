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
}));

import { RevisionDocuments } from "@/components/revision-documents";
import {
  getDownloadUrl,
  listDocuments,
  uploadDocument,
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
    expect(await screen.findByText("No documents in this revision yet.")).toBeInTheDocument();
    expect(screen.queryByText("Clear filters")).toBeNull();

    await user.selectOptions(screen.getByLabelText("Origin"), "INHERITED");
    expect(await screen.findByText("No documents match your filters.")).toBeInTheDocument();

    await user.click(screen.getByText("Clear filters"));
    expect(await screen.findByText("No documents in this revision yet.")).toBeInTheDocument();
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
  it("loads with default filters", async () => {
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    expect(list).toHaveBeenCalledWith(P, R, {
      status: "INCLUDED",
      document_type: "",
      origin: "",
      search: "",
    });
  });

  it("sends Type, Origin and View changes to the client", async () => {
    const user = userEvent.setup();
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await user.selectOptions(screen.getByLabelText("Type"), "CABLE_SCHEDULE");
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(
        P,
        R,
        expect.objectContaining({ document_type: "CABLE_SCHEDULE" }),
      ),
    );
    await user.selectOptions(screen.getByLabelText("Origin"), "INHERITED");
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(P, R, expect.objectContaining({ origin: "INHERITED" })),
    );
    await user.click(screen.getByRole("button", { name: "Removed" }));
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(P, R, expect.objectContaining({ status: "REMOVED" })),
    );
    await user.click(screen.getByRole("button", { name: "All" }));
    await waitFor(() =>
      expect(list).toHaveBeenLastCalledWith(P, R, expect.objectContaining({ status: "ALL" })),
    );
  });

  it("shows removed rows in the Removed view and does not request them by default", async () => {
    const user = userEvent.setup();
    list.mockImplementation(async (_p, _r, filters) =>
      filters?.status === "REMOVED"
        ? [makeRow({ name: "old.pdf", status: "REMOVED" })]
        : [makeRow({ name: "new.pdf" })],
    );
    renderWorkspace();
    expect(await screen.findByText("new.pdf")).toBeInTheDocument();
    expect(list).toHaveBeenCalledWith(P, R, expect.objectContaining({ status: "INCLUDED" }));

    await user.click(screen.getByRole("button", { name: "Removed" }));
    const row = (await screen.findByText("old.pdf")).closest("tr")!;
    expect(within(row).getByText("Removed")).toBeInTheDocument();
    expect(screen.queryByText("new.pdf")).toBeNull();
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
      expect(list).toHaveBeenLastCalledWith(P, R, expect.objectContaining({ search: "sld" })),
    );
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("ignores a slow earlier response that finishes after a newer one", async () => {
    const user = userEvent.setup();
    let resolveFirst: (rows: RevisionDocument[]) => void = () => {};
    list.mockImplementationOnce(
      () => new Promise<RevisionDocument[]>((resolve) => (resolveFirst = resolve)),
    );
    list.mockResolvedValueOnce([makeRow({ name: "fresh.pdf" })]);
    renderWorkspace();
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    await user.click(screen.getByRole("button", { name: "All" }));
    expect(await screen.findByText("fresh.pdf")).toBeInTheDocument();

    await act(async () => {
      resolveFirst([makeRow({ name: "stale.pdf" })]);
    });
    expect(screen.getByText("fresh.pdf")).toBeInTheDocument();
    expect(screen.queryByText("stale.pdf")).toBeNull();
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

    expect(await screen.findByText("No documents in this revision yet.")).toBeInTheDocument();
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

  it("is absent when the revision cannot be changed and present when it can", async () => {
    const first = renderWorkspace(false);
    await waitFor(() => expect(list).toHaveBeenCalled());
    expect(screen.queryByRole("button", { name: "Upload Documents" })).toBeNull();
    first.unmount();

    renderWorkspace(true);
    expect(await screen.findByRole("button", { name: "Upload Documents" })).toBeInTheDocument();
  });

  it("reloads the list when an upload completes", async () => {
    upload.mockResolvedValue({ duplicate_detected: false, duplicate_document_ids: [] } as never);
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));
    list.mockResolvedValue([makeRow({ name: "new.pdf" })]);

    choose(pdf());

    expect(await screen.findByRole("cell", { name: /new\.pdf/ })).toBeInTheDocument();
    expect(list).toHaveBeenCalledTimes(2);
  });

  it("shows a notice, refreshes the page and reloads the list on a read-only 409", async () => {
    upload.mockRejectedValue(
      Object.assign(new Error("Revision is superseded."), {
        apiError: { detail: "Revision is superseded.", code: "revision_read_only" },
        status: 409,
      }),
    );
    renderWorkspace(true);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(1));

    choose(pdf());

    expect(await screen.findByRole("status")).toHaveTextContent("Revision is superseded.");
    expect(refresh).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(list).toHaveBeenCalledTimes(2));
  });
});
