import assert from "node:assert/strict";
import { createServer } from "node:http";
import { spawn } from "node:child_process";
import { mkdir, readFile, writeFile, access } from "node:fs/promises";
import path from "node:path";
import { chromium } from "playwright";
import { PNG } from "pngjs";
import pixelmatch from "pixelmatch";
import { fixtureAsset, fixtureResponse } from "./fixtures.mjs";
import { resetOperationsFixture } from "./phase6f.mjs";

const mode = process.argv[2];
assert(["capture", "compare"].includes(mode), "Use capture or compare");
const root = path.resolve(process.env.VISUAL_ARTIFACTS || ".visual-artifacts");
const baseline = path.join(root, "baseline");
const output = path.join(root, mode === "capture" ? "baseline" : "actual");
if (mode === "capture") {
  try {
    await access(path.join(baseline, "manifest.json"));
    throw new Error(
      "Baseline already exists; choose a new VISUAL_ARTIFACTS directory.",
    );
  } catch (e) {
    if (e.code !== "ENOENT") throw e;
  }
}
await mkdir(output, { recursive: true });
let scenario = "normal";
const failures = [];
const apiPort = Number(process.env.VISUAL_API_PORT || 4311),
  appPort = Number(process.env.VISUAL_APP_PORT || 4310);
const api = `http://127.0.0.1:${apiPort}`,
  base = `http://127.0.0.1:${appPort}`;
