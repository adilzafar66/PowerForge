"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight, Search } from "lucide-react";

import { useExtractionStatuses } from "@/components/document-extraction-panel";
import { EvidencePagination, PanelMessage, readableKey } from "@/components/extraction-evidence-ui";
import { ExtractionRunHistory } from "@/components/extraction-run-history";
import { StatusChip } from "@/components/documents-ui";
import { Select } from "@/components/ui/select";
import { apiErrorOf } from "@/lib/api";
import { getEngineeringRegistry } from "@/lib/engineering-model";
import {
  families,
  familyLabel,
  getEvidence,
  getGroupCandidates,
  getGroups,
  runState,
  type Candidate,
  type DocumentScope,
  type EvidenceFilters,
  type EvidenceGroup,
  type HistoryFamily,
  type HistoryRun,
  type MappingStatus,
  type RunPair,
} from "@/lib/extraction";
import { isRunning } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

type Params = Pick<URLSearchParams, "get">;
type Patch = Record<string, string | number | null>;
export type UpdateEvidenceRoute = (patch: Patch, method?: "push" | "replace") => void;

const filterInput = "h-[38px] w-full min-w-0 rounded-[var(--pf-radius-control)] border border-border bg-panel px-3 text-workspace-caption text-ink outline-none focus-visible:ring-2 focus-visible:ring-ring";
const card = "rounded-[var(--pf-radius-control)] border border-border bg-panel";
const tabClass = "min-w-0 flex-1 rounded-md px-1.5 py-2 text-workspace-caption font-semibold text-muted outline-none focus-visible:ring-2 focus-visible:ring-ring";

function uuid(value: string | null) {
  return value && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value) ? value : null;
}

function offset(value: string | null) {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 0 ? parsed : 0;
}

function family(value: string | null): HistoryFamily {
  if (value === "tables" || value === "enrichment") return value;
  return "engineering";
}

function groupLabel(group: Pick<EvidenceGroup, "label" | "tag_text" | "source_group_id">) {
  return group.tag_text || group.label || (group.source_group_id ? "Untitled source group" : "Ungrouped observations");
}

function groupKey(group: Pick<EvidenceGroup, "run_id" | "source_group_id">) {
  return `${group.run_id}:${group.source_group_id ?? "ungrouped"}`;
}

function pin(pair: RunPair): Patch {
  return { evidencePinned: "1", engineeringRun: pair.engineering, tablesRun: pair.tables };
}

function bestCitation(candidate?: Candidate) {
  return candidate?.evidence.find((item) => item.role === "PRIMARY")?.evidence
    ?? candidate?.evidence.find((item) => item.role === "SUPPORTING")?.evidence;
}

