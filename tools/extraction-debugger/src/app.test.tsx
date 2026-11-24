// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./main";
import { AssertionFields, JsonTree, parseInspectorJson } from "./inspector";
import type { Attempt, Detail } from "./api";

const id = "10000000-0000-4000-8000-000000000001";
const attempt: Attempt = {
  attempt_id: id, run_id: "20000000-0000-4000-8000-000000000001", document: "Siemens fixture.pdf", page: 1,
  attempt_number: 1, status: "COMPLETED", provider: "openai", model: "test", validation: "partial",
  received: 3, accepted: 2, quarantined: 1, output_bytes: 120, output_sha256: "digest",
  finished_at: "2026-01-01T10:00:00Z", expires_at: "2099-01-01T10:00:00Z",
  retained: true, duration_ms: 78600, input_tokens: 100, cached_input_tokens: null,
  output_tokens: 50, cost: null, pricing_basis: null, published: 2, error_code: null,
};
const detail: Detail = {
  attempt, request_sha256: "request", result_sha256: "result", upstream_sha256: "upstream",
  schema_version: "test", prompt_version: "test", fatal: [], validated: null, candidates: [],
  rejections: [{ collection: "attributes", index: 24,
    issues: [{ category: "FIELD_CONSTRAINT", error_type: "string_too_short", path: ["attributes", 24, "raw_value"] }] }],
};
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function serve(record = detail, raw = '{"attributes":[{"raw_value":"<img src=x onerror=alert(1)> Ω"}]}', error?: string) {
  const fetch = vi.fn(async (url: string) => {
    if (url.endsWith("/original")) return error ? Response.json({ detail: error }, { status: 409 }) : new Response(raw);
    if (url.startsWith("/api/attempts?")) return Response.json({ items: [record.attempt], next_cursor: null });
    return Response.json(record);
  });
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

it("shows when historical model information is unavailable", async () => {
  serve({ ...detail, attempt: { ...attempt, model: null } });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture.*Model unavailable/ }));
  const model = await screen.findByText("Provider and model");
  expect(model.parentElement?.textContent).toContain("openai · Model unavailable");
});

it("navigates to the original index and reveals raw only on request", async () => {
  const fetch = serve();
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  const rejected = await screen.findByRole("button", { name: /attributes\[24\]/ });
  fireEvent.click(rejected);
  expect(screen.getByText("attributes[24].raw_value")).toBeTruthy();
  expect(screen.getByText("Original assertion content is unavailable.")).toBeTruthy();
  expect(fetch.mock.calls.some(([url]) => url.endsWith("/original"))).toBe(false);
  fireEvent.click(screen.getByRole("button", { name: "Reveal original response" }));
  await screen.findByRole("button", { name: "Original response verified" });
  fireEvent.click(screen.getByRole("button", { name: "Raw text" }));
  expect(screen.getByText(/<img src=x onerror=alert/)).toBeTruthy();
  expect(document.querySelector("img")).toBeNull();
  fireEvent.change(screen.getByLabelText("Show"), { target: { value: "quarantined" } });
  expect(screen.queryByRole("button", { name: /attributes\[0\]/ })).toBeNull();
  fireEvent.change(screen.getByLabelText("Validation"), { target: { value: "partial" } });
  expect(fetch.mock.calls.some(([url]) => url.includes("validation=partial"))).toBe(true);
});

it("denies reveal for expired output and reports missing objects separately", async () => {
  const expired = { ...detail, attempt: { ...attempt, retained: false } };
  serve(expired);
  const first = render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  expect((await screen.findByRole("button", { name: "Reveal original response" }) as HTMLButtonElement).disabled).toBe(true);
  first.unmount();
  serve(detail, "", "object_missing");
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Reveal original response" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The original audit object is unexpectedly missing.");
});

