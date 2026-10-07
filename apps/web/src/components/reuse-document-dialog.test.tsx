/** @vitest-environment jsdom */
import React from "react";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  listDocuments: vi.fn(),
  reuseDocument: vi.fn(),
  restoreDocument: vi.fn(),
}));

vi.mock("@/lib/projects", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/projects")>()),
  listRevisions: vi.fn(),
}));

import { ReuseDocumentDialog } from "@/components/reuse-document-dialog";
import {
  listDocuments,
  restoreDocument,
  reuseDocument,
  type RevisionDocument,
} from "@/lib/documents";
import { listRevisions, type Revision } from "@/lib/projects";

const list = vi.mocked(listDocuments);
const reuse = vi.mocked(reuseDocument);
const restore = vi.mocked(restoreDocument);
const revisions = vi.mocked(listRevisions);

const CURRENT = "r-3";

function rev(id: string, identifier: string, status: string) {
  return { id, identifier, status } as unknown as Revision;
}

function row(name: string, revisionId: string, status: "INCLUDED" | "REMOVED" = "INCLUDED") {
  return {
    id: `rd-${revisionId}-${name}`,
    revision_id: revisionId,
    document: {
      id: `d-${name}`,
      original_filename: name,
      mime_type: "application/pdf",
      file_extension: "pdf",
      size_bytes: 2048,
      sha256: "a".repeat(64),
      uploaded_at: "2026-10-01T10:00:00Z",
    },
    origin: "UPLOADED",
    inherited_from_revision_id: null,
    inherited_from_revision_identifier: null,
    status,
    document_type: "SINGLE_LINE_DIAGRAM",
    document_number: null,
    description: null,
    notes: null,
    added_at: "2026-10-01T10:00:00Z",
    removed_at: null,
  } as RevisionDocument;
}

function apiError(status: number, code: string, detail: string, extra: object = {}) {
  return Object.assign(new Error(detail), { status, apiError: { code, detail, ...extra } });
}

function setup(sources: Record<string, RevisionDocument[]>, current: RevisionDocument[] = []) {
  revisions.mockResolvedValue([
    rev(CURRENT, "C", "ACTIVE"),
    rev("r-2", "B", "SUPERSEDED"),
    rev("r-1", "A", "SUPERSEDED"),
  ]);
  list.mockImplementation(async (_p, revisionId) =>
    revisionId === CURRENT ? current : (sources[revisionId] ?? []),
  );
  const props = { onClose: vi.fn(), onChanged: vi.fn(), onReadOnly: vi.fn() };
  render(<ReuseDocumentDialog projectId="p-1" revisionId={CURRENT} {...props} />);
  return props;
}

afterEach(() => {
  vi.resetAllMocks();
});