export function useViewerEvidence(scope: DocumentScope, params: Params, active: boolean) {
  const key = keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId);
  const statuses = useExtractionStatuses(scope.projectId, scope.revisionId, active ? [scope.documentId] : []);
  const status = statuses.data?.[scope.documentId];
  const latest: RunPair = {
    engineering: status?.engineering.effective_result?.id ?? null,
    tables: status?.tables.effective_result?.id ?? null,
  };
  const pinned = params.get("evidencePinned") === "1";
  const pair = pinned ? {
    engineering: uuid(params.get("engineeringRun")),
    tables: uuid(params.get("tablesRun")),
  } : latest;
  const history = params.get("evidenceTab") === "history";
  const groupRun = uuid(params.get("groupRun"));
  const groupParam = params.get("sourceGroup");
  const groupId = uuid(groupParam);
  const groupFamily = families.find((item) => pair[item] && pair[item] === groupRun);
  const candidateId = uuid(params.get("candidate"));
  const opened = !!(groupRun && groupFamily && (groupId || groupParam === "ungrouped"));
  const selected = useQuery({
    queryKey: [...key, "candidate", groupRun, groupId, candidateId],
    queryFn: ({ signal }) => getGroupCandidates(scope, groupRun!, groupFamily!, groupId, {}, 0, signal, candidateId!),
    enabled: active && !history && opened && !!candidateId,
    retry: 1,
  });
  const candidate = selected.data?.items[0];
  const citation = bestCitation(candidate);
  const source = useQuery({
    queryKey: [...key, "evidence", groupRun, citation?.id],
    queryFn: async ({ signal }) => {
      const evidence = await getEvidence(scope, citation!.id, signal);
      if (evidence.run_id !== groupRun) throw new Error("Evidence belongs to a different run.");
      return evidence;
    },
    enabled: active && !history && !!citation,
    retry: 1,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  return {
    key, statuses, status, pinned, pair, history, opened, groupRun, groupId, groupFamily,
    candidateId, candidate, citation, selected, source,
  };
}

type Browser = ReturnType<typeof useViewerEvidence>;

export function ExtractionEvidencePanel({
  scope, params, browser, update, page, scrollRef, highlighted, canMutate, onReextract,
}: {
  scope: DocumentScope;
  params: Params;
  browser: Browser;
  update: UpdateEvidenceRoute;
  page: number;
  scrollRef: RefObject<HTMLDivElement | null>;
  highlighted: boolean;
  canMutate: boolean;
  onReextract: (run: HistoryRun) => void;
}) {
  const tab = browser.history ? "history" : "candidates";
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const showTabs = !browser.opened || browser.history;
  return (
    <div className="space-y-3.5">
      {showTabs && (
        <>
          <div className={cn(card, "bg-accent-tint/40 p-3 text-workspace-caption leading-relaxed text-muted")}>
            <strong className="block text-ink">Extraction Evidence</strong>
            Browse source-grounded observations from Engineering and Tables. Each stays tied to its original run and source.
          </div>
          <div role="tablist" aria-label="Extraction evidence sections" className={cn(card, "flex gap-1 bg-soft p-1")}>
            {(["candidates", "history"] as const).map((value, index) => (
              <button
                key={value}
                id={`evidence-tab-${value}`}
                type="button"
                ref={(element) => { buttons.current[index] = element; }}
                role="tab"
                aria-selected={tab === value}
                aria-controls={`evidence-panel-${value}`}
                tabIndex={tab === value ? 0 : -1}
                onClick={() => update({ evidenceTab: value === "history" ? "history" : null })}
                onKeyDown={(event) => {
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
                  event.preventDefault();
                  const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
                  buttons.current[next]?.focus();
                  buttons.current[next]?.click();
                }}
                className={cn(tabClass, tab === value && "bg-panel text-accent shadow-xs")}
              >
                {value === "candidates" ? "Candidates" : "Run history"}
              </button>
            ))}
          </div>
        </>
      )}
      <section
        id={`evidence-panel-${tab}`}
        role={showTabs ? "tabpanel" : undefined}
        aria-labelledby={showTabs ? `evidence-tab-${tab}` : undefined}
      >
        {browser.history ? (
          <ExtractionRunHistory
            scope={scope}
            activeFamily={family(params.get("historyFamily"))}
            runId={uuid(params.get("historyRun"))}
            pair={params.get("historicalPair") === "1"
              ? browser.pair
              : { engineering: null, tables: null }}
            update={update}
            canMutate={canMutate}
            currentProcessingId={browser.status?.processing_run_id}
            onReextract={onReextract}
          />
        ) : (
          <CandidateBrowser
            scope={scope}
            params={params}
            browser={browser}
            update={update}
            page={page}
            scrollRef={scrollRef}
            highlighted={highlighted}
          />
        )}
      </section>
    </div>
  );
}

function CandidateBrowser({
  scope, params, browser, update, page, scrollRef, highlighted,
}: {
  scope: DocumentScope;
  params: Params;
  browser: Browser;
  update: UpdateEvidenceRoute;
  page: number;
  scrollRef: RefObject<HTMLDivElement | null>;
  highlighted: boolean;
}) {
  const { key, pair, opened, groupRun, groupFamily, groupId, status, statuses } = browser;
  const search = params.get("groupSearch")?.slice(0, 200) ?? "";
  const currentOnly = params.get("pageScope") === "current";
  const savedPage = offset(params.get("groupReturnPage")) || page;
  const mapping = params.get("mapping");
  const filters: EvidenceFilters = {
    search: search.trim() || undefined,
    page: currentOnly ? (opened ? savedPage : page) : undefined,
    equipment_hint: params.get("equipmentHint")?.slice(0, 100) || undefined,
    mapping_status: mapping === "MAPPED" || mapping === "UNMAPPED" || mapping === "INVALID" ? mapping : undefined,
  };
  const start = offset(params.get("groupOffset"));
  const groupStart = offset(params.get("candidateOffset"));
  const hasRuns = !!(pair.engineering || pair.tables);
  const groups = useQuery({
    queryKey: [...key, "groups", pair, filters, start],
    queryFn: ({ signal }) => getGroups(scope, pair, filters, start, signal),
    enabled: hasRuns && !opened,
    retry: 1,
  });
  const members = useQuery({
    queryKey: [...key, "group", groupRun, groupId, filters, groupStart],
    queryFn: ({ signal }) => getGroupCandidates(scope, groupRun!, groupFamily!, groupId, filters, groupStart, signal),
    enabled: opened,
    retry: 1,
  });
  const registry = useQuery({
    queryKey: keys.registry,
    queryFn: getEngineeringRegistry,
    enabled: hasRuns && !opened,
  });
  const scrollPositions = useRef(new Map<string, number>());
  const listState = JSON.stringify([pair, filters, start]);
  const groupsLoaded = !!groups.data;
  useEffect(() => {
    if (!opened && groupsLoaded && scrollRef.current) {
      scrollRef.current.scrollTop = scrollPositions.current.get(listState) ?? 0;
    }
  }, [opened, listState, groupsLoaded, scrollRef]);

  const filterChange = (patch: Patch) => update({ ...patch, groupOffset: null }, "replace");

  function openGroup(group: EvidenceGroup) {
    scrollPositions.current.set(listState, scrollRef.current?.scrollTop ?? 0);
    update({
      ...pin(pair),
      groupRun: group.run_id,
      sourceGroup: group.source_group_id ?? "ungrouped",
      groupReturnPage: page,
      candidate: null,
      candidateOffset: null,
    });
    scrollRef.current?.scrollTo?.({ top: 0 });
  }

  function pickCandidate(candidate: Candidate) {
    const candidatePage = bestCitation(candidate)?.source_page_number;
    update({
      candidate: browser.candidateId === candidate.id ? null : candidate.id,
      ...(candidatePage && browser.candidateId !== candidate.id ? { page: candidatePage } : {}),
    });
  }

  function clearGroup() {
    update({
      groupRun: null, sourceGroup: null, groupReturnPage: null, candidate: null, candidateOffset: null, page: savedPage,
    });
  }

  if (params.get("groupRun") && !opened && (browser.pinned || status)) {
    return <PanelMessage error retry={clearGroup}>This group is unavailable in the selected runs.</PanelMessage>;
  }

  if (opened) {
    const selected = browser.candidate;
    const listed = members.data?.items ?? [];
    const items = selected && !listed.some((item) => item.id === selected.id) ? [selected, ...listed] : listed;
    const group = items[0]?.source_group;
    const label = groupLabel({ source_group_id: groupId, tag_text: group?.tag_text ?? null, label: group?.label ?? null });
    return (
      <div className="space-y-3">
        <button type="button" className="flex items-center gap-1 text-workspace-caption font-semibold text-accent hover:underline" onClick={clearGroup}>
          <ArrowLeft aria-hidden className="size-3.5" /> Back to source groups
        </button>
        <div className="border-b border-border pb-3">
          <p className="m-0 text-workspace-overline font-bold tracking-wide text-muted uppercase">Source group · Identity unresolved</p>
          <h3 className="m-0 mt-1 break-words text-workspace-section font-bold text-ink">{label}</h3>
          <p className="m-0 mt-1 text-workspace-caption text-muted">{familyLabel[groupFamily!]} · {groupRun!.slice(0, 8)}{members.data ? ` · ${members.data.total} ${members.data.total === 1 ? "candidate" : "candidates"}` : ""}</p>
        </div>
        <p className="m-0 text-workspace-overline font-bold tracking-wide text-muted uppercase">Extracted candidates</p>
        {members.isPending && <p role="status" className="text-workspace-caption text-muted">Loading candidates…</p>}
        {members.error && <PanelMessage error retry={() => void members.refetch()}>{apiErrorOf(members.error).detail}</PanelMessage>}
        {browser.candidateId && !selected && !browser.selected.isPending && (
          <PanelMessage error retry={() => update({ candidate: null })}>The selected candidate is unavailable in this group.</PanelMessage>
        )}
        {!items.length && members.data && <PanelMessage>No supported candidates match this group and filters.</PanelMessage>}
        {items.map((candidate) => (
          <CandidateCard
            key={candidate.id}
            candidate={candidate}
            expanded={candidate.id === browser.candidateId}
            highlighted={highlighted}
            browser={browser}
            page={page}
            onSelect={() => pickCandidate(candidate)}
            onLocate={(next) => update({ page: next })}
          />
        ))}
        {members.data && <EvidencePagination total={members.data.total} size={20} start={groupStart} onChange={(value) => update({ candidateOffset: value || null, candidate: null })} />}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <h3 className="m-0 text-workspace-label font-bold text-ink">Source groups</h3>
        {groups.data && <span className="text-workspace-caption text-muted">{groups.data.total} {groups.data.total === 1 ? "group" : "groups"}</span>}
      </div>
      <PanelMessage>
        Groups organize cited observations within a source. Equipment identity remains unresolved.
        {families.map((item) => {
          const selectedRun = pair[item];
          const attempt = status?.[item].latest_attempt;
          return (
            <span key={item} title={selectedRun ?? undefined} className="mt-1 block break-words">
              <strong>{familyLabel[item]}</strong> · {selectedRun ? `Run ${selectedRun.slice(0, 8)}` : "No result selected"}
              {isRunning(attempt?.status) && <span> · Latest attempt {runState(attempt).label.toLowerCase()}</span>}
            </span>
          );
        })}
        {browser.pinned && (
          <button type="button" className="mt-1 text-accent hover:underline" onClick={() => update({ evidencePinned: null, historicalPair: null, engineeringRun: null, tablesRun: null, groupOffset: null })}>
            View latest results
          </button>
        )}
      </PanelMessage>
      {statuses.error && <PanelMessage error retry={() => void statuses.refetch()}>{apiErrorOf(statuses.error).detail}</PanelMessage>}
      {!hasRuns && !browser.pinned && statuses.isPending && <p role="status" className="text-workspace-caption text-muted">Checking for extraction results…</p>}
      {!hasRuns && status && (
        <PanelMessage>
          No compatible results for the current source.
          <button type="button" className="mt-1 block text-accent hover:underline" onClick={() => update({ evidenceTab: "history" })}>View run history</button>
        </PanelMessage>
      )}
      {hasRuns && (
        <>
          <div className="relative">
            <Search aria-hidden className="pointer-events-none absolute top-3 left-3 size-3.5 text-muted" />
            <GroupSearch value={search} onCommit={(value) => filterChange({ groupSearch: value })} />
          </div>
          <div role="group" aria-label="Page scope" className="flex gap-1 rounded-[var(--pf-radius-control)] bg-soft p-1">
            {[false, true].map((current) => (
              <button type="button" key={String(current)} aria-pressed={currentOnly === current} className={cn(tabClass, "py-1", currentOnly === current && "bg-panel text-accent shadow-xs")} onClick={() => filterChange({ pageScope: current ? "current" : null })}>
                {current ? "Current page" : "All pages"}
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="min-w-0 text-workspace-caption font-semibold text-muted">
              Equipment type hint
              <Select aria-label="Equipment type hint" presentation="workspace" size="sm" className="mt-1 w-full" value={filters.equipment_hint ?? "all"} onValueChange={(value) => filterChange({ equipmentHint: value === "all" ? null : value })}>
                <option value="all">All types</option>
                {registry.data?.equipment_types.map((item) => <option key={item.key} value={item.key}>{item.display_name}</option>)}
                {filters.equipment_hint && !registry.data?.equipment_types.some((item) => item.key === filters.equipment_hint) && (
                  <option value={filters.equipment_hint}>{readableKey(filters.equipment_hint)}</option>
                )}
              </Select>
            </label>
            <label className="min-w-0 text-workspace-caption font-semibold text-muted">
              Mapping status
              <Select aria-label="Mapping status" presentation="workspace" size="sm" className="mt-1 w-full" value={filters.mapping_status ?? "all"} onValueChange={(value) => filterChange({ mapping: value === "all" ? null : value })}>
                <option value="all">All statuses</option>
                <option value="MAPPED">Mapped</option>
                <option value="UNMAPPED">Unmapped</option>
                <option value="INVALID">Invalid</option>
              </Select>
            </label>
          </div>
          {registry.error && <PanelMessage error retry={() => void registry.refetch()}>Equipment type hints could not load.</PanelMessage>}
          {groups.isPending && <p role="status" className="text-workspace-caption text-muted">Loading source groups…</p>}
          {groups.error && <PanelMessage error retry={() => void groups.refetch()}>{apiErrorOf(groups.error).detail}</PanelMessage>}
          {groups.data?.items.length === 0 && <PanelMessage>No source groups match the selected results and filters.</PanelMessage>}
          {groups.data?.items.map((group) => (
            <button type="button" key={groupKey(group)} className={cn(card, "flex w-full items-center justify-between gap-2 p-3 text-left hover:bg-soft focus-visible:ring-2 focus-visible:ring-ring")} onClick={() => openGroup(group)}>
              <span className="min-w-0">
                <strong className="block break-words text-workspace-label text-ink">{groupLabel(group)}</strong>
                <span className="mt-0.5 block text-workspace-caption text-muted">
                  {group.equipment_type_hint ? `${readableKey(group.equipment_type_hint)} · ` : ""}
                  {group.page_numbers.length === 1 ? "Page" : "Pages"} {group.page_numbers.join(", ")}
                </span>
                <span className="block text-workspace-caption text-muted">{familyLabel[group.family]} · {group.run_id.slice(0, 8)} · {group.candidate_count} {group.candidate_count === 1 ? "candidate" : "candidates"}</span>
              </span>
              <ChevronRight aria-hidden className="size-4 shrink-0 text-muted" />
            </button>
          ))}
          {groups.data && <EvidencePagination total={groups.data.total} size={25} start={start} onChange={(value) => update({ groupOffset: value || null })} />}
        </>
      )}
    </div>
  );
}

function GroupSearch({ value, onCommit }: { value: string; onCommit: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const pending = useRef<ReturnType<typeof setTimeout> | null>(null);
  const commitRef = useRef(onCommit);
  const committed = useRef(value);
  commitRef.current = onCommit;
  useEffect(() => {
    if (value === committed.current) return;
    committed.current = value;
    if (pending.current !== null) clearTimeout(pending.current);
    setDraft(value);
  }, [value]);
  useEffect(() => () => {
    if (pending.current !== null) clearTimeout(pending.current);
  }, []);
  return (
    <input
      type="search"
      aria-label="Search source groups"
      className={cn(filterInput, "pl-8")}
      placeholder="Search tag, type, attribute or value…"
      maxLength={200}
      value={draft}
      onChange={(event) => {
        const next = event.target.value;
        setDraft(next);
        if (pending.current !== null) clearTimeout(pending.current);
        pending.current = setTimeout(() => {
          committed.current = next;
          commitRef.current(next);
        }, 240);
      }}
    />
  );
}

const mappingTones = { MAPPED: "green", UNMAPPED: "yellow", INVALID: "red" } as const satisfies Record<MappingStatus, string>;

function CandidateCard({
  candidate, expanded, highlighted, browser, page, onSelect, onLocate,
}: {
  candidate: Candidate;
  expanded: boolean;
  highlighted: boolean;
  browser: Browser;
  page: number;
  onSelect: () => void;
  onLocate: (page: number) => void;
}) {
  const citation = bestCitation(candidate);
  const locator = citation?.source_locator;
  const pageNumber = citation?.source_page_number;
  const sourceLabel = locator?.reading_basis === "OCR" || citation?.source_kind === "OCR_TEXT" ? "OCR"
    : locator?.reading_basis === "NATIVE_PDF" || citation?.source_kind === "NATIVE_TEXT" || citation?.grounding_precision === "TEXT_OFFSETS" ? "Native PDF" : "Page-only";
  const normalized = candidate.numeric_value ?? candidate.integer_value ?? candidate.text_value ?? candidate.boolean_value;
  const raw = [candidate.raw_value, candidate.raw_unit].filter(Boolean).join(" ") || candidate.raw_text;
  const value = normalized !== null ? [String(normalized), candidate.unit].filter(Boolean).join(" ") : candidate.observed_tag || raw;
  const field = candidate.attribute_key ?? (candidate.kind === "EQUIPMENT_MENTION" ? candidate.equipment_type_key : null);
  const detailId = `candidate-detail-${candidate.id}`;
  const evidence = browser.source.data;
  const reason = candidate.explanation ?? (candidate.reason_code ? readableKey(candidate.reason_code) : null);
  return (
    <article className={cn(card, "overflow-hidden", expanded && "border-accent/45 bg-accent-tint/35")}>
      <button type="button" aria-expanded={expanded} aria-controls={expanded ? detailId : undefined} className="block w-full p-3 text-left hover:bg-soft focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring" onClick={onSelect}>
        <span className="flex flex-wrap items-start justify-between gap-1.5">
          <strong className="min-w-0 break-words text-workspace-label text-ink">{field ? readableKey(field) : candidate.kind === "EQUIPMENT_MENTION" ? "Equipment mention" : "Observed attribute"}</strong>
          <StatusChip tone={mappingTones[candidate.mapping_status]}>{readableKey(candidate.mapping_status)}</StatusChip>
        </span>
        <span className="mt-1 block break-words text-workspace-label font-semibold text-ink">{value}</span>
        <span className="mt-1 block text-workspace-caption text-muted">{pageNumber ? `Page ${pageNumber} · ` : ""}{candidate.kind === "EQUIPMENT_MENTION" ? "Equipment mention" : "Attribute candidate"}</span>
      </button>
      {expanded && (
        <div id={detailId} className="space-y-2.5 border-t border-border p-3 text-workspace-caption text-muted">
          <dl className="m-0 space-y-1.5">
            {reason && <div className="flex justify-between gap-2"><dt>Mapping</dt><dd className="m-0 break-words text-right text-ink">{reason}</dd></div>}
            {raw !== value && <div className="flex justify-between gap-2"><dt>Original reading</dt><dd className="m-0 break-words text-right text-ink">{raw}</dd></div>}
            <div className="flex justify-between gap-2"><dt>Source</dt><dd className="m-0 font-semibold text-ink">{sourceLabel}</dd></div>
            <div className="flex justify-between gap-2"><dt>Physical identity</dt><dd className="m-0 font-semibold text-ink">Unresolved</dd></div>
          </dl>
          {browser.source.isFetching && !evidence && <p role="status" className="m-0">Loading source…</p>}
          {browser.source.error && <PanelMessage error retry={() => void browser.source.refetch()}>Pinned source evidence could not load.</PanelMessage>}
          {highlighted ? <p role="status" className="m-0 font-semibold text-accent">Source highlighted on page</p>
            : pageNumber && pageNumber !== page ? <button type="button" className="text-accent hover:underline" onClick={() => onLocate(pageNumber)}>Locate source</button>
            : evidence && <p className="m-0">{!evidence.source_image_url ? "The pinned page image is unavailable." : evidence.region ? "Source region is available on the pinned page." : "Page-level citation. No grounded highlight is available."}</p>}
          <details className="border-t border-border pt-2">
            <summary className="cursor-pointer font-semibold text-accent">Source details</summary>
            <div className="mt-2 space-y-2 break-words">
              {citation?.source_snippet && <blockquote className="m-0 whitespace-pre-wrap border-l-2 border-border pl-2 text-ink">{citation.source_snippet}</blockquote>}
              {candidate.evidence.filter((item) => item.evidence.id !== citation?.id && item.evidence.source_snippet).map(({ evidence: context }) => (
                <p key={context.id} className="m-0 whitespace-pre-wrap">Context · {context.source_snippet}</p>
              ))}
              <p className="m-0">Source-local group · {candidate.source_group?.tag_text || candidate.source_group?.label || "Ungrouped observations"}</p>
              <p className="m-0">Mapping records a registry interpretation. The printed reading and equipment identity require independent verification.</p>
            </div>
          </details>
        </div>
      )}
    </article>
  );
}
