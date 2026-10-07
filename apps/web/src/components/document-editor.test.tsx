/** @vitest-environment jsdom */
import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({ href, children, ...props }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  updateDocument: vi.fn(),
}));

import { changedFields, DocumentEditor } from "@/components/document-editor";
import { updateDocument, type RevisionDocument } from "@/lib/documents";

const update = vi.mocked(updateDocument);

function makeRow(overrides: Partial<RevisionDocument> = {}): RevisionDocument {
  return {
    id: "rd-1",
    revision_id: "r-2",
    document: {
      id: "d-1",
      original_filename: "SLD.pdf",
      mime_type: "application/pdf",
      file_extension: "pdf",
      size_bytes: 2048,
      sha256: "a".repeat(64),
      uploaded_at: "2026-10-01T10:00:00Z",
    },
    origin: "UPLOADED",
    inherited_from_revision_id: null,
    inherited_from_revision_identifier: null,
    status: "INCLUDED",
    document_type: "SINGLE_LINE_DIAGRAM",
    document_number: "E-101",
    description: "Main one-line",
    notes: null,
    added_at: "2026-10-01T10:00:00Z",
    removed_at: null,
    ...overrides,
  } as RevisionDocument;
}

function setup(
  row: RevisionDocument,
  { canMutate = true, handled = false }: { canMutate?: boolean; handled?: boolean } = {},
) {
  const props = {
    onClose: vi.fn(),
    onSaved: vi.fn(),
    onMutationError: vi.fn(() => handled),
  };
  render(
    <DocumentEditor projectId="p-1" revisionId="r-2" document={row} canMutate={canMutate} {...props} />,
  );
  return props;
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("changedFields", () => {
  const row = makeRow();
  const same = {
    type: row.document_type,
    document_number: "E-101",
    description: "Main one-line",
    notes: "",
  };

  it("is empty when nothing changed, including surrounding whitespace", () => {
    expect(changedFields(row, same)).toEqual({});
    expect(changedFields(row, { ...same, document_number: "  E-101 " })).toEqual({});
  });

  it("returns only the changed fields", () => {
    expect(changedFields(row, { ...same, type: "CABLE_SCHEDULE" })).toEqual({
      document_type: "CABLE_SCHEDULE",
    });
    expect(changedFields(row, { ...same, notes: " hello " })).toEqual({ notes: "hello" });
  });

  it("sends null when a text field is cleared", () => {
    expect(changedFields(row, { ...same, document_number: "   " })).toEqual({
      document_number: null,
    });
  });
});

describe("DocumentEditor", () => {
  it("shows the read-only facts", () => {
    setup(
      makeRow({
        origin: "INHERITED",
        inherited_from_revision_id: "r-1",
        inherited_from_revision_identifier: "1",
      }),
    );
    expect(screen.getByText("application/pdf")).toBeInTheDocument();
    expect(screen.getByText("2.0 KB")).toBeInTheDocument();
    expect(screen.getByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Revision 1" })).toHaveAttribute(
      "href",
      "/projects/p-1/revisions/r-1",
    );
  });

  it("disables Save until something changes", async () => {
    const user = userEvent.setup();
    setup(makeRow());
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();

    await user.type(screen.getByLabelText("Notes"), "check");
    expect(save).toBeEnabled();
    await user.clear(screen.getByLabelText("Notes"));
    expect(save).toBeDisabled();
  });

  it("sends only the changed field and reports the saved row", async () => {
    const user = userEvent.setup();
    const saved = makeRow({ document_type: "CABLE_SCHEDULE" });
    update.mockResolvedValue(saved);
    const props = setup(makeRow());

    await user.selectOptions(screen.getByLabelText("Document type"), "CABLE_SCHEDULE");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(update).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledWith("p-1", "r-2", "rd-1", { document_type: "CABLE_SCHEDULE" });
    expect(props.onSaved).toHaveBeenCalledWith(saved);
  });

  it("sends null for a cleared field and never sends file facts", async () => {
    const user = userEvent.setup();
    update.mockResolvedValue(makeRow());
    setup(makeRow());

    await user.clear(screen.getByLabelText("Document number"));
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    const body = update.mock.calls[0][3];
    expect(body).toEqual({ document_number: null });
    expect(Object.keys(body)).not.toEqual(
      expect.arrayContaining(["original_filename", "sha256", "size_bytes"]),
    );
  });

  it("shows a validation error inline and stays open", async () => {
    const user = userEvent.setup();
    update.mockRejectedValue(
      Object.assign(new Error("Description is too long."), {
        status: 422,
        apiError: { code: "validation_error", detail: "Description is too long." },
      }),
    );
    const props = setup(makeRow());

    await user.type(screen.getByLabelText("Notes"), "n");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Description is too long.");
    expect(props.onClose).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
  });

  it("closes when the owner handles the failure (read-only or vanished row)", async () => {
    const user = userEvent.setup();
    update.mockRejectedValue(Object.assign(new Error("x"), { status: 409, apiError: { detail: "d" } }));
    const props = setup(makeRow(), { handled: true });

    await user.type(screen.getByLabelText("Notes"), "n");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => expect(props.onClose).toHaveBeenCalled());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("is view-only when the revision cannot be changed", () => {
    setup(makeRow(), { canMutate: false });
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    expect(screen.getByLabelText("Notes")).toBeDisabled();
    expect(screen.getByLabelText("Document type")).toBeDisabled();
    expect(screen.getByText(/read-only/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Close" })).toBeInTheDocument();
  });

  it("is view-only for a removed document", () => {
    setup(makeRow({ status: "REMOVED" }));
    expect(screen.queryByRole("button", { name: "Save changes" })).toBeNull();
    expect(screen.getByLabelText("Document number")).toBeDisabled();
    expect(screen.getByText(/Restore it to edit/)).toBeInTheDocument();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const props = setup(makeRow());
    await user.keyboard("{Escape}");
    expect(props.onClose).toHaveBeenCalled();
  });
});
