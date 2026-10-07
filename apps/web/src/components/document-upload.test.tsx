/** @vitest-environment jsdom */
import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  uploadDocument: vi.fn(),
}));

import { DocumentUpload } from "@/components/document-upload";
import { uploadDocument, type UploadResult } from "@/lib/documents";

type Call = {
  file: File;
  metadata: Record<string, unknown>;
  signal?: AbortSignal;
  onProgress?: (percent: number) => void;
  resolve: (result: Partial<UploadResult>) => void;
  reject: (error: unknown) => void;
};

const upload = vi.mocked(uploadDocument);
let calls: Call[] = [];
let inFlight = 0;
let maxInFlight = 0;

beforeEach(() => {
  calls = [];
  inFlight = 0;
  maxInFlight = 0;
  upload.mockImplementation(
    (_p, _r, file, metadata = {}, options = {}) =>
      new Promise<UploadResult>((resolve, reject) => {
        inFlight += 1;
        maxInFlight = Math.max(maxInFlight, inFlight);
        const settle = () => {
          inFlight -= 1;
        };
        calls.push({
          file,
          metadata: metadata as Record<string, unknown>,
          signal: options.signal,
          onProgress: options.onProgress,
          resolve: (result) => {
            settle();
            resolve({ duplicate_detected: false, duplicate_document_ids: [], ...result } as UploadResult);
          },
          reject: (error) => {
            settle();
            reject(error);
          },
        });
        options.signal?.addEventListener("abort", () => {
          const abort = Object.assign(new Error("Upload cancelled."), { name: "AbortError" });
          reject(abort);
        });
      }),
  );
});

afterEach(() => {
  vi.clearAllMocks();
});

function apiError(status: number, code: string, detail: string) {
  return Object.assign(new Error(detail), { apiError: { detail, code }, status });
}

function pdf(name: string, size = 100) {
  return new File([new Uint8Array(size)], name, { type: "application/pdf" });
}

function renderUpload(props: Partial<React.ComponentProps<typeof DocumentUpload>> = {}) {
  const onUploaded = vi.fn();
  const onReadOnly = vi.fn();
  render(
    <DocumentUpload
      projectId="p"
      revisionId="r"
      onUploaded={onUploaded}
      onReadOnly={onReadOnly}
      {...props}
    />,
  );
  return { onUploaded, onReadOnly };
}

function choose(files: File[]) {
  fireEvent.change(screen.getByLabelText("Choose files"), { target: { files } });
}

function row(name: string) {
  return screen.getByText(name).closest("li") as HTMLElement;
}