const server = createServer(async (req, res) => {
  res.setHeader("Access-Control-Allow-Origin", base);
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
  if (req.method === "OPTIONS") {
    res.writeHead(204);
    res.end();
    return;
  }
  const url = new URL(req.url, api);
  const operationsPost = process.env.VISUAL_PHASE6F_OPERATIONS && req.method === "POST"
    && /^\/api\/projects\/p\/revisions\/r\/extraction\/operations(?:\/(?:sources|preview))?$/.test(url.pathname);
  if (req.method !== "GET" && !operationsPost) {
    failures.push(`Unexpected ${req.method} ${req.url}`);
    res.writeHead(500);
    res.end("{}");
    return;
  }
  const asset = fixtureAsset(url);
  if (asset) {
    res.setHeader("Content-Type", asset.type);
    res.end(asset.body);
    return;
  }
  let requestBody;
  if (operationsPost) {
    let data = "";
    for await (const chunk of req) data += chunk;
    requestBody = JSON.parse(data);
  }
  const body = fixtureResponse(url, scenario, requestBody);
  if (body === undefined) {
    failures.push(`Missing fixture ${req.url}`);
    res.writeHead(500);
    res.end("{}");
    return;
  }
  res.setHeader("Content-Type", "application/json");
  if (scenario === "error" && url.pathname === "/api/projects") {
    res.writeHead(503);
    res.end(JSON.stringify({ detail: "Fixture service unavailable" }));
    return;
  }
  if (body.__status) {
    res.writeHead(body.__status);
    res.end(JSON.stringify({ detail: body.detail }));
    return;
  }
  res.end(JSON.stringify(body));
});
await new Promise((resolve, reject) => {
  server.once("error", reject);
  server.listen(apiPort, "127.0.0.1", resolve);
});
const appRoot = path.resolve(process.env.VISUAL_APP_ROOT || ".");
const child = spawn(
  process.execPath,
  [
    path.resolve("node_modules/next/dist/bin/next"),
    "dev",
    "--hostname",
    "127.0.0.1",
    "--port",
    String(appPort),
  ],
  {
    cwd: appRoot,
    env: {
      ...process.env,
      NEXT_PUBLIC_API_URL: api,
      API_INTERNAL_URL: api,
      TZ: "UTC",
      NODE_OPTIONS: `${process.env.NODE_OPTIONS || ""} --require=${path.resolve("visual/fixed-date.cjs")}`,
      NEXT_TELEMETRY_DISABLED: "1",
    },
    stdio: ["ignore", "pipe", "pipe"],
  },
);
let logs = "";
child.stdout.on("data", (x) => (logs += x));
child.stderr.on("data", (x) => (logs += x));
let browser;
try {
  for (let i = 0; i < 120; i++) {
    if (child.exitCode !== null) throw Error(logs);
    try {
      if ((await fetch(base)).ok) break;
    } catch {}
    await new Promise((r) => setTimeout(r, 500));
    if (i === 119) throw Error("App did not start\n" + logs);
  }
  browser = await chromium.launch({
    ...(process.env.VISUAL_BROWSER_PATH
      ? { executablePath: process.env.VISUAL_BROWSER_PATH }
      : {}),
    args: ["--disable-gpu", "--force-color-profile=srgb", "--disable-lcd-text"],
  });
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1000 },
    deviceScaleFactor: 1,
    locale: "en-US",
    timezoneId: "UTC",
    colorScheme: "light",
  });
  // Cache the exact font responses once. Comparisons must use those bytes.
  await context.route(
    /https:\/\/(fonts.googleapis.com|fonts.gstatic.com)\//,
    async (route) => {
      const key = Buffer.from(route.request().url()).toString("base64url");
      const file = path.join(root, "fonts", key + ".json");
      let saved;
      try {
        saved = JSON.parse(await readFile(file, "utf8"));
      } catch (e) {
        if (mode !== "capture" || e.code !== "ENOENT") throw e;
        const response = await route.fetch();
        assert(response.ok(), "Font request failed");
        saved = {
          status: response.status(),
          headers: response.headers(),
          body: (await response.body()).toString("base64"),
        };
        await mkdir(path.dirname(file), { recursive: true });
        await writeFile(file, JSON.stringify(saved));
      }
      await route.fulfill({
        ...saved,
        body: Buffer.from(saved.body, "base64"),
      });
    },
  );
  const page = await context.newPage();
  await page.clock.setFixedTime(new Date("2026-01-20T12:00:00Z"));
  page.on("pageerror", (e) => failures.push(e.message));
  const manifest = {
    browser: browser.version(),
    viewport: { desktop: [1440, 1000], mobile: [390, 844] },
    locale: "en-US",
    timezone: "UTC",
    captures: {},
  };
  const old =
    mode === "compare"
      ? JSON.parse(await readFile(path.join(baseline, "manifest.json"), "utf8"))
      : null;
  if (old)
    assert.equal(manifest.browser, old.browser, "Browser version changed");
  async function settle() {
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(350);
    await page.addStyleTag({
      content: "nextjs-portal{display:none!important}",
    });
  }
  async function shot(name, fullPage = true) {
    await settle();
    await page.screenshot({
      path: path.join(output, name + ".png"),
      fullPage,
      animations: "disabled",
      caret: "hide",
    });
    const geometry = await page
      .locator(
        'h1, main, table, [role="dialog"], input:not([type="hidden"]), textarea, [role="combobox"]',
      )
      .evaluateAll((es) =>
        es
          .filter((e) => e.getBoundingClientRect().width)
          .map((e) => {
            const r = e.getBoundingClientRect(),
              s = getComputedStyle(e);
            return {
              tag: e.tagName,
              x: r.x,
              y: r.y,
              w: r.width,
              h: r.height,
              font: s.font,
              lineHeight: s.lineHeight,
              color: s.color,
              background: s.backgroundColor,
            };
          }),
      );
    manifest.captures[name] = geometry;
    if (old && !old.captures[name]) {
      failures.push(`${name}: no baseline capture`);
    } else if (old) {
      const a = PNG.sync.read(
          await readFile(path.join(baseline, name + ".png")),
        ),
        b = PNG.sync.read(await readFile(path.join(output, name + ".png")));
      if (a.width !== b.width || a.height !== b.height) {
        failures.push(`${name}: image dimensions changed`);
        return;
      }
      const diff = new PNG({ width: a.width, height: a.height });
      const n = pixelmatch(a.data, b.data, diff.data, a.width, a.height, {
        threshold: 0,
        includeAA: true,
      });
      if (n) {
        await writeFile(
          path.join(output, name + ".diff.png"),
          PNG.sync.write(diff),
        );
        failures.push(`${name}: ${n} changed pixels`);
      }
      if (JSON.stringify(geometry) !== JSON.stringify(old.captures[name]))
        failures.push(`${name}: geometry/computed styles changed`);
    }
    console.log(name);
  }
  async function referenceSizeShot(name, width, height) {
    const original = page.viewportSize();
    await page.setViewportSize({ width, height });
    await shot(`reference-${name}`, false);
    await page.setViewportSize(original);
  }
  const p = "/projects/p",
    r = p + "/revisions/r",
    model = r + "?workspace=model",
    edit = (tab) =>
      `${model}&equipment=e1&equipmentMode=edit&equipmentTab=${tab}`;
  async function go(url) {
    await page.goto(base + url);
    await page.waitForLoadState("networkidle");
    await settle();
  }
  async function equipmentStates(prefix) {
    await go(model + "&equipment=e1");
    await page
      .getByRole("complementary", { name: "Equipment quick details" })
      .getByText("LINE ↔ Main bus")
      .first()
      .waitFor();
    await shot(`${prefix}-equipment-quick`);
    for (const tab of ["general", "attributes", "terminals"]) {
      await go(edit(tab));
      await page
        .getByRole("tab", { name: tab[0].toUpperCase() + tab.slice(1) })
        .waitFor();
      await shot(`${prefix}-equipment-edit-${tab}`);
    }
  }
  if (process.env.VISUAL_PHASE6G) {
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await go(r + "/documents/doc?mode=evidence&evidenceTab=history");
      const engineering = page.getByRole("region", { name: "Engineering history" });
      await engineering.getByRole("button", { name: /Run / }).click();
      await engineering.getByText("Attempts and source bindings", { exact: true }).click();
      await engineering.getByText("0 candidates · 0 tables published", { exact: true }).click();
      await engineering.getByText("Crosses source lines · 1", { exact: true }).waitFor();
      await engineering.getByText("Returned · Attributes 1", { exact: true }).waitFor();
      await shot(`phase6g-engineering-loss-${width}`);

      const tables = page.getByRole("region", { name: "Tables history" });
      await tables.getByRole("button", { name: /Run .*Partial/ }).click();
      await tables.getByText("Attempts and source bindings", { exact: true }).click();
      await tables.getByText("Parse · Missing field", { exact: true }).click();
      await tables.getByText("Missing field · tables.0.cells.0.raw_text", { exact: true }).waitFor();
      await shot(`phase6g-table-parse-${width}`);
    }
  } else if (process.env.VISUAL_PHASE6F_OPERATIONS) {
    for (const width of [1440, 1024, 768, 390]) {
      resetOperationsFixture();
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await go(r);
      await page.getByRole("checkbox", { name: "Select eligible visible documents" }).check();
      await page.getByRole("button", { name: "Start extraction", exact: true }).click();
      const wizard = page.getByRole("dialog", { name: "Start extraction" });
      await wizard.getByRole("textbox", { name: "Pages for Substation_SLD.pdf" }).waitFor();
      await shot(`phase6f-source-${width}`);
      if (width === 1440) await referenceSizeShot("source", 1440, 1158);
      await wizard.getByRole("button", { name: "Continue to enrichment" }).click();
      await wizard.getByText("Reuse existing results", { exact: true }).waitFor();
      await wizard.getByText("Will prepare automatically", { exact: true }).waitFor();
      await shot(`phase6f-enrichment-${width}`);
      if (width === 1440) await referenceSizeShot("enrichment", 1440, 1158);
      await wizard.getByRole("button", { name: "Continue to extraction" }).click();
      await wizard.getByText("4 extraction runs requested", { exact: true }).waitFor();
      await shot(`phase6f-comprehensive-${width}`);
      if (width === 1440) await referenceSizeShot("comprehensive", 1440, 950);
      await wizard.getByText("Advanced extraction settings", { exact: true }).click();
      await wizard.getByRole("checkbox", { name: "Extract from engineering text" }).uncheck();
      await wizard.getByText("2 extraction runs requested", { exact: true }).waitFor();
      await shot(`phase6f-targeted-${width}`);
      if (width === 1440) await referenceSizeShot("targeted", 1440, 950);
      await wizard.getByRole("checkbox", { name: /I authorize sending/ }).check();
      await wizard.getByRole("button", { name: "Start extraction", exact: true }).click();
      await page.getByRole("link", { name: "View operation" }).click();
      await page.getByText(/Operation ID ·/).waitFor();
      assert(await page.getByRole("heading", { name: "Extraction operation" }).evaluate(
        (heading) => heading.getBoundingClientRect().top < window.innerHeight
      ));
      await shot(`phase6f-operation-${width}`);
    }
    resetOperationsFixture();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await go(r + "/documents/doc?mode=evidence&evidenceTab=history");
    await page.getByRole("region", { name: "Engineering history" })
      .getByRole("button", { name: /Run / }).click();
    await page.getByRole("button", { name: "Re-extract", exact: true }).click();
    const reextract = page.getByRole("dialog", { name: "Re-extract", exact: true });
    assert.equal(await reextract.getByRole("textbox", { name: "Pages for Substation_SLD.pdf" }).inputValue(), "1");
    await shot("phase6f-reextract-1440");
  } else if (process.env.VISUAL_PHASE6F) {
    const viewer = r + "/documents/doc?mode=evidence";
    for (const width of [1440, 1024, 768, 390]) {
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await go(r);
      await page.getByRole("columnheader", { name: "AI Extraction" }).waitFor();
      if (width === 1440) await referenceSizeShot("register", 1440, 1081);
      await page.getByRole("checkbox", { name: "Select eligible visible documents" }).check();
      await shot(`phase6f-register-${width}`);
      await go(r + "?document=doc");
      await page.getByRole("button", { name: "View results" }).waitFor();
      await shot(`phase6f-inspector-${width}`);
      if (width === 1440) await referenceSizeShot("inspector", 1580, 1091);
      await go(viewer);
      await page.getByText("52 groups", { exact: true }).waitFor();
      assert.deepEqual(await page.getByRole("tablist", { name: "Extraction evidence sections" })
        .getByRole("tab").allTextContents(), ["Candidates", "Run history"]);
      await shot(`phase6f-groups-${width}`);
      if (width === 1440) await referenceSizeShot("groups", 1512, 1000);
      await page.getByRole("button", { name: /TX-1.*Tables/ }).click();
      await page.getByRole("button", { name: /Rated apparent power/ }).click();
      await page.getByRole("img", { name: "Grounded source region" }).waitFor();
      await shot(`phase6f-candidate-${width}`);
      if (width === 1440) await referenceSizeShot("candidate", 1512, 1000);
      await page.getByRole("button", { name: "Back to source groups" }).click();
      await page.getByRole("tab", { name: "Run history" }).click();
      const tableHistory = page.getByRole("region", { name: "Tables history" });
      if (width === 1440) await referenceSizeShot("history", 1512, 1000);
      await tableHistory.getByRole("button", { name: /Run .*Completed/ }).click();
      await page.getByText("Inspect raw table output (technical)", { exact: true }).click();
      await page.getByRole("table").getByText("750 kVA", { exact: true }).waitFor();
      await shot(`phase6f-history-${width}`);
      if (width === 1440) await referenceSizeShot("raw-table", 1512, 1000);

      if (width === 1440 || width === 390) {
        await tableHistory.getByRole("button", { name: /Run .*Partial/ }).click();
        await tableHistory.getByRole("button", { name: /Run .*Partial/, expanded: true }).waitFor();
        await tableHistory.getByRole("button", { name: "Browse candidates" }).click();
        await page.getByText("1 group", { exact: true }).waitFor();
        await page.getByRole("tab", { name: "Run history" }).click();
        const engineeringHistory = page.getByRole("region", { name: "Engineering history" });
        await engineeringHistory.getByRole("button", { name: /Run / }).click();
        await engineeringHistory.getByRole("button", { name: "Browse candidates" }).click();
        await page.getByText("27 groups", { exact: true }).waitFor();
        const selectedRuns = new URL(page.url()).searchParams;
        assert(selectedRuns.get("engineeringRun")?.endsWith("000001"));
        assert(selectedRuns.get("tablesRun")?.endsWith("000002"));
        await page.getByRole("button", { name: "View latest results" }).click();
        await page.getByText("52 groups", { exact: true }).waitFor();

        const pages = page.getByRole("navigation", { name: "Result pages" });
        await pages.getByRole("button", { name: "Next" }).click();
        await pages.getByText("26–50 of 52").waitFor();
        await pages.getByRole("button", { name: "Next" }).click();
        await pages.getByText("51–52 of 52").waitFor();
        await page.getByRole("button", { name: /TX-052.*Engineering/ }).waitFor();

        await page.getByRole("button", { name: "Current page", exact: true }).click();
        await page.getByText("26 groups", { exact: true }).waitFor();
        await page.getByRole("button", { name: "All pages", exact: true }).click();
        await page.getByText("52 groups", { exact: true }).waitFor();
        const search = page.getByRole("searchbox", { name: "Search source groups" });
        await search.fill("TX-002");
        await page.getByText("1 group", { exact: true }).waitFor();
        if (width === 1440) await referenceSizeShot("group-search", 1512, 1000);
        await page.getByRole("button", { name: /TX-002.*Engineering/ }).click();
        await page.getByRole("button", { name: /Rated apparent power/ }).click();
        await page.getByText("Native PDF", { exact: true }).waitFor();
        const region = page.getByRole("img", { name: "Grounded source region" });
        await region.waitFor();
        const sourcePage = await page.getByRole("img", { name: "Pinned source page 1" }).boundingBox();
        const highlight = await region.boundingBox();
        assert(Math.abs(highlight.x - sourcePage.x - 0.57 * sourcePage.width) < 1);
        assert(Math.abs(highlight.y - sourcePage.y - 0.371 * sourcePage.height) < 1);
        await page.getByText("Original reading", { exact: true }).waitFor();
        const deepLink = page.url();
        await page.reload();
        assert.equal(page.url(), deepLink);
        await region.waitFor();
        await shot(`phase6f-native-${width}`);
        await page.getByRole("button", { name: "Back to source groups" }).click();
        assert.equal(await search.inputValue(), "TX-002");

        await search.fill("");
        await page.getByText("52 groups", { exact: true }).waitFor();
        const mapping = page.getByRole("combobox", { name: "Mapping status" });
        await mapping.click();
        await page.getByRole("option", { name: "Unmapped", exact: true }).click();
        await page.getByRole("button", { name: /Ungrouped observations.*Tables/ }).click();
        await page.getByRole("button", { name: /Observed attribute.*Unmapped/ }).click();
        await page.getByText("Page-level citation. No grounded highlight is available.").waitFor();
        await page.getByRole("img", { name: "Pinned source page 2" }).waitFor();
        assert.equal(await region.count(), 0);
        await shot(`phase6f-page-only-${width}`);
        await page.getByRole("button", { name: "Back to source groups" }).click();
        await mapping.click();
        await page.getByRole("option", { name: "Invalid", exact: true }).click();
        await page.getByRole("button", { name: /TX-004.*Engineering/ }).click();
        await page.getByRole("button", { name: /Observed attribute.*Invalid/ }).click();
        await page.getByText("Unrecognized voltage unit", { exact: true }).waitFor();
      }
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await go(p + "/revisions/old/documents/doc?mode=evidence&evidenceTab=history");
    await page.getByRole("region", { name: "Engineering history" })
      .getByRole("button", { name: /Run / }).click();
    await page.getByRole("button", { name: "Browse candidates" }).waitFor();
    assert.equal(await page.getByRole("button", { name: "Re-extract", exact: true }).count(), 0);
  } else {
  for (const width of process.env.VISUAL_QUICK ? [1440] : [1440, 390]) {
    const prefix = width === 1440 ? "desktop" : "mobile";
    await page.setViewportSize({ width, height: width === 1440 ? 1000 : 844 });
    for (const [name, url] of [
      ["projects", "/"],
      ["create", "/projects/new"],
      ["project", p],
      ["revisions", p + "/revisions"],
      ["revision", r + "?view=overview"],
    ]) {
      await go(url);
      await shot(`${prefix}-${name}`);
      if (name === "project" || name === "revision") {
        await page
          .getByRole("button", {
            name:
              name === "project" ? "Edit details" : "Edit revision information",
            exact: true,
          })
          .click();
        await shot(`${prefix}-${name}-editor`);
        const field = page.getByRole("textbox", {
          name: name === "project" ? "Project Name" : "Description",
          exact: true,
        });
        await field.fill("Unsaved fixture draft");
        await page.keyboard.press("Escape");
        await shot(`${prefix}-${name}-discard`);
        await page
          .getByRole("button", { name: "Cancel", exact: true })
          .last()
          .click();
        assert.equal(await field.inputValue(), "Unsaved fixture draft");
        await page.keyboard.press("Escape");
        await page
          .getByRole("button", { name: "Discard changes", exact: true })
          .click();
      }
      if (name === "revisions") {
        await page.getByRole("button", { name: /^Draft / }).click();
        await shot(`${prefix}-revision-filter`);
        await page
          .getByRole("button", { name: "New revision", exact: true })
          .click();
        await shot(`${prefix}-revision-create`);
        await page
          .getByRole("combobox", { name: "Based on", exact: true })
          .click();
        await shot(`${prefix}-revision-select`);
        await page.keyboard.press("Escape");
        await page.keyboard.press("Escape");
      }
    }
    if (!process.env.VISUAL_QUICK) {
      await go(p);
      await page.getByRole("button", { name: "Pause", exact: true }).click();
      await shot(`${prefix}-lifecycle-dialog`);
      await page.keyboard.press("Escape");
      if (width === 390) {
        await page.getByRole("button", { name: "Open navigation" }).click();
        await shot("mobile-navigation");
        await page.keyboard.press("Escape");
      }
      for (const [name, url] of [
        ["documents", r],
        ["equipment", r + "?workspace=model"],
        ["topology", r + "?workspace=model&view=topology"],
        ["status", "/status"],
      ]) {
        await go(url);
        await shot(`${prefix}-${name}`);
      }
      await equipmentStates(prefix);
    }
  }
  if (!process.env.VISUAL_QUICK) {
    await page.setViewportSize({ width: 1024, height: 1000 });
    await go(model);
    await shot("tablet-equipment");
    await equipmentStates("tablet");
    await page.setViewportSize({ width: 1440, height: 1000 });
    await go(r + "?document=doc");
    await page
      .getByRole("dialog")
      .filter({ has: page.getByRole("button", { name: "Close details" }) })
      .waitFor();
    await shot("document-drawer");
    await page.getByRole("button", { name: "Remove", exact: true }).click();
    await shot("document-remove-dialog");
    await page.keyboard.press("Escape");
    for (const width of [1440, 1024, 390]) {
      const prefix = `documents-${width}`;
      await page.setViewportSize({ width, height: width === 390 ? 844 : 1000 });
      await go(r);
      await shot(`${prefix}-register`);
      await page.getByRole("button", { name: "Filters", exact: true }).click();
      await shot(`${prefix}-filters`);
      await page.keyboard.press("Escape");
      const addMenu = () =>
        page
          .getByRole("button", { name: "Add documents", exact: true })
          .first()
          .click();
      await addMenu();
      await shot(`${prefix}-add-menu`);
      await page.getByRole("menuitem", { name: "Upload files" }).click();
      await shot(`${prefix}-upload`);
      await page.keyboard.press("Escape");
      await addMenu();
      await page
        .getByRole("menuitem", { name: "Add from another revision" })
        .click();
      await page.getByText("Panel_Schedules_Level2.pdf").last().waitFor();
      await shot(`${prefix}-reuse`);
      await page.keyboard.press("Escape");
      await go(r + "?document=doc-panels");
      await page
        .getByRole("dialog")
        .filter({ has: page.getByRole("button", { name: "Close details" }) })
        .waitFor();
      await shot(`${prefix}-inspector`);
      const viewer = r + "/documents/doc";
      await go(viewer);
      await page.getByRole("img", { name: "Page 1" }).waitFor();
      await shot(`${prefix}-viewer`);
      await go(viewer + "?mode=evidence");
      await page.getByRole("img", { name: "Page 1" }).waitFor();
      await shot(`${prefix}-evidence`);
      if (width !== 390) {
        await go(viewer + "?page=2");
        await page
          .getByRole("button", { name: "Page thumbnails", exact: true })
          .click();
        await page.getByRole("img", { name: "Page 2" }).waitFor();
        await shot(`${prefix}-thumbs-collapsed`);
      }
      await go(r + "/documents/doc-tx");
      await shot(`${prefix}-viewer-processing`);
      scenario = "readonly";
      await go(r);
      await shot(`${prefix}-readonly`);
      scenario = "normal";
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await go(r + "?document=doc-panels");
    await page
      .getByRole("textbox", { name: "Description", exact: true })
      .fill("Unsaved fixture draft");
    await page.getByRole("button", { name: "Close details", exact: true }).click();
    await page
      .getByRole("dialog", { name: "Discard unsaved changes?" })
      .waitFor();
    await shot("documents-unsaved-dialog");
    await page
      .getByRole("button", { name: "Keep editing", exact: true })
      .click();
    await go(edit("general"));
    await page
      .getByRole("textbox", { name: "Equipment tag", exact: true })
      .fill("SWGR-1A");
    await page
      .getByRole("button", { name: "Back to Equipment", exact: true })
      .click();
    await page.getByRole("dialog", { name: "Unsaved changes" }).waitFor();
    await shot("equipment-unsaved-dialog");
    await page
      .getByRole("button", { name: "Discard changes", exact: true })
      .click();
    await page.waitForURL((u) => !u.search.includes("equipmentMode"));
    await go(edit("general"));
    await page
      .getByRole("button", { name: "Remove equipment", exact: true })
      .click();
    await shot("equipment-remove-dialog");
    await page.keyboard.press("Escape");
    await go(r + "?workspace=model&view=topology");
    await page
      .getByRole("button", { name: "Add Electrical Node", exact: true })
      .click();
    await shot("topology-editor");
    await page.keyboard.press("Escape");
    for (const width of [1440, 1024, 390]) {
      const prefix = `topology-${width}`;
      await page.setViewportSize({
        width,
        height: width === 390 ? 844 : 1000,
      });
      const topology = r + "?workspace=model&view=topology";
      await go(topology);
      await page.getByRole("table", { name: "Nodes" }).waitFor();
      await shot(`${prefix}-overview`);
      await go(`${topology}&node=t1`);
      await page
        .getByRole("dialog")
        .filter({ has: page.getByRole("button", { name: "Close inspector" }) })
        .waitFor();
      await shot(`${prefix}-node-inspector`);
      await go(`${topology}&connection=c1`);
      await page.getByRole("button", { name: "Edit connection" }).waitFor();
      await shot(`${prefix}-connection-inspector`);
      await page.getByRole("button", { name: "Edit connection" }).click();
      await page.getByRole("dialog", { name: "Edit Connection" }).waitFor();
      await shot(`${prefix}-edit-connection`);
      await page.keyboard.press("Escape");
      await go(topology);
      await page.getByRole("button", { name: "Add Electrical Node" }).click();
      await page.getByRole("dialog", { name: "Add Electrical Node" }).waitFor();
      await shot(`${prefix}-add-node`);
      await page.keyboard.press("Escape");
      await go(`${topology}&node=n1`);
      await page.getByRole("button", { name: "Remove" }).click();
      await page.getByRole("dialog", { name: "Remove node?" }).waitFor();
      await shot(`${prefix}-remove-confirm`);
      await page.keyboard.press("Escape");
      scenario = "readonly";
      await go(topology);
      await page.getByRole("table", { name: "Nodes" }).waitFor();
      await shot(`${prefix}-readonly`);
      scenario = "normal";
      await go(topology);
      await page.getByLabel("Search topology").fill("zzzzz");
      await page.getByText("No nodes match this filter.").waitFor();
      await shot(`${prefix}-empty`);
    }
    await page.setViewportSize({ width: 1440, height: 1000 });
    await go("/");
    const rowLink = page.locator("tbody a").first();
    await rowLink.focus();
    await shot("project-link-focus");
    await page.keyboard.press("Enter");
    await page.waitForURL(base + p);
    await go(p);
    await page
      .getByRole("button", { name: "Edit details", exact: true })
      .click();
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => document.activeElement?.textContent?.trim() === "Edit details",
    );
    assert.equal(
      await page
        .getByRole("button", { name: "Edit details", exact: true })
        .evaluate((e) => e === document.activeElement),
      true,
      "Restore editor trigger focus",
    );
    await go("/projects/new");
    await page.locator("input[type=checkbox]").first().uncheck();
    await shot("create-checkbox-unchecked");
    for (const state of ["empty", "error", "readonly"]) {
      scenario = state;
      await go(state === "readonly" ? p : "/");
      await shot(state);
    }
    scenario = "readonly";
    await go(edit("general"));
    await shot("equipment-readonly");
    scenario = "normal";
    await go(p);
    await page.emulateMedia({ reducedMotion: "reduce" });
    await shot("reduced-motion");
    await page.emulateMedia({ reducedMotion: "no-preference" });
    for (const width of [529, 530, 767, 768, 789, 790, 1119, 1120]) {
      await page.setViewportSize({ width, height: 1000 });
      await go(p);
      await shot(`breakpoint-${width}`);
    }
  }
  }
  await writeFile(
    path.join(output, "manifest.json"),
    JSON.stringify(manifest, null, 2),
  );
  await writeFile(
    path.join(output, "result.json"),
    JSON.stringify(
      { captures: Object.keys(manifest.captures).length, failures },
      null,
      2,
    ),
  );
  assert.deepEqual(failures, []);
  console.log(
    `${mode}: ${Object.keys(manifest.captures).length} captures passed`,
  );
} finally {
  if (browser) await browser.close();
  child.kill("SIGTERM");
  server.closeAllConnections();
  server.close();
  await writeFile(path.join(output, "server.log"), logs);
}