it("renders malformed JSON as literal original text", async () => {
  serve({ ...detail, attempt: { ...attempt, validation: "fatal" } }, "{unfinished Ω");
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Reveal original response" }));
  await screen.findByRole("button", { name: "Original response verified" });
  fireEvent.click(screen.getByRole("button", { name: "JSON tree" }));
  expect(screen.getByText("Invalid JSON. Showing original text.")).toBeTruthy();
  expect(screen.getByText("{unfinished Ω")).toBeTruthy();
});

it("expands JSON without rendering source content as HTML", () => {
  const view = render(<JsonTree value={{ nested: { name: "<script>test</script>", long: "Ω".repeat(500) } }} />);
  const node = within(view.container).getByText("nested").closest("details")!;
  expect(node.open).toBe(false);
  node.open = true;
  fireEvent(node, new Event("toggle", { bubbles: false }));
  expect(within(node).getByText(/<script>test<\/script>/)).toBeTruthy();
  expect(view.container.querySelector("script")).toBeNull();
});

it("correlates shifted indices and compares an unmapped candidate using recorded values", async () => {
  const original = Array.from({ length: 26 }, (_, index) => ({
    local_ref: `a${index}`, origin: "EXTRACTED", raw_value: index === 24 ? "" : `raw ${index}`,
  }));
  const shifted: Detail = {
    ...detail, attempt: { ...attempt, received: 26, accepted: 25 },
    validated: { attributes: original.filter((_, index) => index !== 24), raw_unmapped: [] },
    candidates: [{ ordinal: 24, local_ref: "a25", mapping_status: "UNMAPPED", reason_code: "unit_unverified",
      proposed_value: null, alternate_representations: null,
      normalized_type: null, normalized_value: null, normalized_unit: null, evidence: [] }],
  };
  serve(shifted, JSON.stringify({ attributes: original, raw_unmapped: [] }));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Reveal original response" }));
  await screen.findByRole("button", { name: "Original response verified" });
  fireEvent.change(screen.getByLabelText("Show"), { target: { value: "UNMAPPED" } });
  fireEvent.click(await screen.findByRole("button", { name: /attributes\[25\]/ }));
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  expect(screen.getByText("Original · attributes[25]")).toBeTruthy();
  expect(screen.getByText("Validated assertion")).toBeTruthy();
  expect(screen.getByText("unit_unverified")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /attributes\[24\]/ })).toBeNull();
});

it("disables export after an integrity failure", async () => {
  serve(detail, "", "integrity_failed");
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByRole("button", { name: "Reveal original response" }));
  expect(await screen.findByRole("alert")).toHaveProperty("textContent", "The audit object failed its size or checksum verification.");
  expect((screen.getByRole("button", { name: "Export original" }) as HTMLButtonElement).disabled).toBe(true);
});

it("shows validated historical assertions without inventing original positions", async () => {
  serve({ ...detail, rejections: [], attempt: { ...attempt, received: null, accepted: null,
    quarantined: null, validation: null, retained: null }, validated: {
      version: "phase-6r-attributes-v5",
      attributes: [{ local_ref: "historical", raw_value: "Star", proposed_enum_value: "WYE" }], raw_unmapped: [],
    } });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByRole("button", { name: /Validated attributes\[0\]/ }));
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  expect(screen.getByText("Original position unavailable")).toBeTruthy();
  expect(screen.getByText("Validated assertion")).toBeTruthy();
  const fields = screen.getByLabelText("Recorded assertion fields");
  expect(within(fields).getByText("Historical enum proposal")).toBeTruthy();
  expect(within(fields).getByText('"WYE"')).toBeTruthy();
});

