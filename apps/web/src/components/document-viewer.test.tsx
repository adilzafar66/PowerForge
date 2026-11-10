/** @vitest-environment jsdom */
import React from "react";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@/components/query-test-utils";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: {
    href: string;
    children: React.ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
  refresh: vi.fn(),
  back: vi.fn(),
  search: "",
}));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  usePathname: () => "/projects/p-1/revisions/r-2/documents/rd-a",
  useSearchParams: () => new URLSearchParams(nav.search),
}));

vi.mock("@/lib/documents", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/documents")>()),
  getDocument: vi.fn(),
  listPages: vi.fn(),
  getPageArtifactUrl: vi.fn(),
  getProcessing: vi.fn(),
  listClassificationPages: vi.fn(),
  retryProcessing: vi.fn(),
  getDownloadUrl: vi.fn(),
}));

vi.mock("@/lib/extraction", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/extraction")>()),
  getExtractionStatuses: vi.fn(),
  getGroups: vi.fn(),
  getGroupCandidates: vi.fn(),
  getEvidence: vi.fn(),
  getHistory: vi.fn(),
  getRunDetail: vi.fn(),
  getRunSources: vi.fn(),
}));

vi.mock("@/lib/engineering-model", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/engineering-model")>()),
  getEngineeringRegistry: vi.fn().mockResolvedValue({ equipment_types: [] }),
}));

import {
  getEvidence, getExtractionStatuses, getGroupCandidates, getGroups, getHistory,
  getRunDetail, getRunSources, type Candidate, type EvidenceDetail, type ExtractionStatus,
} from "@/lib/extraction";
import { DocumentViewer, DocumentViewerPage } from "@/components/document-viewer";
import {
  getDocument,
  getPageArtifactUrl,
  getProcessing,
  listClassificationPages,
  listPages,
  retryProcessing,
  type DocumentPage,
  type ProcessingSummary,
  type RevisionDocument,
} from "@/lib/documents";
import type { Project, Revision } from "@/lib/projects";

const P = "p-1";
const R = "r-2";
const BASE = `/projects/${P}/revisions/${R}/documents/rd-a`;

const revision = {
  id: R,
  project_id: P,
  identifier: "B",
  description: null,
  status: "ACTIVE",
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:00:00Z",
  created_by: null,
  based_on_revision_id: null,
  based_on_identifier: null,
  system_frequency: null,
  system_phase_count: null,
} as Revision;

function processing(
  overrides: Partial<ProcessingSummary> & Pick<ProcessingSummary, "status">,
): ProcessingSummary {
  return {
    attempt_count: 1,
    pages_processed: 2,
    pages_total: 2,
    error_code: null,
    error_message: null,
    ...overrides,
  };
}

