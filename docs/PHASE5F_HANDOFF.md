# Phase 5F handoff — Basic Engineering Model workspace UI

Implemented on 2026-10-25. Phase 5A–5F are implemented. Phase 5G has not started, and Phase 5 as a whole remains incomplete.

## Baseline and boundaries

- Working branch: `codex/phase-5f-model-workspace`.
- Baseline: accepted `main` at `aed2e18fce9efcdadab04ca1d087c26d81148d64` (`Reject empty model PATCHes and classify consistency errors safely`). This includes the accepted Phase 5E fixes.
- Instructions: [Phase 5F prompt](prompts/phase-5f-codex.md), [Phase 5 specification](specs/phase-5-engineering-model.md), and [ADR-007](../decisions/ADR-007-canonical-engineering-model-persistence.md). The user explicitly confirmed finishing **Phase 5F only**.
- The pre-existing, untracked Phase 5F prompt was preserved without edits. Historical Phase 5A–5E handoffs were not rewritten.
- No backend Python, API contract, database migration, worker, registry-v1, or dependency changes. Alembic head remains `0009_topology_persistence`.

## Changed frontend files and architecture

Paths below are relative to `apps/web/src/`.

| File | Responsibility |
| --- | --- |
| `app/projects/[projectId]/revisions/[revisionId]/page.tsx` | Mounts the combined workspace below the existing shared revision banner |
| `components/read-only-banner.tsx` | Clarifies that engineering-model data remains viewable |
| `components/revision-workspace.tsx` | Documents/Engineering Model switch and workspace query parameters |
| `components/engineering-model-workspace.tsx` | Registry load, Equipment/Topology views, local writability and refresh/error handling |
| `components/model-shared.tsx` | Local context, cancellable query state, select/Sheet/loading helpers, lifecycle controls and confirmation warnings |
| `components/equipment-workspace.tsx` | Equipment search, filters, list, create Sheet and selected equipment URL |
| `components/equipment-detail-drawer.tsx` | Scoped detail GET and General/Attributes/Terminals tabs |
| `components/equipment-general-panel.tsx` | Registry-driven type selection, create and changed-field general PATCH |
| `components/equipment-attributes-panel.tsx` | Generic registry-driven attribute rows and independent saves |
| `components/equipment-terminals-panel.tsx` | Selected equipment's terminals and owner-aware lifecycle controls |
| `components/model-node-editor.tsx` | Shared explicit terminal/electrical-node form |
| `components/topology-workspace.tsx` | Node/connection lists, human endpoint labels and lifecycle actions |
| `components/connection-editor-sheet.tsx` | Connection create/edit, active endpoints and decimal-safe voltage |
| `lib/engineering-model.ts` | API types, typed requests, display labels and nullable-text patch comparison |
| `lib/engineering-model.test.ts` | API request/response and PATCH contract tests |
| `components/model-test-fixtures.ts` | Representative synthetic registry/model fixtures, not a copy of registry-v1 |
| `components/model-editors.test.tsx` | Equipment, attribute, terminal, node and connection form tests |
| `components/revision-workspace.test.tsx` | Workspace navigation, filtering, deep links, lifecycle and stale-state tests |

Current-facing `ENGINEERING_MODEL.md`, `TOPOLOGY.md`, `ARCHITECTURE.md`, `PROJECT_STATUS.md`, and `ROADMAP.md` now describe 5F as implemented and 5G as next.

The existing UI primitives supply Buttons, Fields, Inputs, Cards, Chips, SegmentedControls, Sheets, and confirmation dialogs. Local component state stores drafts, filters and open forms; a model-local context shares registry metadata, writability and a refresh version. No global store or data-fetching framework was added. Superseded requests cannot replace newer query results.

## Workspace URLs and registry

Documents remains the default, including existing `?document=<id>` links. Switching to Engineering Model sets `workspace=model` and removes `document`. Switching back removes `workspace` and `equipment`. Other query parameters survive. Equipment opening/closing adds/removes only `equipment` within the model workspace.

`?workspace=model&equipment=<id>` loads the scoped equipment detail independently of the current list filters. A missing or scoped-out ID clears the selection and displays the API's safe error. The detail drawer is not inferred from a possibly filtered list.

