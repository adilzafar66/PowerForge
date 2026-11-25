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
      extraction: { latest_attempt: null, effective_result: null },
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
    const launch = screen.getByRole("button", { name: "Run extraction" });
    expect(launch).toBeEnabled();
    await userEvent.setup().click(launch);
    expect(nav.push).toHaveBeenLastCalledWith(`/projects/${P}/revisions/${R}?document=rd-a&extract=ensure`);
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
      await within(panel).findByText("No published candidates. Check run history for extraction progress."),
    ).toBeInTheDocument();
    expect(within(panel).queryByText(/confidence/i)).toBeNull();
    expect(
      screen.getByRole("button", { name: "Extraction Evidence" }),
    ).toHaveAttribute("aria-pressed", "true");

    await user.click(screen.getByRole("button", { name: "Document" }));
    expect(nav.replace).toHaveBeenLastCalledWith(BASE, { scroll: false });
  });

  it.each([
    { localization: "RESOLVED", label: "Matches cited text", support: "TEXT_MATCH", inferred: false },
    { localization: "VISUAL_REPORTED", label: "Cited value differs", support: "TEXT_MISMATCH", inferred: false },
    { localization: "UNRESOLVED", label: "Not verified", support: "UNVERIFIED", inferred: false },
    { localization: "UNRESOLVED", label: "Inferred without a direct citation", support: "UNVERIFIED", inferred: true },
  ] as const)("shows $label with the appropriate source context", async ({ localization, label, support, inferred }) => {
    const user = userEvent.setup();
    const runId = "10000000-0000-4000-8000-000000000001";
    const groupId = "30000000-0000-4000-8000-000000000003";
    const candidateId = "40000000-0000-4000-8000-000000000004";
    const evidenceId = "50000000-0000-4000-8000-000000000005";
    const run = { id: runId, status: "COMPLETED" as const, processing_run_id: "processing", profile_key: "phase-6r", created_at: "2026-01-20T12:00:00Z" };
    const status: ExtractionStatus = {
      revision_document_id: "rd-a", processing_run_id: "processing", ineligible_reason: null,
      extraction: { latest_attempt: run, effective_result: run }, enrichment: null,
    };
    const candidate: Candidate = {
      id: candidateId, page_id: "page-two", attempt_id: "attempt", kind: "ATTRIBUTE",
      equipment_id: groupId, association: "UNCERTAIN", raw_unmapped: false,
      origin: "EXTRACTED", attribute_display_name: "Percent Impedance",
      raw_label: "Z", raw_value: "5.750", raw_unit: "pct", qualifiers: [], value_form: "SINGLE",
      proposed_value: null, proposed_unit: "%", inference_explanation: null, inference_basis: null,
      source_expression: null, source_display_label: null, redundant_with_id: null,
      mapping_status: "MAPPED", proposed_attribute_key: "percent_impedance", alternate_representations: [],
      normalized: { type: "NUMBER", value: "5.75", unit: "%" }, conflict: false, reason_code: null,
      value_source_support: support, evidence_ids: inferred ? [] : [evidenceId],
      ...(inferred ? {
        origin: "INFERRED", raw_label: null, raw_value: null, raw_unit: null, value_form: null,
        proposed_value: "5.75", proposed_unit: "%",
        inference_explanation: "Example proposal from equipment context.",
        inference_basis: "EQUIPMENT_CHARACTERISTICS",
      } : {}),
    };
    const region = { x: "0.25", y: "0.3", width: "0.15", height: "0.02" };
    const detail: EvidenceDetail = {
      id: evidenceId, candidate_id: candidateId, page_id: "page-two", page_image_id: "pinned-image",
      role: "VALUE", candidate_value_source_support: support, page_image_width: 1200, page_image_height: 800,
      page_image: { id: "pinned-image", url: "https://files.example/pinned-page.png", sha256: "digest", expires_seconds: 90 },
      ...(localization === "RESOLVED"
        ? { localization, modality: "NATIVE_PDF", quote: "5.750 %", source_issues: [], regions: [region, { ...region, x: "0.5" }] }
        : localization === "VISUAL_REPORTED"
          ? { localization, region, reported_text: "5.750" }
          : { localization, reason_code: "NO_CITATION" }),
    };
    const group = { group_id: groupId, kind: "EQUIPMENT" as const, label: "TX-009", tag: "TX-009",
      registry_type: null, page_numbers: [2], matching_candidate_count: 1,
      matching_attribute_count: 1, matching_identification_count: 0, source_description: "Transformer" };
    const paging = { total: 1, next_cursor: null, previous_cursor: null };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": status });
    vi.mocked(getGroups).mockResolvedValue({ ...paging, items: [group] });
    vi.mocked(getGroupCandidates).mockResolvedValue({ ...paging, items: [candidate], group, identification: null });
    vi.mocked(getRunSources).mockResolvedValue({ items: [{
      page_id: "page-two", page_number: 2, page_image_id: "pinned-image", prepared_result_id: "prep",
      spatial_result_id: "layout", layout_producer_run_id: "producer", prepared_manifest_hash: "hash", spatial_manifest_hash: "hash", page_context_hash: "page-hash",
    }] });
    vi.mocked(getEvidence).mockResolvedValue(detail);
    nav.search = "mode=evidence&search=TX-009";
    const view = renderViewer();
    function followLastPush() {
      nav.search = nav.push.mock.lastCall?.[0].split("?")[1] ?? "";
      view.rerender(<DocumentViewer projectId={P} revision={revision} row={makeRow()} />);
    }
    await user.click(await screen.findByRole("button", { name: /TX-009/ }));
    expect(getGroups).toHaveBeenCalledWith(expect.anything(), runId, expect.objectContaining({ search: "TX-009" }), null, expect.anything());
    followLastPush();
    const valueLabel = inferred ? /Percent Impedance.*5.75 %.*Inferred/ : /Percent Impedance.*5.75 %.*Extracted/;
    await user.click(await screen.findByRole("button", { name: valueLabel }));
    followLastPush();
    if (inferred) {
      expect(await screen.findByText("Example proposal from equipment context.")).toBeVisible();
      expect(screen.getByText("Equipment characteristics")).toBeVisible();
      expect(screen.queryByText("Original PDF label")).toBeNull();
      expect(screen.queryByRole("list", { name: "Inference context references" })).toBeNull();
      expect(getEvidence).not.toHaveBeenCalled();
      return;
    }
    expect(await screen.findByText("Original PDF label")).toHaveTextContent("Original PDF label Z");
    expect(screen.getByText("Raw value")).toHaveTextContent("Raw value 5.750");
    expect(screen.getByText("Source unit")).toHaveTextContent("Source unit pct");
    expect(screen.getByText("Proposed unit")).toHaveTextContent("Proposed unit %");
    const image = await screen.findByRole("img", { name: "Pinned source page 2" });
    expect(image).toHaveAttribute("src", detail.page_image.url);
    expect(screen.queryByRole("img", { name: "Grounded source region" })).toBeNull();
    fireEvent.load(image);
    expect(screen.getByText(label, { exact: true })).toBeVisible();
    expect(screen.getByText("Uncertain", { exact: true })).toBeVisible();
    expect(screen.queryAllByRole("img", { name: "Grounded source region" })).toHaveLength(localization === "RESOLVED" ? 2 : 0);
    expect(screen.queryAllByRole("img", { name: "Approximate visual region" })).toHaveLength(localization === "VISUAL_REPORTED" ? 1 : 0);
    await user.click(screen.getByRole("button", { name: "Back to source groups" }));
    followLastPush();
    expect(await screen.findByRole("searchbox", { name: "Search source groups" })).toHaveValue("TX-009");
  });

  it.each([
    { title: "Enclosure Width", rawValue: "20 in (508.000 mm)", rawUnit: "in",
      proposal: "20.000", unit: "in", status: "MAPPED" as const, display: "508 mm",
      normalized: { type: "NUMBER", value: "508", unit: "mm" },
      form: "EQUIVALENT_UNITS" as const, alternates: [{ value: "508.000", unit: "mm" }] },
    { title: "Nominal Voltage", rawValue: "400/600 V", rawUnit: "V",
      proposal: "400/600", unit: "V", status: "UNMAPPED" as const, display: "400/600 V",
      form: "MULTIPLE" as const, reason: "PROPOSAL_TYPE_MISMATCH" },
    { title: "Normally Closed", rawValue: "Yes", proposal: false,
      status: "INVALID" as const, display: "false", reason: "SOURCE_VALUE_MISMATCH" },
    { title: "Pole Count", rawValue: null, proposal: BigInt("9007199254740993"),
      status: "UNMAPPED" as const, display: "9007199254740993", inferred: true },
    { title: "Primary Connection", rawValue: "Star", proposal: "WYE",
      status: "MAPPED" as const, display: "WYE", normalized: { type: "ENUM", value: "WYE", unit: null } },
    { title: "Model", rawValue: "Model: 00-AB 75", proposal: "00-AB 75",
      status: "MAPPED" as const, display: "00-AB 75",
      normalized: { type: "TEXT", value: "00-AB 75", unit: null } },
    { title: "Manufacturer", rawValue: "Unknown", proposal: null,
      status: "UNMAPPED" as const, display: "Unknown", reason: "NO_VALUE_PROPOSAL" },
  ])("renders the recorded $title value and provenance", async (example) => {
    const runId = "10000000-0000-4000-8000-000000000001";
    const groupId = "30000000-0000-4000-8000-000000000003";
    const candidateId = "40000000-0000-4000-8000-000000000004";
    const run = { id: runId, status: "COMPLETED" as const, processing_run_id: "processing",
      profile_key: "phase-6r", created_at: "2026-01-20T12:00:00Z" };
    const candidate: Candidate = {
      id: candidateId, page_id: "page-two", attempt_id: "attempt", kind: "ATTRIBUTE",
      equipment_id: groupId, association: "ASSERTED", raw_unmapped: false,
      origin: example.inferred ? "INFERRED" : "EXTRACTED", attribute_display_name: example.title,
      raw_label: null, raw_value: example.rawValue, raw_unit: example.rawUnit ?? null,
      qualifiers: [], value_form: example.inferred ? null : example.form ?? "SINGLE",
      proposed_value: example.proposal, proposed_unit: example.unit ?? null,
      alternate_representations: example.alternates ?? [], proposed_attribute_key: "field",
      inference_explanation: example.inferred ? "A synthetic contextual proposal." : null,
      inference_basis: null, source_expression: null, source_display_label: null,
      redundant_with_id: null, mapping_status: example.status, normalized: example.normalized ?? null,
      conflict: false, reason_code: example.reason ?? null, value_source_support: "UNVERIFIED",
      evidence_ids: [],
    };
    const group = { group_id: groupId, kind: "EQUIPMENT" as const, label: "Assembly",
      source_description: "Assembly", tag: null, registry_type: "BUS", page_numbers: [2],
      matching_candidate_count: 1, matching_attribute_count: 1, matching_identification_count: 0 };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": {
      revision_document_id: "rd-a", processing_run_id: "processing", ineligible_reason: null,
      extraction: { latest_attempt: run, effective_result: run }, enrichment: null,
    } });
    vi.mocked(getRunSources).mockResolvedValue({ items: [] });
    vi.mocked(getGroupCandidates).mockResolvedValue({
      total: 1, next_cursor: null, previous_cursor: null, group, items: [candidate], identification: null,
    });
    nav.search = `mode=evidence&extractionRun=${runId}&equipmentGroup=${groupId}&candidate=${candidateId}`;
    renderViewer();
    const registry = await screen.findByRole("region", { name: "Registry attributes" });
    const card = within(registry).getByRole("button", { name: new RegExp(example.title) });
    expect(card).toHaveTextContent(example.display);
    expect(card).toHaveTextContent(example.inferred ? "Inferred" : "Extracted");
    expect(within(registry).getByText("Proposed value")).toHaveTextContent(
      example.proposal == null ? "Unavailable" : String(example.proposal),
    );
    if (example.rawValue === null) expect(within(registry).queryByText("Raw value")).toBeNull();
    else expect(within(registry).getByText("Raw value")).toHaveTextContent(example.rawValue);
    if (example.normalized) expect(within(registry).getByText("Normalized value")).toHaveTextContent(example.normalized.value);
    if (example.alternates) {
      expect(within(registry).getByText("Alternate representations")).toBeVisible();
      expect(within(registry).getByText("508.000 mm")).toBeVisible();
    }
  });

  it("separates identification, registry values, unmapped facts and repeated assertions", async () => {
    const user = userEvent.setup();
    const runId = "10000000-0000-4000-8000-000000000001";
    const groupId = "30000000-0000-4000-8000-000000000003";
    const valueId = "40000000-0000-4000-8000-000000000004";
    const duplicateId = "40000000-0000-4000-8000-000000000005";
    const rawId = "40000000-0000-4000-8000-000000000006";
    const run = { id: runId, status: "COMPLETED" as const, processing_run_id: "processing",
      profile_key: "phase-6r", created_at: "2026-01-20T12:00:00Z" };
    const common = { page_id: "page-two", attempt_id: "attempt", mapping_status: "MAPPED" as const,
      conflict: false, reason_code: null, evidence_ids: [] };
    const equipment: Extract<Candidate, { kind: "EQUIPMENT" }> = {
      ...common, id: groupId, kind: "EQUIPMENT", display_name: "LV Breaker 1",
      source_description: "A complete original device description", registry_type: "LV_BREAKER",
      tag: null, tag_state: "ABSENT", qualification: "INSTALLED", raw_qualification: null,
    };
    const value: Extract<Candidate, { kind: "ATTRIBUTE" }> = {
      ...common, id: valueId, kind: "ATTRIBUTE", equipment_id: groupId, association: "ASSERTED",
      origin: "EXTRACTED", attribute_display_name: "Trip Unit Model", raw_unmapped: false,
      raw_label: "Trip Unit", raw_value: "MODEL-X", raw_unit: null,
      proposed_value: null, proposed_unit: null, inference_explanation: null, inference_basis: null,
      source_expression: null, source_display_label: null, redundant_with_id: null,
      value_source_support: "UNVERIFIED", qualifiers: [], value_form: "SINGLE",
      proposed_attribute_key: "trip_unit_model", alternate_representations: [],
      normalized: { type: "TEXT", value: "MODEL-X", unit: null },
    };
    const duplicate: Candidate = { ...value, id: duplicateId, redundant_with_id: valueId,
      qualifiers: ["Protection functions"], normalized: null,
      mapping_status: "UNMAPPED", reason_code: "UNREPRESENTABLE_VALUE_FORM" };
    const raw: Candidate = { ...value, id: rawId, raw_unmapped: true,
      raw_label: "Branch device", source_display_label: "Current Rating (Unspecified)",
      attribute_display_name: null, proposed_attribute_key: null, raw_value: "600A",
      raw_unit: "A", mapping_status: "UNMAPPED", normalized: null, reason_code: "UNSUPPORTED_ATTRIBUTE" };
    const group = { group_id: groupId, kind: "EQUIPMENT" as const, label: equipment.display_name,
      source_description: equipment.source_description, tag: null, registry_type: "LV_BREAKER",
      page_numbers: [2], matching_candidate_count: 4, matching_attribute_count: 3,
      matching_identification_count: 1 };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": {
      revision_document_id: "rd-a", processing_run_id: "processing", ineligible_reason: null,
      extraction: { latest_attempt: run, effective_result: run }, enrichment: null,
    } });
    vi.mocked(getRunSources).mockResolvedValue({ items: [] });
    vi.mocked(getGroupCandidates).mockImplementation(async (_scope, _run, _group, _filters, _cursor, _signal, id) => ({
      total: 4, next_cursor: null, previous_cursor: null, group, identification: equipment,
      items: id ? [duplicate] : [equipment, value, duplicate, raw],
    }));
    nav.search = `mode=evidence&extractionRun=${runId}&equipmentGroup=${groupId}`;
    const view = renderViewer();
    const identification = await screen.findByRole("region", { name: "Equipment identification" });
    expect(within(identification).getByRole("button", { name: /LV Breaker 1/ })).toBeVisible();
    const registry = screen.getByRole("region", { name: "Registry attributes" });
    expect(within(registry).getAllByRole("button")).toHaveLength(1);
    expect(within(registry).queryByText("LV Breaker 1")).toBeNull();
    expect(screen.getByRole("region", { name: "Unmapped source attributes" })).toHaveTextContent("Current Rating (Unspecified)");
    await user.click(screen.getByText("Possible repeated assertions"));
    const repeat = screen.getByText("Possible repeated assertions").closest("details")!;
    expect(within(repeat).getByRole("button", { name: /Trip Unit Model/ })).toBeVisible();
    await user.click(within(repeat).getByRole("button", { name: /Trip Unit Model/ }));
    nav.search = nav.push.mock.lastCall?.[0].split("?")[1] ?? "";
    view.rerender(<DocumentViewer projectId={P} revision={revision} row={makeRow()} />);
    await user.click(await screen.findByRole("button", { name: "View related assertion" }));
    expect(nav.push.mock.lastCall?.[0]).toContain(`candidate=${valueId}`);
  });

  it.each([0, 1])("keeps a selected historical run fixed with %i overflowed", async (overflowed) => {
    const historical = "10000000-0000-4000-8000-000000000001";
    const latest = "20000000-0000-4000-8000-000000000002";
    const run = { id: latest, status: "COMPLETED" as const, processing_run_id: "processing", profile_key: "phase-6r", created_at: "2026-01-20T12:00:00Z" };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": {
      revision_document_id: "rd-a", processing_run_id: "processing", ineligible_reason: null,
      extraction: { latest_attempt: run, effective_result: run }, enrichment: null,
    } });
    vi.mocked(getGroups).mockResolvedValue({ items: [], total: 0, next_cursor: null, previous_cursor: null });
    vi.mocked(getRunSources).mockResolvedValue({ items: [{
      page_id: "page-one", page_number: 1, page_image_id: "pinned-image",
      prepared_result_id: "prep", spatial_result_id: "layout", layout_producer_run_id: "producer",
      prepared_manifest_hash: "hash", spatial_manifest_hash: "hash", page_context_hash: "page-hash",
      assertion_counts: { received: 5 + overflowed, accepted: 3, quarantined: 2, overflowed },
    }] });
    nav.search = `mode=evidence&extractionRun=${historical}`;
    renderViewer();
    expect(await screen.findByText("No candidates match these filters.")).toBeVisible();
    expect(getGroups).toHaveBeenCalledWith(expect.anything(), historical, expect.anything(), null, expect.anything());
    const summary = overflowed ? /3 of 6 assertions were accepted/ : /3 of 5 assertions passed schema validation/;
    expect(await screen.findByText(summary)).toHaveTextContent("2 quarantined assertions");
    if (overflowed) expect(screen.getByText(/1 raw-unmapped assertion exceeded/)).toBeVisible();
  });

  it.each([0, 1])("opens run details with %i overflowed and candidates unavailable", async (overflowed) => {
    const user = userEvent.setup();
    const historical = "10000000-0000-4000-8000-000000000001";
    const run = {
      id: historical, status: "COMPLETED" as const, processing_run_id: "historic-processing",
      profile_key: "phase-6r", created_at: "2026-01-19T10:00:00Z", model: "fake", profile_version: "v1",
      profile_hash: "hash", selected_pages: [1], pages_processed: 1, error_code: null,
    };
    vi.mocked(getExtractionStatuses).mockResolvedValue({ "rd-a": {
      revision_document_id: "rd-a", processing_run_id: "current-processing", ineligible_reason: null,
      extraction: { latest_attempt: run, effective_result: null }, enrichment: null,
    } });
    vi.mocked(getHistory).mockResolvedValue({ items: [run], total: 1, next_cursor: null, previous_cursor: null });
    vi.mocked(getRunDetail).mockResolvedValue({
      run, attempts: [{
        id: "attempt", stage: "ATTRIBUTE_EXTRACTION", status: "COMPLETED", page_numbers: [1],
        attempt_number: 1, retryable: false, error_code: null, provider_calls: 1,
        latency_ms: 2000, stage_outcome: "RESULT", result_sha256: "hash", usage: null,
        estimated_cost: null, validation_diagnostics: [], stage_diagnostics: [],
        assertion_validation: {
          state: "PARTIALLY_VALIDATED", counts: { received: 2 + overflowed, accepted: 1, quarantined: 1, overflowed },
          rejections: [{ category: "FIELD_CONSTRAINT", error_type: "string_too_short", path: ["attributes", 0, "raw_value"] }],
        },
      }], coverage: { required_units: 1, completed_required_units: 1 },
      can_browse_candidates: false, can_retry: false, can_cancel: false, execution: null,
    });
    vi.mocked(getRunSources).mockResolvedValue({ items: [] });
    nav.search = "mode=evidence&evidenceTab=history";
    const view = renderViewer();
    await user.click(await screen.findByRole("button", { name: /Pages 1/ }));
    nav.search = nav.push.mock.lastCall?.[0].split("?")[1] ?? "";
    view.rerender(<DocumentViewer projectId={P} revision={revision} row={makeRow()} />);
    expect(await screen.findByRole("region", { name: "Selected extraction run" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Browse candidates" })).toBeNull();
    expect(screen.getByText("Partially validated")).toBeVisible();
    expect(screen.getByText(overflowed
      ? "3 received · 1 accepted · 1 quarantined · 1 above the raw-unmapped limit"
      : "2 received · 1 schema-valid · 1 quarantined")).toBeVisible();
    await user.click(screen.getByText("Quarantined assertions"));
    expect(screen.getByText(/attributes.0.raw_value/)).toBeVisible();
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