function makeRow(overrides: Partial<RevisionDocument> = {}): RevisionDocument {
  return {
    id: "rd-a",
    revision_id: R,
    document: {
      id: "d-a",
      original_filename: "sld.pdf",
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
    document_number: "E-001",
    description: null,
    notes: null,
    added_at: "2026-10-01T10:00:00Z",
    removed_at: null,
    processing: processing({ status: "COMPLETED" }),
    classification: { enabled: true, suggestion: null, attempt: null },
    ...overrides,
  };
}

function page(number: number, text = 0): DocumentPage {
  return {
    id: `page-${number}`,
    page_number: number,
    source_width: "612",
    source_height: "792",
    source_unit: "POINTS",
    rotation_degrees: 0,
    native_text_char_count: text,
    artifacts: [
      {
        artifact_type: "ANALYSIS_IMAGE",
        mime_type: "image/png",
        width_px: 1275,
        height_px: 1650,
      },
      {
        artifact_type: "THUMBNAIL",
        mime_type: "image/webp",
        width_px: 200,
        height_px: 259,
      },
      ...(text
        ? [
            {
              artifact_type: "NATIVE_TEXT" as const,
              mime_type: "text/plain",
              width_px: null,
              height_px: null,
            },
          ]
        : []),
    ],
  };
}

const pages = vi.mocked(listPages);
const artifactUrl = vi.mocked(getPageArtifactUrl);
let urlVersion = 0;

function renderViewer(row = makeRow()) {
  return render(<DocumentViewer projectId={P} revision={revision} row={row} />);
}

beforeEach(() => {
  nav.search = "";
  vi.mocked(getExtractionStatuses).mockResolvedValue({
    "rd-a": {
      revision_document_id: "rd-a",
      processing_run_id: "processing",
      ineligible_reason: null,
      engineering: { latest_attempt: null, effective_result: null },
      tables: { latest_attempt: null, effective_result: null },
      enrichment: null,
    },
  });
  urlVersion = 0;
  pages.mockResolvedValue([page(1, 120), page(2)]);
  artifactUrl.mockImplementation(async (_p, _r, _d, pageId, type) => ({
    url: `https://files.example/${type}/${pageId}?v=${++urlVersion}`,
    expires_at: "2026-10-10T00:00:00Z",
    filename: "artifact",
  }));
  vi.mocked(getProcessing).mockResolvedValue({
    processing: processing({ status: "COMPLETED" }),
    processor_version: "1.4.0",
    profile_version: "2026.1",
    profile_hash: null,
  });
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("DocumentViewer", () => {
  it("shows the document header, page 1 and its source facts", async () => {
    renderViewer();

    expect(
      screen.getByRole("heading", { level: 1, name: "E-001 — sld.pdf" }),
    ).toBeInTheDocument();
    expect(screen.getByText("2 pages · PDF · Processed")).toBeInTheDocument();
    expect(await screen.findByText("1 / 2")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Page 1" })).toHaveAttribute(
      "src",
      expect.stringContaining("ANALYSIS_IMAGE/page-1"),
    );
    expect(screen.getByText("Page 1 · Native text")).toBeInTheDocument();

    const details = screen.getByRole("complementary", {
      name: "Document details",
    });
    expect(within(details).getByText("Single Line Diagram")).toBeInTheDocument();
    expect(await within(details).findByText("1.4.0")).toBeInTheDocument();
    expect(within(details).getByText("2026.1")).toBeInTheDocument();
    expect(
      within(details).getByRole("button", { name: "Download page text" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Run extraction" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Run extraction" }),
    ).toHaveAccessibleDescription("Extraction scheduling is pending");
  });

  it("reads the page from the URL and writes page changes back", async () => {
    const user = userEvent.setup();
    nav.search = "page=2";
    renderViewer();

    expect(await screen.findByText("2 / 2")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Page 2" })).toBeInTheDocument();
    expect(screen.getByText("Page 2 · No text layer")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next page" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Page 2" }),
    ).toHaveAttribute("aria-current", "page");

    await user.click(screen.getByRole("button", { name: "Previous page" }));
    expect(nav.replace).toHaveBeenLastCalledWith(BASE, { scroll: false });

    await user.click(screen.getByRole("button", { name: "Page 1" }));
    expect(nav.replace).toHaveBeenLastCalledWith(BASE, { scroll: false });
  });

  it("changes pages with the arrow keys, but not while typing", async () => {
    renderViewer();
    await screen.findByText("1 / 2");

    fireEvent.keyDown(window, { key: "ArrowRight" });
    expect(nav.replace).toHaveBeenLastCalledWith(`${BASE}?page=2`, {
      scroll: false,
    });

    nav.replace.mockClear();
    const input = document.createElement("input");
    document.body.append(input);
    fireEvent.keyDown(input, { key: "ArrowRight" });
    expect(nav.replace).not.toHaveBeenCalled();
    input.remove();
  });

  it("zooms in steps and fits the page or width", async () => {
    const user = userEvent.setup();
    renderViewer();
    await screen.findByText("1 / 2");

    const level = screen.getByLabelText("Zoom level");
    expect(level).toHaveTextContent("34%");
    expect(screen.getByRole("button", { name: "Fit page" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(level).toHaveTextContent("49%");
    fireEvent.keyDown(window, { key: "+" });
    expect(level).toHaveTextContent("64%");
    expect(screen.getByRole("button", { name: "Fit page" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );

    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    await user.click(screen.getByRole("button", { name: "Zoom out" }));
    expect(level).toHaveTextContent("30%");
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeDisabled();

    await user.click(screen.getByRole("button", { name: "Fit width" }));
    expect(screen.getByRole("button", { name: "Fit width" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("toggles thumbnails and the details panel", async () => {
    const user = userEvent.setup();
    renderViewer();
    await screen.findByText("1 / 2");

    await user.click(screen.getByRole("button", { name: "Page thumbnails" }));
    expect(screen.getByRole("navigation", { name: "Pages" })).toHaveClass(
      "hidden",
    );
    await user.click(screen.getByRole("button", { name: "Details" }));
    expect(
      screen.getByRole("complementary", { name: "Document details" }),
    ).toHaveClass("hidden");
  });

  it("requests a fresh image URL once when the signed URL has expired", async () => {
    renderViewer();
    const image = await screen.findByRole("img", { name: "Page 1" });
    const first = image.getAttribute("src");

    fireEvent.error(image);
    await waitFor(() =>
      expect(screen.getByRole("img", { name: "Page 1" })).not.toHaveAttribute(
        "src",
        first,
      ),
    );
    const imageCalls = () =>
      artifactUrl.mock.calls.filter(
        ([, , , pageId, type]) =>
          pageId === "page-1" && type === "ANALYSIS_IMAGE",
      ).length;
    expect(imageCalls()).toBe(2);

    fireEvent.error(screen.getByRole("img", { name: "Page 1" }));
    expect(
      await screen.findByText("The page image could not be loaded."),
    ).toBeInTheDocument();
    expect(imageCalls()).toBe(2);
  });

  it("reloads the image element even when the re-signed URL is identical", async () => {
    artifactUrl.mockImplementation(async (_p, _r, _d, pageId, type) => ({
      url: `https://files.example/${type}/${pageId}`,
      expires_at: "2026-10-10T00:00:00Z",
      filename: "artifact",
    }));
    renderViewer();
    const image = await screen.findByRole("img", { name: "Page 1" });
    fireEvent.error(image);
    await waitFor(() =>
      expect(screen.getByRole("img", { name: "Page 1" })).not.toBe(image),
    );
  });

  it("shows an honest unavailable state in evidence mode", async () => {
    const user = userEvent.setup();
    nav.search = "mode=evidence";
    renderViewer();

    const panel = screen.getByRole("complementary", {
      name: "Extraction evidence",
    });
    expect(
      await within(panel).findByText("No compatible results for the current source."),
    ).toBeInTheDocument();
    expect(within(panel).queryByText(/confidence/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: "Extraction Evidence" }),
    ).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Document" }));
    expect(nav.replace).toHaveBeenLastCalledWith(BASE, { scroll: false });
  });

  it.each([
    { label: "OCR", sourceKind: "OCR_TEXT", reading: "OCR", geometry: "OCR_ENGINE" },
    { label: "Native PDF", sourceKind: "NATIVE_TEXT", reading: "NATIVE_PDF", geometry: "NATIVE_DOCUMENT" },
    { label: "Page-only", sourceKind: "VISUAL_REGION", reading: "VISUAL_REPORTED", geometry: "NONE" },
  ] as const)("locates $label on its pinned source and restores group search", async ({ label, sourceKind, reading, geometry }) => {
    const user = userEvent.setup();
    const engineering = "10000000-0000-4000-8000-000000000001";
    const tables = "20000000-0000-4000-8000-000000000002";
    const group = "30000000-0000-4000-8000-000000000003";
    const candidateId = "40000000-0000-4000-8000-000000000004";
    const evidenceId = "50000000-0000-4000-8000-000000000005";
    const run = {
      id: engineering, status: "COMPLETED" as const, processing_run_id: "processing",
      profile_key: "engineering-openai-enriched-v1", created_at: "2026-01-20T12:00:00Z",
    };
    const status: ExtractionStatus = {
      revision_document_id: "rd-a", processing_run_id: "processing", ineligible_reason: null,
      engineering: { latest_attempt: run, effective_result: run },
      tables: { latest_attempt: { ...run, id: tables }, effective_result: { ...run, id: tables } },
      enrichment: null,
    };
    const citation: Candidate["evidence"][number]["evidence"] = {
      id: evidenceId, source_kind: sourceKind, source_snippet: geometry === "NONE" ? null : "5.750 %",
      source_page_number: 2, grounding_precision: geometry === "NONE" ? "VISUAL_PAGE" : "TEXT_OFFSETS",
      source_locator: { reading_basis: reading, geometry_basis: geometry },
    };
    const candidate: Candidate = {
      id: candidateId, run_id: tables, source_group_id: group,
      source_group: { tag_text: "TX-009", label: null }, kind: "ATTRIBUTE_VALUE",
      raw_text: "Impedance", raw_value: "5.750", raw_unit: "%",
      mapping_status: "MAPPED", equipment_type_key: "TWO_WINDING_TRANSFORMER",
      observed_tag: null, attribute_key: "percent_impedance", numeric_value: "5.75",
      integer_value: null, text_value: null, boolean_value: null, unit: "%",
      reason_code: null, explanation: null,
      evidence: [{ role: "PRIMARY", evidence: citation }],
    };
    const detail: EvidenceDetail = {
      ...citation, run_id: tables, processing_run_id: "pinned-processing",
      page_number: 2, region: geometry === "NONE" ? null : { x: "0.25", y: "0.3", width: "0.15", height: "0.02" },
      text_start: geometry === "NONE" ? null : 0, text_end: geometry === "NONE" ? null : 7, source_image_url: "https://files.example/pinned-page.png",
      source_image_width_px: 1200, source_image_height_px: 800, artifact_url_expires_seconds: 90,
    };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": status });
    vi.mocked(getGroups).mockResolvedValue({
      items: [
        { run_id: engineering, family: "engineering", source_group_id: group, label: null, tag_text: "TX-009", equipment_type_hint: null, page_numbers: [2], candidate_count: 1 },
        { run_id: tables, family: "tables", source_group_id: group, label: null, tag_text: "TX-009", equipment_type_hint: null, page_numbers: [2], candidate_count: 1 },
      ],
      total: 2, limit: 25, offset: 0,
    });
    vi.mocked(getGroupCandidates).mockResolvedValue({ items: [candidate], total: 1, limit: 20, offset: 0 });
    vi.mocked(getEvidence).mockResolvedValue(detail);
    nav.search = "mode=evidence&groupSearch=TX-009";
    const view = renderViewer();
    function followLastPush() {
      nav.search = nav.push.mock.lastCall?.[0].split("?")[1] ?? "";
      view.rerender(<DocumentViewer projectId={P} revision={revision} row={makeRow()} />);
    }

    expect(await screen.findByRole("tab", { name: "Candidates" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByRole("tab")).toHaveLength(2);
    await user.click(await screen.findByRole("button", { name: /TX-009.*Tables/ }));
    expect(getGroups).toHaveBeenCalledWith(expect.anything(), { engineering, tables }, expect.objectContaining({ search: "TX-009" }), 0, expect.anything());
    followLastPush();
    await user.click(await screen.findByRole("button", { name: /Percent impedance/ }));
    followLastPush();

    const image = await screen.findByRole("img", { name: "Pinned source page 2" });
    expect(image).toHaveAttribute("src", detail.source_image_url);
    expect(screen.queryByRole("img", { name: "Grounded source region" })).toBeNull();
    fireEvent.load(image);
    if (geometry === "NONE") {
      expect(screen.queryByRole("img", { name: "Grounded source region" })).toBeNull();
      expect(screen.getByText("Page-level citation. No grounded highlight is available.")).toBeVisible();
    } else {
      expect(await screen.findByText("Source highlighted on page")).toBeInTheDocument();
      expect(screen.getByRole("img", { name: "Grounded source region" })).toHaveStyle({ left: "25%", top: "30%" });
    }
    expect(screen.getByText("Original reading").parentElement).toHaveTextContent("5.750 %");
    expect(screen.getByText(label, { exact: true })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Back to source groups" }));
    followLastPush();
    expect(await screen.findByRole("searchbox", { name: "Search source groups" })).toHaveValue("TX-009");
    expect(screen.getByRole("button", { name: /TX-009.*Engineering/ })).toBeInTheDocument();
  });

  it("keeps a historical run pair fixed even after current results arrive", async () => {
    const historical = "10000000-0000-4000-8000-000000000001";
    const latest = "20000000-0000-4000-8000-000000000002";
    const latestTables = "30000000-0000-4000-8000-000000000003";
    const run = { id: latest, status: "COMPLETED" as const, processing_run_id: "processing", profile_key: "engineering-openai-enriched-v1", created_at: "2026-01-20T12:00:00Z" };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": {
      revision_document_id: "rd-a", processing_run_id: "processing", ineligible_reason: null,
      engineering: { latest_attempt: run, effective_result: run },
      tables: { latest_attempt: { ...run, id: latestTables }, effective_result: { ...run, id: latestTables } },
      enrichment: null,
    } });
    vi.mocked(getGroups).mockResolvedValue({ items: [], total: 0, limit: 25, offset: 0 });
    nav.search = `mode=evidence&evidencePinned=1&engineeringRun=${historical}`;
    renderViewer();
    expect(await screen.findByText("No source groups match the selected results and filters.")).toBeVisible();
    expect(getGroups).toHaveBeenCalledTimes(1);
    expect(getGroups).toHaveBeenCalledWith(expect.anything(), { engineering: historical, tables: null }, expect.anything(), 0, expect.anything());
  });

  it("starts an explicit historical selection without taking the other family's current result", async () => {
    const user = userEvent.setup();
    const historical = "10000000-0000-4000-8000-000000000001";
    const latestTables = "20000000-0000-4000-8000-000000000002";
    const run = {
      id: historical, status: "COMPLETED" as const, processing_run_id: "historic-processing",
      profile_key: "engineering-openai-enriched-v1", created_at: "2026-01-19T10:00:00Z",
      selected_pages: [1], pages_processed: 1, error_code: null,
    };
    const tables = { ...run, id: latestTables, processing_run_id: "current-processing" };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": {
      revision_document_id: "rd-a", processing_run_id: "current-processing", ineligible_reason: null,
      engineering: { latest_attempt: run, effective_result: null },
      tables: { latest_attempt: tables, effective_result: tables },
      enrichment: null,
    } });
    vi.mocked(getHistory).mockImplementation(async (_scope, family) => ({
      items: family === "engineering" ? [run] : [], total: family === "engineering" ? 1 : 0, limit: 10, offset: 0,
    }));
    vi.mocked(getRunDetail).mockResolvedValue({
      run, attempts: [], coverage: { required_units: 1, completed_required_units: 1 },
    });
    vi.mocked(getRunSources).mockResolvedValue({ items: [] });
    nav.search = "mode=evidence&evidenceTab=history";
    const view = renderViewer();
    await user.click(await screen.findByRole("button", { name: /Run 10000000/ }));
    nav.search = nav.push.mock.lastCall?.[0].split("?")[1] ?? "";
    view.rerender(<DocumentViewer projectId={P} revision={revision} row={makeRow()} />);
    await user.click(await screen.findByRole("button", { name: "Browse candidates" }));
    const next = new URLSearchParams(nav.push.mock.lastCall?.[0].split("?")[1]);
    expect(next.get("historicalPair")).toBe("1");
    expect(next.get("engineeringRun")).toBe(historical);
    expect(next.has("tablesRun")).toBe(false);
  });

  it("explains running processing without requesting pages", async () => {
    renderViewer(
      makeRow({
        processing: processing({
          status: "RUNNING",
          pages_processed: 3,
          pages_total: 12,
        }),
      }),
    );
    expect(
      screen.getByText("Pages are still processing"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/3 of 12 pages processed/),
    ).toBeInTheDocument();
    expect(pages).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeDisabled();
  });

  it("offers retry when processing failed", async () => {
    const user = userEvent.setup();
    vi.mocked(retryProcessing).mockResolvedValue({
      processing: processing({ status: "PENDING" }),
      processor_version: null,
      profile_version: null,
      profile_hash: null,
    });
    renderViewer(
      makeRow({
        processing: processing({
          status: "FAILED",
          error_message: "The PDF could not be rendered.",
        }),
      }),
    );
    expect(
      screen.getByText("The PDF could not be rendered."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry processing" }));
    expect(retryProcessing).toHaveBeenCalledWith(P, R, "rd-a");
  });

  it("shows a not-ready state when pages return 409", async () => {
    pages.mockRejectedValue(
      Object.assign(new Error("Processing is not complete."), {
        apiError: {
          detail: "Processing is not complete.",
          code: "processing_not_complete",
        },
        status: 409,
      }),
    );
    renderViewer();
    expect(
      await screen.findByText("Pages are not ready yet"),
    ).toBeInTheDocument();
    expect(pages).toHaveBeenCalledTimes(1);
  });

  it("labels mixed-document pages with their page classification", async () => {
    vi.mocked(listClassificationPages).mockResolvedValue([
      { page_number: 1, predicted_type: "PANEL_SCHEDULE", confidence_band: "HIGH" },
    ]);
    renderViewer(makeRow({ document_type: "MIXED_DOCUMENT" }));
    expect(
      await screen.findByText("Page 1 · Panel Schedule · Native text"),
    ).toBeInTheDocument();
  });

  it("keeps removed documents viewable", async () => {
    renderViewer(makeRow({ status: "REMOVED" }));
    expect(screen.getByText("Removed from revision")).toBeInTheDocument();
    expect(await screen.findByRole("img", { name: "Page 1" })).toBeInTheDocument();
  });
});

describe("DocumentViewerPage", () => {
  it("explains when the document is not part of the revision", async () => {
    vi.mocked(getDocument).mockRejectedValue(
      Object.assign(new Error("Not found"), {
        apiError: { detail: "Not found" },
        status: 404,
      }),
    );
    render(
      <DocumentViewerPage
        initialProject={{ id: P } as Project}
        initialRevision={revision}
        initialRevisions={[revision]}
        documentId="rd-a"
      />,
    );
    expect(await screen.findByText("Document not found")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Back to documents" }),
    ).toHaveAttribute("href", `/projects/${P}/revisions/${R}`);
  });
});
