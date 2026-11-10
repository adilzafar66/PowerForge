/** @vitest-environment jsdom */
import { render, screen, waitFor, within } from "@/components/query-test-utils";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/lib/extraction-operations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/extraction-operations")>()),
  getOperationSources: vi.fn(),
  previewExtractionOperation: vi.fn(),
  startExtractionOperation: vi.fn(),
}));

import { StartExtractionWizard } from "@/components/start-extraction-wizard";
import { getOperationSources, previewExtractionOperation, startExtractionOperation } from "@/lib/extraction-operations";

const scope = { projectId: "project", revisionId: "revision" };
const source = {
  revision_document_id: "source", filename: "schedule.pdf", processing_run_id: "processing-version",
  page_count: 3, available_pages: [1, 2, 3], error: null,
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(getOperationSources).mockResolvedValue({
    items: [source], max_pages_per_document: 50, max_documents: 20, max_pages: 150, read_only: false,
  });
  vi.mocked(previewExtractionOperation).mockImplementation(async (_scope, selection) => ({
    items: selection.documents.map((item) => ({
      revision_document_id: item.revision_document_id, filename: source.filename,
      processing_run_id: item.processing_run_id, error: null,
      pages: item.pages.map((page_number) => ({
        page_number, force_ocr: item.force_ocr_pages.includes(page_number),
        reuse_preparation: false, reuse_layout: false,
      })),
    })),
    errors: [],
    profiles: selection.families.map((family) => ({ family, key: family, provider: "openai", model: "fixture", enabled: true })),
    review_hash: selection.families.join(","),
    planned_runs: selection.families.length,
    provider_admissions: 12, ocr_attempts: 3, parallel_documents: 2,
    consent_version: "external-openai-v1",
  }));
  vi.mocked(startExtractionOperation).mockResolvedValue({ id: "operation" });
});

it("validates source and OCR pages, retains targeting, and starts only after consent", async () => {
  const user = userEvent.setup();
  const started = vi.fn();
  render(<StartExtractionWizard scope={scope} launch={{ documentIds: ["source"] }} onClose={vi.fn()} onStarted={started} />);
  const modal = within(screen.getByRole("dialog", { name: "Start extraction" }));
  const pages = await modal.findByRole("textbox", { name: "Pages for schedule.pdf" });
  await user.clear(pages);
  await user.type(pages, "1, 1");
  expect(modal.getByText("Page 1 is listed more than once.")).toBeVisible();
  expect(modal.getByRole("button", { name: "Continue to enrichment" })).toBeDisabled();
  await user.clear(pages);
  await user.type(pages, "1–2");
  await user.click(modal.getByRole("button", { name: "Continue to enrichment" }));
  await user.click(modal.getByText("Advanced OCR override (optional)"));
  const ocr = modal.getByRole("textbox", { name: "Force OCR pages for schedule.pdf" });
  await user.type(ocr, "3");
  expect(modal.getByText("Page 3 is outside the available pages.")).toBeVisible();
  expect(modal.getByRole("button", { name: "Continue to extraction" })).toBeDisabled();
  await user.clear(ocr);
  await user.type(ocr, "2");
  await waitFor(() => expect(modal.getByRole("button", { name: "Continue to extraction" })).toBeEnabled());
  await user.click(modal.getByRole("button", { name: "Continue to extraction" }));
  expect(modal.getByText("Comprehensive extraction")).toBeVisible();
  expect(await modal.findByText("2 extraction runs requested")).toBeVisible();
  await user.click(modal.getByText("Advanced extraction settings"));
  await user.click(modal.getByRole("checkbox", { name: "Extract from engineering text" }));
  expect(modal.getByRole("checkbox", { name: "Extract from tables and schedules" })).toBeDisabled();
  expect(await modal.findByText("1 extraction run requested")).toBeVisible();

  await user.click(modal.getByRole("button", { name: "Back" }));
  await user.click(modal.getByRole("button", { name: "Continue to extraction" }));
  expect(modal.getByText("Targeted extraction")).toBeVisible();
  expect(startExtractionOperation).not.toHaveBeenCalled();
  expect(modal.getByRole("button", { name: "Start extraction" })).toBeDisabled();
  await user.click(modal.getByRole("checkbox", { name: /I authorize.*OpenAI.*tables and schedules/ }));
  await user.click(modal.getByRole("button", { name: "Start extraction" }));
  expect(startExtractionOperation).toHaveBeenCalledWith(scope, {
    documents: [{ revision_document_id: "source", processing_run_id: "processing-version", pages: [1, 2], force_ocr_pages: [2] }],
    families: ["tables"], mode: "ensure",
  }, "tables", expect.any(String));
  expect(started).toHaveBeenCalledWith("operation", "source");
});