describe("DocumentUpload queue", () => {
  it("sends one independent request per file and never runs more than 3 at once", async () => {
    renderUpload();
    const files = ["a", "b", "c", "d", "e"].map((n) => pdf(`${n}.pdf`));
    choose(files);

    await waitFor(() => expect(calls).toHaveLength(3));
    expect(upload).toHaveBeenCalledTimes(3);
    expect(calls.map((c) => c.file.name)).toEqual(["a.pdf", "b.pdf", "c.pdf"]);
    expect(within(row("d.pdf")).getByText("Queued")).toBeInTheDocument();

    await act(async () => calls[0].resolve({}));
    await waitFor(() => expect(calls).toHaveLength(4));
    await act(async () => calls[1].resolve({}));
    await waitFor(() => expect(calls).toHaveLength(5));
    expect(calls.map((c) => c.file.name)).toEqual(["a.pdf", "b.pdf", "c.pdf", "d.pdf", "e.pdf"]);

    for (const call of calls.slice(2)) {
      await act(async () => call.resolve({}));
    }
    await waitFor(() => expect(screen.getAllByText("Uploaded")).toHaveLength(5));
    expect(maxInFlight).toBe(3);
  });

  it("resolves mixed outcomes per file without stopping the others", async () => {
    const { onUploaded } = renderUpload();
    choose([pdf("ok.pdf"), pdf("exe.pdf"), pdf("big.pdf"), pdf("net.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(3));

    await act(async () => calls[0].resolve({}));
    await act(async () => calls[1].reject(apiError(415, "unsupported_document_type", "Unsupported type.")));
    await act(async () => calls[2].reject(apiError(413, "file_too_large", "Too large.")));
    await waitFor(() => expect(calls).toHaveLength(4));
    await act(async () =>
      calls[3].reject(
        Object.assign(new Error("Could not reach the server. Check your connection and retry."), {
          apiError: { detail: "Could not reach the server. Check your connection and retry." },
          status: 0,
        }),
      ),
    );

    expect(within(row("ok.pdf")).getByText("Uploaded")).toBeInTheDocument();
    expect(within(row("exe.pdf")).getByText("Unsupported type.")).toBeInTheDocument();
    expect(within(row("big.pdf")).getByText("Too large.")).toBeInTheDocument();
    expect(within(row("net.pdf")).getByText(/Could not reach the server/)).toBeInTheDocument();
    expect(onUploaded).toHaveBeenCalledTimes(1);
  });

  it("retries only the file whose Retry was clicked", async () => {
    const user = userEvent.setup();
    renderUpload();
    choose([pdf("good.pdf"), pdf("bad1.pdf"), pdf("bad2.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(3));
    await act(async () => calls[0].resolve({}));
    await act(async () => calls[1].reject(apiError(502, "storage_upload_failed", "Storage failed.")));
    await act(async () => calls[2].reject(apiError(502, "storage_upload_failed", "Storage failed.")));

    await user.click(screen.getByRole("button", { name: "Retry bad1.pdf" }));

    await waitFor(() => expect(calls).toHaveLength(4));
    expect(upload).toHaveBeenCalledTimes(4);
    expect(calls[3].file.name).toBe("bad1.pdf");
    expect(within(row("bad2.pdf")).getByText("Failed")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry bad2.pdf" })).toBeInTheDocument();
    await act(async () => calls[3].resolve({}));
    await waitFor(() => expect(within(row("bad1.pdf")).getByText("Uploaded")).toBeInTheDocument());
  });

  it("shows a non-blocking duplicate warning on an uploaded file", async () => {
    renderUpload();
    choose([pdf("dup.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(1));
    await act(async () => calls[0].resolve({ duplicate_detected: true }));

    const item = row("dup.pdf");
    expect(within(item).getByText("Uploaded")).toBeInTheDocument();
    expect(
      within(item).getByText("An identical file already exists in this project."),
    ).toBeInTheDocument();
  });

  it("updates the progress bar from the progress callback", async () => {
    renderUpload();
    choose([pdf("p.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(1));

    await act(async () => calls[0].onProgress?.(40));
    expect(screen.getByRole("progressbar", { name: /p\.pdf/ })).toHaveAttribute(
      "aria-valuenow",
      "40",
    );
  });

  it("rejects an unsupported file client-side with no request and no Retry", async () => {
    renderUpload();
    choose([new File(["MZ"], "setup.exe")]);

    expect(await screen.findByText(/setup\.exe: unsupported file type/)).toBeInTheDocument();
    expect(upload).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Remove setup.exe" })).toBeInTheDocument();
  });

  it("accepts files dropped on the drop zone", async () => {
    renderUpload();
    fireEvent.drop(screen.getByTestId("drop-zone"), {
      dataTransfer: { files: [pdf("dropped.pdf")] },
    });
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].file.name).toBe("dropped.pdf");
  });
});

describe("DocumentUpload batch document type", () => {
  it("sends the chosen type for every file in the batch", async () => {
    const user = userEvent.setup();
    renderUpload();
    await user.selectOptions(
      screen.getByLabelText("Document type for this batch"),
      "SINGLE_LINE_DIAGRAM",
    );
    choose([pdf("a.pdf"), pdf("b.pdf")]);

    await waitFor(() => expect(calls).toHaveLength(2));
    expect(calls.map((c) => c.metadata)).toEqual([
      { document_type: "SINGLE_LINE_DIAGRAM" },
      { document_type: "SINGLE_LINE_DIAGRAM" },
    ]);
  });

  it("sends no document type when the batch is Unclassified", async () => {
    renderUpload();
    choose([pdf("a.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].metadata).toEqual({});
  });
});

describe("DocumentUpload removal and cancelling", () => {
  it("never sends a queued file that was removed", async () => {
    const user = userEvent.setup();
    renderUpload();
    choose(["a", "b", "c", "d"].map((n) => pdf(`${n}.pdf`)));
    await waitFor(() => expect(calls).toHaveLength(3));

    await user.click(screen.getByRole("button", { name: "Remove d.pdf" }));
    await act(async () => calls[0].resolve({}));

    await waitFor(() => expect(screen.getAllByText("Uploaded")).toHaveLength(1));
    expect(upload).toHaveBeenCalledTimes(3);
    expect(screen.queryByText("d.pdf")).toBeNull();
  });

  it("aborts the request when an uploading file is cancelled", async () => {
    const user = userEvent.setup();
    renderUpload();
    choose([pdf("a.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(1));

    await user.click(screen.getByRole("button", { name: "Cancel a.pdf" }));

    expect(calls[0].signal?.aborted).toBe(true);
    expect(screen.queryByText("a.pdf")).toBeNull();
  });

  it("clears finished uploads", async () => {
    const user = userEvent.setup();
    renderUpload();
    choose([pdf("a.pdf")]);
    await waitFor(() => expect(calls).toHaveLength(1));
    await act(async () => calls[0].resolve({}));

    await user.click(screen.getByRole("button", { name: "Clear finished" }));
    expect(screen.queryByText("a.pdf")).toBeNull();
  });
});

describe("DocumentUpload read-only handling", () => {
  it("reports a read-only 409 and fails the queued files without retry", async () => {
    const { onReadOnly } = renderUpload();
    choose(["a", "b", "c", "d"].map((n) => pdf(`${n}.pdf`)));
    await waitFor(() => expect(calls).toHaveLength(3));

    await act(async () =>
      calls[0].reject(apiError(409, "revision_read_only", "Revision is superseded.")),
    );

    expect(onReadOnly).toHaveBeenCalledWith("Revision is superseded.");
    expect(within(row("a.pdf")).getByText("Revision is superseded.")).toBeInTheDocument();
    expect(within(row("a.pdf")).getByText("Failed")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Retry/ })).toBeNull();
    // d.pdf was still queued and is failed rather than sent.
    expect(within(row("d.pdf")).getByText("Failed")).toBeInTheDocument();
    expect(upload).toHaveBeenCalledTimes(3);
  });
});