describe("ReuseDocumentDialog", () => {
  it("lists other revisions only, with status labels", async () => {
    setup({});
    const select = await screen.findByLabelText("Source revision");
    const labels = within(select)
      .getAllByRole("option")
      .map((option) => option.textContent);
    expect(labels).toEqual(["Revision B (Superseded)", "Revision A (Superseded)"]);
  });

  it("says so when the project has no other revisions", async () => {
    revisions.mockResolvedValue([rev(CURRENT, "C", "ACTIVE")]);
    render(<ReuseDocumentDialog projectId="p-1" revisionId={CURRENT} onClose={vi.fn()} onChanged={vi.fn()} onReadOnly={vi.fn()} />);
    expect(await screen.findByText("This project has no other revisions.")).toBeInTheDocument();
  });

  it("loads the source's included documents plus this revision's rows of every status", async () => {
    setup({ "r-2": [row("a.pdf", "r-2")] });
    await screen.findByText("a.pdf");
    expect(list).toHaveBeenCalledWith("p-1", "r-2", { status: "INCLUDED" });
    expect(list).toHaveBeenCalledWith("p-1", CURRENT, { status: "ALL" });
  });

  it("shows an empty source message", async () => {
    setup({ "r-2": [] });
    expect(await screen.findByText("No included documents in Revision B.")).toBeInTheDocument();
  });

  it("disables documents already in this revision, with the reason", async () => {
    setup(
      { "r-2": [row("kept.pdf", "r-2"), row("gone.pdf", "r-2"), row("new.pdf", "r-2")] },
      [row("kept.pdf", CURRENT), row("gone.pdf", CURRENT, "REMOVED")],
    );
    await screen.findByText("new.pdf");

    expect(screen.getByRole("checkbox", { name: "Select kept.pdf" })).toBeDisabled();
    expect(screen.getByText("Already in this revision")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select gone.pdf" })).toBeDisabled();
    expect(
      screen.getByText("Removed from this revision. Restore it from the Removed view."),
    ).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select new.pdf" })).toBeEnabled();
  });

  it("adds the selected documents one at a time with only the source id", async () => {
    const user = userEvent.setup();
    reuse.mockResolvedValue({} as never);
    const props = setup({ "r-2": [row("a.pdf", "r-2"), row("b.pdf", "r-2")] });
    await screen.findByText("a.pdf");

    await user.click(screen.getByRole("checkbox", { name: "Select a.pdf" }));
    await user.click(screen.getByRole("checkbox", { name: "Select b.pdf" }));
    await user.click(screen.getByRole("button", { name: "Add 2 documents" }));

    await waitFor(() => expect(props.onChanged).toHaveBeenCalledWith(2));
    expect(reuse.mock.calls.map((call) => call.slice(0, 3))).toEqual([
      ["p-1", CURRENT, { source_revision_document_id: "rd-r-2-a.pdf" }],
      ["p-1", CURRENT, { source_revision_document_id: "rd-r-2-b.pdf" }],
    ]);
    expect(screen.getAllByText("Added")).toHaveLength(2);
    expect(screen.getByRole("checkbox", { name: "Select a.pdf" })).toBeDisabled();
  });

  it("keeps a failed document selectable and offers Restore when it was removed", async () => {
    const user = userEvent.setup();
    reuse.mockRejectedValue(
      apiError(409, "document_already_in_revision", "Document is already in this revision.", {
        existing_revision_document_id: "rd-existing",
        existing_status: "REMOVED",
      }),
    );
    restore.mockResolvedValue({} as never);
    const props = setup({ "r-2": [row("a.pdf", "r-2")] });
    await screen.findByText("a.pdf");

    await user.click(screen.getByRole("checkbox", { name: "Select a.pdf" }));
    await user.click(screen.getByRole("button", { name: "Add 1 document" }));

    expect(await screen.findByText("Document is already in this revision.")).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "Select a.pdf" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Restore a.pdf" }));
    expect(restore).toHaveBeenCalledWith("p-1", CURRENT, "rd-existing");
    expect(await screen.findByText("Restored")).toBeInTheDocument();
    expect(props.onChanged).toHaveBeenLastCalledWith(1);
  });

  it("does not offer Restore when the existing row is still included", async () => {
    const user = userEvent.setup();
    reuse.mockRejectedValue(
      apiError(409, "document_already_in_revision", "Already here.", {
        existing_revision_document_id: "rd-existing",
        existing_status: "INCLUDED",
      }),
    );
    setup({ "r-2": [row("a.pdf", "r-2")] });
    await screen.findByText("a.pdf");

    await user.click(screen.getByRole("checkbox", { name: "Select a.pdf" }));
    await user.click(screen.getByRole("button", { name: "Add 1 document" }));

    expect(await screen.findByText("Already here.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Restore a.pdf" })).toBeNull();
  });

  it("stops the batch on a read-only conflict and marks the rest as not added", async () => {
    const user = userEvent.setup();
    reuse.mockRejectedValue(apiError(409, "revision_read_only", "This revision is read-only."));
    const props = setup({ "r-2": [row("a.pdf", "r-2"), row("b.pdf", "r-2")] });
    await screen.findByText("a.pdf");

    await user.click(screen.getByRole("checkbox", { name: "Select a.pdf" }));
    await user.click(screen.getByRole("checkbox", { name: "Select b.pdf" }));
    await user.click(screen.getByRole("button", { name: "Add 2 documents" }));

    await waitFor(() => expect(props.onReadOnly).toHaveBeenCalledWith("This revision is read-only."));
    expect(reuse).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Not added. This revision is read-only.")).toBeInTheDocument();
  });

  it("clears the selection when the source revision changes", async () => {
    const user = userEvent.setup();
    setup({ "r-2": [row("a.pdf", "r-2")], "r-1": [row("z.pdf", "r-1")] });
    await screen.findByText("a.pdf");
    await user.click(screen.getByRole("checkbox", { name: "Select a.pdf" }));
    expect(screen.getByRole("button", { name: "Add 1 document" })).toBeEnabled();

    await user.selectOptions(screen.getByLabelText("Source revision"), "r-1");
    await screen.findByText("z.pdf");
    expect(screen.getByRole("button", { name: "Add 0 documents" })).toBeDisabled();
  });
});
