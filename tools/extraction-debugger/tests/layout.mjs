// Synthetic browser smoke. Uses the existing PowerForge Playwright install.
import { createRequire } from "node:module";
import assert from "node:assert/strict";

const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const { chromium } = require("playwright");
const secret = process.env.EXTRACTION_DEBUGGER_SECRET;
assert(secret, "Set the running debugger secret in the test shell");
const browser = await chromium.launch({
  executablePath: process.env.DEBUGGER_BROWSER_PATH || undefined,
  headless: true,
});
const id = "10000000-0000-4000-8000-000000000001";
const accepted = { local_ref: "a2", attribute_key: "model", raw_value: "<svg onload=alert(1)> Ω" };
const rejected = { collection: "attributes", index: 0,
  issues: [{ category: "FIELD_CONSTRAINT", error_type: "string_too_short", path: ["attributes", 0, "raw_value"] }] };
const attempt = {
  attempt_id: id, run_id: id, document: "Synthetic breaker schedule", page: 1, attempt_number: 1,
  status: "COMPLETED", provider: "openai", model: "fixture", validation: "partial", received: 2,
  accepted: 1, quarantined: 1, published: 1, retained: true, expires_at: "2099-01-01T00:00:00Z",
  finished_at: "2026-01-01T00:00:00Z", duration_ms: 57000, output_sha256: "a".repeat(64),
};
try {
  for (const width of [1440, 720]) {
    const page = await browser.newPage({ viewport: { width, height: 900 } });
    await page.route("**/api/attempts**", async route => {
      if (!(await route.request().allHeaders()).cookie) return route.continue();
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/original")) return route.fulfill({
        body: JSON.stringify({ attributes: [{ local_ref: "a1", raw_value: "" }, accepted], raw_unmapped: [] }),
      });
      return route.fulfill({ json: path === "/api/attempts" ? { items: [attempt], next_cursor: null } : {
        attempt, rejections: [rejected], fatal: [], validated: { attributes: [accepted], raw_unmapped: [] },
        candidates: [{ ordinal: 0, local_ref: "a2", mapping_status: "UNMAPPED", reason_code: "unit_unverified", evidence: [] }],
      } });
    });
    await page.goto("http://127.0.0.1:3100");
    await page.getByLabel("Startup secret").fill(secret);
    await page.getByRole("button", { name: "Sign in" }).click();
    await page.getByRole("button", { name: /Synthetic breaker schedule/ }).click();
    await page.getByRole("button", { name: /attributes\[0\]/ }).click();
    await page.getByText("attributes[0].raw_value").waitFor();
    await page.getByRole("button", { name: "Reveal original response" }).click();
    await page.getByRole("button", { name: /attributes\[1\]/ }).click();
    await page.getByRole("button", { name: "Compare" }).click();
    await page.getByText("Validated assertion").waitFor();
    const layout = await page.evaluate(() => ({
      fits: document.documentElement.scrollWidth <= window.innerWidth,
      comparisonColumns: getComputedStyle(document.querySelector(".comparison")).gridTemplateColumns.split(" ").length,
      injected: !!document.querySelector("svg[onload]"),
    }));
    assert(layout.fits && !layout.injected);
    assert.equal(layout.comparisonColumns, width === 1440 ? 2 : 1);
    await page.getByRole("button", { name: "Sign out" }).click();
    await page.getByLabel("Startup secret").waitFor();
    await page.close();
    console.log(`Layout and reveal/compare workflow passed at ${width}px`);
  }
} finally {
  await browser.close();
}