Registry metadata is requested on first model use and retained in the mounted workspace across the normal Documents/Engineering Model switch. A fresh mount loads it again. Registry failure has an explicit Retry and does not prevent using Documents. Types, display order, attribute controls, enum choices, badges and unit choices derive from the API metadata. Production code does not copy the canonical registry into TypeScript.

## API types and equipment workflows

`lib/engineering-model.ts` defines registry metadata, canonical Equipment/EquipmentAttribute/ModelNode/ModelConnection response types, lifecycle and manual-state vocabulary, and explicit manual request types. Requests use the existing `request`/`apiErrorOf` boundary. List wrappers expose their `items`; the module rejects an empty PATCH before making a request. No request body sets origin, verification, confidence, actors or inheritance.

The equipment list sends a 300 ms debounced server `search`, the registry-provided equipment type and ACTIVE/REMOVED/ALL lifecycle filters. ACTIVE is the default. The list has loading, empty and retry states, keyboard row opening, and responsive layout. It does not fetch attributes for every list row.

Add Equipment accepts a registry type and optional tag/name/description. Duplicate or missing tags remain valid. Success closes the create form, refreshes the list and opens the created equipment. Details use the existing Sheet pattern with General, Attributes and Terminals tabs. Removed equipment stays readable and exposes restoration in writable revisions.

General edits compare the loaded row with the draft. Omitted fields remain unchanged; clearing nullable text sends explicit null. Untouched null/blank fields do not create changes. Save is disabled for an unchanged draft, with an additional no-empty-PATCH guard at the API helper. Type-change conflicts surface the API detail and preserve the draft while requesting a canonical refresh. A successful type change replaces the equipment response and reloads its attribute definitions/materialized rows.

## Attributes, precision and units

Rows follow registry order. Required and Critical flags display independently, with Conditional shown from requirement group/condition metadata. Notes and condition descriptions remain visible. The frontend does not execute a new requirement engine or persist findings.

| Value type | PRESENT editor and submission |
| --- | --- |
| NUMBER | Text input with decimal input mode; trimmed string sent unchanged |
| INTEGER | Text input with numeric input mode; trimmed string sent without `Number`/`parseFloat`; server validates integrality |
| BOOLEAN | Explicit True/False select; submits actual JSON `true`/`false` |
| ENUM | Select populated from registry `allowed_values` |
| TEXT | Text input submitted without numeric interpretation |

The regression value `0.1234567890123456789012345678901234` reaches the request body unchanged. Connection voltage follows the same string strategy. Integer input `9007199254740993` is also tested as an unchanged string at submission; this does not claim arbitrary-precision integer responses (see limitations below).

NUMBER/INTEGER unit choices come from each attribute's `supported_input_units`. Existing canonical values load with their persisted unit. Changing the input unit does not numerically convert the draft; the UI explains that conversion occurs on save. Successful saves replace the local row/draft with the server's canonical response. Connection units derive from the registry Voltage unit family and its default unit, without a hardcoded V/kV/MV list.

Manual targets are PRESENT, UNKNOWN, MISSING and NOT_APPLICABLE. Existing NOT_EXTRACTED/CONFLICTING state remains visible as a disabled current option, without becoming a selectable manual target. Non-PRESENT saves omit value and unit, so stale draft values cannot accompany state-only changes. Required fields may remain incomplete.

Each attribute has an explicit independent Save, dirty/busy state, row-local error and success feedback. A successful row save does not reset other attribute drafts. A 422 retains the edited draft; stale 404/409 requests canonical refresh. Origin, verification and confidence are informational only.

## Terminals and topology

The Terminals tab requests nodes with lifecycle ALL and filters by EQUIPMENT_TERMINAL plus the selected equipment ID. Terminals are explicitly added, edited, removed and restored; none are generated automatically. Only active equipment permits terminal mutations. A removed owner must be restored first. Terminal PATCH permits the key and nullable label, never ownership/kind.

Topology loads nodes, connections and equipment summaries with lifecycle ALL, then offers local ACTIVE/REMOVED/ALL views. The equipment lookup is bulk, avoiding one request per terminal label. Global node creation/edit/removal/restoration applies to ELECTRICAL_NODE only. Terminals remain visible but are managed through Equipment.

Human terminal labels combine owner tag/name/type with terminal key and optional label. Electrical nodes use their label or a short-ID fallback. Duplicate labels append a short node ID for disambiguation; raw UUIDs are not the primary selector text.

