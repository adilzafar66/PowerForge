# Deterministic visual checks

These opt-in checks render the real Next.js routes against synthetic HTTP fixtures. Both server rendering and browser queries use the fixture API. No requests are forwarded to the application backend; unexpected API paths and writes fail the run. No application feature contains fixture logic.

Install development dependencies with `npm ci`, then install the matching browser with `npx playwright install chromium`. Alternatively set `VISUAL_BROWSER_PATH` to an installed Chrome executable. Use the same browser binary for both runs.

From `apps/web`, **before changing the application**:

```sh
npm run visual:capture
# Make the change, then:
npm run visual:compare
```

Capture refuses to replace an existing completed baseline. The comparison writes actual images, per-pixel diffs, a geometry manifest, a machine-readable result, and server logs under `.visual-artifacts/actual`. Baselines and cached Google Fonts responses are under `.visual-artifacts/baseline` and `.visual-artifacts/fonts`. These generated files stay outside Git. Keep the whole artifact directory when sharing evidence. A comparison never refreshes the font cache or updates a baseline.

The harness fixes fixture timestamps, server/browser display dates, locale, timezone, scale, light color scheme, viewports, browser version, and software rasterization settings. Scheduler clocks continue to run. Font bytes are captured once and reused. Screenshots wait for query completion and fonts, then settle transitions; screenshot capture finishes animations. Normal and reduced-motion views are exercised. The development indicator is hidden only in the test browser.

The workspace suite covers desktop/mobile project and revision screens, creation and editing sheets, discard/lifecycle dialogs, open select menus, empty/error/read-only states, Documents/Equipment/Topology/System Status, affected legacy drawers/dialogs, mobile navigation, keyboard focus, and layout boundaries. Dirty editor retention, Escape handling, focus restoration, and project-link keyboard navigation are asserted. Existing Vitest tests cover mutation semantics and failure paths. `.mjs` harness files are outside Vitest's test discovery.

The Phase 6F evidence fixture captures the Documents register and inspector, the 52-group Candidates browser, an OCR source highlight, and Run history with the raw table diagnostic at 1440, 1024, 768, and 390 px. Desktop and mobile checks also cover pagination, filter and search retention, independent historical run selection, a native candidate deep link, and a page-only citation without a rectangle. The fixture uses synthetic observations modeled on source policies exercised by the offline spatial evaluator.

```sh
VISUAL_PHASE6F=1 VISUAL_ARTIFACTS=.visual-artifacts/phase6f npm run visual:capture
```

The operations fixture captures all three wizard steps, Targeted extraction, operation progress, and the Run history re-extraction entry. Its fixture server accepts the workflow's source discovery, preview, and consent requests during this check.

```sh
VISUAL_PHASE6F_OPERATIONS=1 VISUAL_ARTIFACTS=.visual-artifacts/phase6f-m3-m4 npm run visual:capture
```

Both suites include `reference-*.png` viewport screenshots at the dimensions of the supplied design previews. Compare those screenshots visually with the corresponding prototype views. The separate `visual:compare` command checks changes against a baseline captured from the React routes.

Useful environment variables:

- `VISUAL_ARTIFACTS`: separate baseline/output root for a new task or rendering environment.
- `VISUAL_APP_ROOT`: an isolated frontend checkout to render (defaults to the current directory). This supports comparing an unchanged Git revision without restoring files over ongoing work. Its dependencies must already be installed.
- `VISUAL_APP_PORT` / `VISUAL_API_PORT`: defaults 4310 / 4311; avoid an existing development server.
- `VISUAL_QUICK=1`: 12 desktop workspace captures for iteration. This is **not** the full acceptance run.

Run comparisons serially for each application checkout: Next development and production builds share `.next`. A nonzero exit means a screenshot/geometry difference, page error, unsupported fixture request, or interaction failure; inspect `result.json` and the diff images rather than updating baselines to accept the result. Exact pixel checks intentionally report even minor rendering variation.
