# PowerForge — Frontend Component, Styling & Design Token Refactor

## Objective

Refactor the **existing `apps/web` frontend** into a cleaner, maintainable, **Tailwind-first, component-based design architecture** before beginning UI-D/E/F.

This is an **architecture-only refactor**, not a visual redesign or feature implementation. Audit the entire frontend, but make changes **only where they produce a clear maintainability benefit**, prioritizing the UI-C Projects & Revisions implementation.

Start from the latest `main` after UI-C has been merged. Work on a dedicated refactor branch and inspect the repository's actual current state before changing anything. Preserve all approved screens, working behavior, and backend contracts.

## 1. Audit first; refactor selectively

Inspect shared UI primitives, page/workspace components, Tailwind class usage, design tokens and custom CSS across `apps/web`, especially:

- `src/components/ui/workspace-styles.ts`, `workspace-patterns.tsx`, `ui-c-workspace.tsx`, `workspace-editor.tsx` and UI-C screen components.
- Existing UI-A primitives in `src/components/ui/` (e.g. `button.tsx`, `card.tsx`, `badge.tsx`, `field.tsx`, `input.tsx`, `select.tsx`, `sheet.tsx`, `page-header.tsx`).
- Shared presentation in `src/components/ui/revision-table.tsx` and its Equipment/Documents/Topology consumers.
- `src/app/globals.css`, `src/styles/workspace-tokens.css`, `src/styles/workspace-motion.css`, and the existing Tailwind v4 `@theme` integration.

Identify redundant components, repeated markup/styles, oversized styling dictionaries, fragile descendant selectors, conflicting tokens, and ad hoc values.

**Do not refactor something merely because it is different:** retain simple, well-structured code and intentionally distinct visual treatments.

## 2. Make shared React components own their styling

The principal concern is the large `workspace-styles.ts` file: long Tailwind class-string recipes and complex descendant selectors reproduce a stylesheet inside TypeScript and couple styling to descendant markup.

- Move appropriate Tailwind classes into the reusable React components that own the elements: workspace/page layouts, headers, cards, detail rows, tables, controls, drawers, form sections, action footers, etc.
- Prefer **composition and clear component props** over broad descendant selectors, cross-component styling dependencies, and large centralized class maps.
- Reuse and extend existing UI-A components where sensible, rather than maintaining parallel components for the same purpose. Introduce variants with `class-variance-authority` / `cn` only where they clarify genuine differences.
- Preserve necessary distinct variants between current workspaces. Avoid both extremes: a giant central class dictionary **and** copy-pasting large strings across many screens.
- Remove obsolete class dictionaries, marker selectors, wrappers, or styles once consumers have migrated. Small local class constants for genuine reuse are fine; abstraction is not an end in itself.
- Ensure the future UI-D/E/F workspaces can use the resulting shared primitives without speculative rewrites of their current feature-specific screens.

## 3. Consolidate and improve the design token system

Establish an understandable **single source of truth for shared design values**, integrating with the project's existing Tailwind v4 setup. Cover:

- Semantic colors: canvas/surfaces, text, borders, actions, focus, hover/selection, and status states.
- Typography: font families, sizes, weights, line heights, and letter spacing.
- Spacing, border radii, control and layout dimensions, elevations/shadows.
- Motion: transition durations, easing, and keyframe timings.

Review `globals.css` and `workspace-tokens.css` together. Organize shared CSS variables coherently, remove duplicate/conflicting definitions, and make Tailwind components consume the same tokens.

Keep tokens **semantic where genuinely shared**; do not create a global variable for every one-off pixel value. One-off values may remain local Tailwind utilities.

**Critical:** This is *not* an opportunity to normalize the actual visual values. Where two existing screens intentionally differ, preserve the difference through appropriate variants or local values. Preserve the current application font family, the **intentional post-UI-C typography adjustments**, and the **intentional removal of the two Project Overview section headings**.

Do not change the look merely to simplify a spacing or typography scale.

## 4. Tailwind-first, with narrowly justified CSS

Use Tailwind utilities for routine component styling, preferably directly inside the owning components.

Maintain CSS custom properties for theme/design tokens and minimal standalone CSS for genuinely necessary global behavior, complex control states, accessibility, or keyframe definitions.

Do not migrate all CSS blindly to obscure arbitrary Tailwind selectors, and do not create another large parallel CSS stylesheet.

Keep the styling approach straightforward for later contributors.

## 5. Non-negotiable scope and behavior safeguards

- **No perceptible UI change:** retain existing layouts, font sizes/weights, line heights, spacing, dimensions, colors, borders, responsive behavior, button/select/checkbox styling, transitions, animations, and focus/hover/disabled states.
- Preserve all routes, navigation, project/revision lifecycle semantics, editor drafts and dirty-state guards, TanStack Query behavior, server-side validations, exact engineering decimal handling, and read-only permissions.
- Do **not** modify backend APIs, database/schema, canonical engineering behavior, extraction functionality, or unrelated application features.
- Do **not** implement UI-D, UI-E, or UI-F. Audit Equipment/Documents/Topology and refactor a small shared primitive only if clearly justified, but **do not redesign or extensively restructure those feature screens**; their visual implementations will be addressed in UI-D/E/F.
- Treat the existing GitHub design-reference/prototypes as reference material only. Do not update them as part of this refactor.

## 6. Verification and completion

1. Capture a **before** visual baseline of representative existing pages and states using stable fixture data where possible: Projects list, Create Project, Project Overview, Revisions register, Revision Overview, project/revision editors, dialogs, and relevant mobile views. Include other affected screens if shared primitives change.
2. Refactor in small, reviewable steps; compare **after** screenshots at identical viewport sizes, browser conditions, and UI states. Investigate and correct differences rather than claiming similarity from code inspection alone. Honor reduced-motion and keyboard/focus behavior.
3. Run applicable frontend tests, TypeScript, ESLint, and the production build. Keep tests focused; add or update tests only for changed component contracts or meaningful regression risks. Do not weaken existing tests to make the refactor pass.
4. Provide a concise handoff summarizing the audit, component consolidation, design token organization, removed/replaced files, remaining justified CSS, tests/build results, and any visual differences or unresolved risks. Clearly distinguish checks actually executed from those not possible in the environment.

**Acceptance criterion:** The app looks and behaves the same as immediately before this refactor, but the shared styling and component architecture is significantly easier to understand, reuse, and extend for UI-D/E/F.