it.each([
  ["false", "false", "(boolean)"],
  ['"false"', '"false"', "(string)"],
  ["9007199254740993", "9007199254740993", "(integer)"],
  ["1.0", "1.0", "(number)"],
  ['"015.750"', '"015.750"', "(string)"],
  ['"400/600"', '"400/600"', "(string)"],
  ["null", "null", "(null)"],
])("distinguishes the recorded JSON proposal %s", (literal, shown, type) => {
  const assertion = parseInspectorJson(`{"proposed_value":${literal}}`);
  const view = render(<><AssertionFields value={assertion} /><JsonTree value={assertion} /></>);
  const fields = within(screen.getByLabelText("Recorded assertion fields"));
  expect(fields.getByText(shown)).toBeTruthy();
  expect(fields.getByText(type)).toBeTruthy();
  expect(within(view.container).getByText(`proposed_value: ${shown}`)).toBeTruthy();
});

it("compares exact equivalent representations and the published canonical value", async () => {
  const assertion = {
    local_ref: "width", origin: "EXTRACTED", attribute_key: "enclosure_width",
    raw_value: '20”(508.000mm)W', raw_unit: "”", proposed_value: "20.00", proposed_unit: "in",
    value_form: "EQUIVALENT_UNITS", alternate_representations: [{ value: "508.000", unit: "mm" }],
  };
  const recorded = { version: "phase-6r-attributes-v6", attributes: [assertion], raw_unmapped: [] };
  serve({
    ...detail, schema_version: recorded.version, rejections: [], validated: recorded,
    attempt: { ...attempt, received: 1, accepted: 1, quarantined: 0, validation: "validated" },
    candidates: [{
      ordinal: 0, local_ref: "width", mapping_status: "MAPPED", reason_code: null,
      // Deliberately distinct projection to prove the UI reads the persisted row.
      proposed_value: false, alternate_representations: [{ value: "509.000", unit: "mm" }],
      normalized_type: "NUMBER", normalized_value: "508", normalized_unit: "mm",
      evidence: [{ role: "VALUE", localization: "RESOLVED", reason_code: null }],
    }],
  }, JSON.stringify(recorded));
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByRole("button", { name: /attributes\[0\]/ }));
  fireEvent.click(screen.getByRole("button", { name: "Reveal original response" }));
  await screen.findByRole("button", { name: "Original response verified" });
  fireEvent.click(screen.getByRole("button", { name: "Compare" }));
  const [original, validated] = screen.getAllByLabelText("Recorded assertion fields");
  for (const fields of [original, validated]) {
    expect(within(fields).getByText('"20”(508.000mm)W"')).toBeTruthy();
    expect(within(fields).getByText('"20.00"')).toBeTruthy();
    expect(within(fields).getByText('"EQUIVALENT_UNITS"')).toBeTruthy();
    expect(within(fields).getByText('"508.000"')).toBeTruthy();
  }
  const persisted = within(screen.getByLabelText("Persisted candidate fields"));
  expect(persisted.getByText("false")).toBeTruthy();
  expect(persisted.getByText("(boolean)")).toBeTruthy();
  expect(persisted.getByText('"509.000"')).toBeTruthy();
  expect(screen.getByText("508 mm")).toBeTruthy();
  expect(screen.getByText("Evidence localization")).toBeTruthy();
});


it("shows performance nulls and large counts without an audit", async () => {
  serve({ ...detail, attempt: { ...attempt, retained: null, validation: null, status: "FAILED" },
    requested_reasoning_effort: "low",
    performance: { version: 1, provider_call_ms: 100_000, response_status: "timeout",
      request: { body_bytes: 2_100_000, native_readings: 123, ocr_readings: 3_022 },
      ocr_selected: true },
  });
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: /Siemens fixture/ }));
  fireEvent.click(await screen.findByText("Performance"));
  expect(screen.getByText("100,000 ms")).toBeTruthy();
  expect(screen.getByText("2,100,000")).toBeTruthy();
  expect(screen.getByText("3,022")).toBeTruthy();
  expect(screen.getByText("Pinned reasoning effort").parentElement?.textContent).toContain("low");
  expect(screen.getByText("Reasoning tokens").parentElement?.textContent).toContain("Unavailable");
});