Connections remain separate rows even when endpoints match. Forms select distinct active endpoints and allow kind, direction, nullable phase configuration and optional voltage. Blank create voltage omits both value and unit. Editing voltage sends the pair when needed; clearing sends explicit null. Save is disabled for unchanged forms, and no empty PATCH is sent. The canonical list refresh displays normalized voltage/unit after success.

Equipment removal confirms the terminal/incident-connection cascade. Terminal or electrical-node removal confirms incident-connection removal. Warnings state that restoration does not automatically restore connections. Equipment restoration restores terminals according to the accepted service semantics; no additional connection-restoration loop exists in the UI. A removed connection can be restored only when both endpoints are active; otherwise the UI explains that endpoints must be restored first. Node lifecycle changes refresh both nodes and connections.

## Read-only and error handling

The existing server-derived revision writability and shared banner govern both workspaces. Superseded/cancelled/archived revisions remain viewable with model mutation actions unavailable and editor fields disabled. Removed equipment is readable but cannot have its general fields, attributes or terminals edited.

Recognized read-only API error codes immediately lock local model mutations, call `router.refresh()` and refresh canonical model state. Scoped missing/lifecycle conflicts refresh the model lists/detail. Ordinary 422 validation errors remain near the affected form with its draft intact. API error formatting, including sanitized consistency failures, remains in the accepted request/backend boundary.

## Validation

Run from `apps/web` unless stated otherwise:

| Command/check | Result |
| --- | --- |
| `npm run lint` | Passed; no warnings or errors |
| `npm test` | 243 passed across 15 files; no failures (rerun 2026-10-26 after the BOOLEAN fix) |
| `npx tsc --noEmit` | Passed; no errors |
| `npm run build` | Passed; production build compiled, typechecked and generated all pages |
| `.venv/bin/pytest -q` from repository root | 506 passed, 548 skipped, 6 existing warnings |
| `git diff --check` | Passed |
| Browser/manual smoke check | Not performed: no browser automation/manual browser tool was available in the session |
| Destructive live integration/clean-stack check | Not run; no backend/API Python changed. Normal backend regression was run. Development database was not used for destructive testing |

The 30 new tests comprise 3 API-module tests, 16 editor/workflow cases and 11 workspace/server-page cases. The follow-up BOOLEAN regression verifies that selecting PRESENT leaves an unset value unselected, blocks saving without a choice, and submits JSON false only after an explicit False selection. They cover allowlisted requests, explicit null and no-op PATCH protection, precise numeric strings, actual booleans, registry enum/order/badges/units, state-only omissions, 422 draft retention, type-change conflict/success, terminal ownership/lifecycle, node removal refresh, connection create/edit/remove/restore and inactive endpoints, duplicate endpoint rows, debounced response races, filter-independent deep links, missing-object cleanup, registry retry/cache, read-only mutation hiding, stale read-only refresh and banner placement. Existing document/project tests passed unchanged.

## Dependencies, limitations and remaining scope

- No runtime or development dependencies were added; package manifests and lockfiles are unchanged. A temporary formatter invocation did not install a project dependency.
- No visual/browser smoke test was performed. jsdom component tests and the production build are the available frontend evidence.
- Existing APIs remain unpaginated. Topology uses whole revision lists and the accepted backend bulk consistency checks. Large-model performance review remains Phase 5G work.
- The accepted API returns INTEGER slots as JSON numbers. Although new integer drafts are submitted as exact strings, an existing integer beyond JavaScript's safe range may already lose precision in the shared JSON decoder. No arbitrary-precision response decoding/API change was introduced in this UI slice; the submission test does not claim to fix that pre-existing response-contract limitation. This does not block 5F and is explicitly carried into [Phase 5G's priority review](PROJECT_STATUS.md#phase-5g--priority-review-items), which must prove enforced safe bounds or adopt lossless response serialization with cross-layer regression coverage.
- Registry caching is component-local, not persistent or global. The UI ignores superseded request results but does not cancel their network transport.
- Drafts are local to mounted editors, without cross-session persistence or an unsaved-change navigation guard. General refresh/version handling is intentionally local to this workspace.
- No DB migration or new API was required. No graph canvas, React Flow, AI extraction, evidence/candidate/reconciliation workflow, validation findings, verification mutation, protection/study model, study export or other Phase 6+ scope was implemented.
- Phase 5G's broader hardening, clean-stack validation, debt review and final Phase 5 freeze have not begun.
