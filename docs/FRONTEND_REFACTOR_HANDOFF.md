# Frontend component and design-token refactor

Implemented on `codex/frontend-component-token-refactor`, based on merged UI-C `30843ea`. This is a presentation architecture refactor. Routes, backend contracts, domain serialization, query behavior, permissions, lifecycle operations, and draft guards retain their existing implementations. Design-reference material was not modified.

## Audit and decisions

- Removed the 422-line `workspace-styles.ts` dictionary and `ui-c-workspace.tsx` compatibility module. Element owners now carry their own utilities, without UI-C markers or cross-component descendant selectors.
- Existing Button, Badge, PageHeader, Field, Input, Textarea, Select, Sheet, ConfirmDialog, SegmentedControl, Card, and CardContent provide explicit workspace presentations. Existing default consumers retain their treatment. Button's direct icon selector is intentionally local to that control's icon contract.
- Workspace layout, notes, register table anatomy, semantic detail lists, form sections, drawer anatomy, and action footers are shared components. Projects/Revisions retain different table density, filter styles, badge colors, rails, and drawers. Timeline event presentation stays local to Revision Overview.
- Project editor sizing is selected by a presentation prop, not title text. Confirmation overlays are selected by a presentation prop, not class-name parsing. Existing Radix modal mechanics and editor guards are retained.
- Audited Documents/Equipment/Topology and their shared controls. Retained `revision-table.tsx`: its small class helpers are readable and already share the intended distinct presentation. Those feature screens were not restructured. System Status was checked as another default-primitive consumer.
- Preserved adjusted 29px titles, current font families and weights, and the intentionally absent Project Overview section headings. Preserved formerly effective specificity outcomes, including visible mobile project-status badges, danger-colored workspace error notices, and distinct project drawer padding on mobile; ineffective caller overrides were removed rather than silently changing their appearance.

## Tokens and contributor guidance

`apps/web/src/styles/design-tokens.css` is the canonical source for shared values and Tailwind v4 aliases. It groups semantic colors, typography, layout/control dimensions, radii/elevation, and motion. Intentional visual differences have distinct values; matching typography roles use aliases. Ordinary local spacing remains readable Tailwind utilities rather than a variable per pixel value.

`globals.css` retains the existing font loading, document defaults, focus/selection/scrollbars, reduced-motion and forced-color behavior, plus the compound select-option and native checkbox states. `workspace-motion.css` retains only appearance/drawer keyframes. The feedback animation remains with its existing global behavior. `workspace-tokens.css` was replaced by the consolidated token source.

Use existing primitives with explicit presentation props rather than wrapping a default component in ancestor selectors. Use `cn` for overrides. Its configuration knows the custom font-size and shadow utilities so it does not confuse font sizes with text colors or leave conflicting elevation classes. Keep explicit line height after typography variant selection when combining classes; regression tests cover this composition contract.

## Verification

The opt-in harness and instructions are in `apps/web/visual/README.md`. It serves synthetic records to both SSR and browser queries, rejects unsupported API requests and all writes, caches exact font bytes, fixes display dates, and records screenshots, geometry, results, and logs. Generated artifacts stay outside Git. It does not introduce fixture behavior into the application.

The original 54-view baseline was captured before production edits. Further rendering diagnostics used an isolated copy of the same unchanged Git revision; no baseline was regenerated from refactored source. Software rasterization removed most tiny rendering differences observed even between unchanged-source captures. The comparator remains strict: no thresholds were widened, no regions masked, and no failing image was promoted to a baseline.

The acceptance run exposed two genuine migration regressions: the mobile project-status badge was hidden after its formerly effective display rule moved into a mergeable component class, and three workspace alerts lost their danger text color. Both were corrected. The final 54 captures have identical geometry and computed styles, and all interaction assertions complete without page, fixture, or write-request failures.

Strict image comparison still reports isolated raster differences. Two consecutive final runs reported 10 and then 6 affected views, with 7–68 and 8–50 changed pixels respectively. The varying set, an unchanged-source diagnostic that differed by 15 pixels, and inspection of the remaining pixels identify software text/rounded-edge antialiasing rather than layout or token changes: residual channels differ by one or two values at isolated edge pixels. This remains a nonzero comparator result and is recorded as the only unresolved verification risk; the baseline, threshold, and images were not altered to conceal it.

## Final verification

- `npm test`: 298 tests passed across 24 files.
- `npx tsc --noEmit`: passed.
- `npm run lint`: passed with no warnings or errors.
- `npm run build`: passed, including Next.js type validation and all production routes.
- Full visual harness: 54 views captured; geometry, computed styles, fixture coverage, interactions, and runtime checks passed. Exact image comparison retained the isolated antialiasing differences described above.
