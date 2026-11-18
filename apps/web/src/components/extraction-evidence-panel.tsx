"use client";

import { useEffect, useRef, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronRight } from "lucide-react";

import { useExtractionStatuses } from "@/components/document-extraction-panel";
import { EvidencePagination, PanelMessage, readableKey } from "@/components/extraction-evidence-ui";
import { ExtractionRunHistory } from "@/components/extraction-run-history";
import { StatusChip, docButtonClass } from "@/components/documents-ui";
import { Select } from "@/components/ui/select";
import { apiErrorOf } from "@/lib/api";
import { getEngineeringRegistry } from "@/lib/engineering-model";
import {
  getEvidence, getGroupCandidates, getGroups, getRunSources, valueSourceSupportLabel,
  type Candidate, type DocumentScope, type EvidenceDetail, type EvidenceFilters,
  type HistoryRun, type MappingStatus,
} from "@/lib/extraction";
import { isRunning, jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

type Params = Pick<URLSearchParams, "get">;
type Patch = Record<string, string | number | null>;
export type UpdateEvidenceRoute = (patch: Patch, method?: "push" | "replace") => void;
const card = "rounded-[var(--pf-radius-control)] border border-border bg-panel";

function uuid(value: string | null) {
  return value && /^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/i.test(value) ? value : null;
}

export function useViewerEvidence(scope: DocumentScope, params: Params, active: boolean) {
  const key = keys.extractionDocument(scope.projectId, scope.revisionId, scope.documentId);
  const statuses = useExtractionStatuses(scope.projectId, scope.revisionId, active ? [scope.documentId] : []);
  const status = statuses.data?.[scope.documentId];
  const latest = status?.extraction.effective_result?.id ?? null;
  const explicitRun = uuid(params.get("extractionRun"));
  const runId = explicitRun ?? latest;
  const history = params.get("evidenceTab") === "history";
  const groupParam = params.get("equipmentGroup");
  const groupId = groupParam === "unassigned" ? groupParam : uuid(groupParam);
  const candidateId = uuid(params.get("candidate"));
  const opened = !!(runId && groupId && !history);
  const sources = useQuery({
    queryKey: [...key, "sources", runId],
    queryFn: ({ signal }) => getRunSources(scope, runId!, signal),
    enabled: active && !!runId && !history,
  });
  const selection = useQuery({
    queryKey: [...key, "candidate", runId, groupId, candidateId],
    queryFn: ({ signal }) => getGroupCandidates(scope, runId!, groupId!, {}, null, signal, candidateId!),
    enabled: active && opened && !!candidateId,
  });
  const candidate = selection.data?.items[0];
  const binding = sources.data?.items.find((item) => item.page_id === candidate?.page_id);
  const fragments = useQueries({
    queries: (active && opened ? candidate?.evidence_ids ?? [] : []).map((id) => ({
      queryKey: [...key, "evidence", runId, candidate!.id, id],
      queryFn: async ({ signal }: { signal: AbortSignal }) => {
        const evidence = await getEvidence(scope, id, signal);
        if (evidence.id !== id || evidence.candidate_id !== candidate!.id || evidence.page_id !== candidate!.page_id) {
          throw new Error("Evidence belongs to a different candidate.");
        }
        return evidence;
      },
      retry: 1,
      staleTime: 0,
      gcTime: 0,
      refetchOnWindowFocus: false,
    })),
  });
  const selectedFragment = params.get("fragment");
  const index = selectedFragment ? candidate?.evidence_ids.indexOf(selectedFragment) ?? -1 : 0;
  const source = fragments[index];
  const pinned = binding && source?.data?.page_image_id === binding.page_image_id ? source.data : null;
  const refresh = () => { if (source) void source.refetch(); };
  return {
    key, statuses, status, explicitRun, runId, history, groupId, opened, candidateId,
    candidate, selection, binding, sources, fragments, selectedFragment, pinned, refresh,
    loading: selection.isFetching || sources.isFetching || !!source?.isFetching,
  };
}

type Browser = ReturnType<typeof useViewerEvidence>;

export function ExtractionEvidencePanel({
  scope, params, browser, update, page, highlighted, canMutate, onReextract,
}: {
  scope: DocumentScope; params: Params; browser: Browser; update: UpdateEvidenceRoute;
  page: number; highlighted: boolean; canMutate: boolean; onReextract: (run: HistoryRun) => void;
}) {
  const tab = browser.history ? "history" : "candidates";
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  return (
    <div className="space-y-3.5">
      <div role="tablist" aria-label="Extraction evidence sections" className={cn(card, "flex gap-1 bg-soft p-1")}>
        {(["candidates", "history"] as const).map((value, index) => (
          <button key={value} id={`evidence-tab-${value}`} type="button" role="tab"
            aria-selected={tab === value} aria-controls="extraction-tab-panel"
            tabIndex={tab === value ? 0 : -1}
            ref={(element) => { buttons.current[index] = element; }}
            className={cn(docButtonClass("tiny"), "flex-1", tab === value && "bg-panel text-accent shadow-xs")}
            onClick={() => update({ evidenceTab: value === "history" ? "history" : null })}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : 1 - index;
              buttons.current[next]?.focus();
              buttons.current[next]?.click();
            }}
          >{value === "candidates" ? "Candidates" : "Run history"}</button>
        ))}
      </div>
      <section id="extraction-tab-panel" role="tabpanel" aria-labelledby={`evidence-tab-${tab}`}>
        {browser.history ? (
          <ExtractionRunHistory scope={scope} runId={browser.explicitRun} update={update}
            canMutate={canMutate} currentProcessingId={browser.status?.processing_run_id} onReextract={onReextract} />
        ) : (
          <CandidateBrowser scope={scope} params={params} browser={browser} update={update}
            page={page} highlighted={highlighted} />
        )}
      </section>
    </div>
  );
}

function CandidateBrowser({ scope, params, browser, update, page, highlighted }: {
  scope: DocumentScope; params: Params; browser: Browser; update: UpdateEvidenceRoute;
  page: number; highlighted: boolean;
}) {
  const { key, runId, groupId, opened, status, statuses } = browser;
  const currentOnly = params.get("pageScope") === "current";
  const returnPage = Number(params.get("returnPage")) || page;
  const mapping = params.get("mapping");
  const kind = params.get("kind");
  const search = params.get("search")?.slice(0, 200) ?? "";
  const selectedPage = browser.sources.data?.items.find((item) => item.page_number === (opened ? returnPage : page));
  const filters: EvidenceFilters = {
    search: search.trim() || undefined,
    page_id: currentOnly ? selectedPage?.page_id : undefined,
    equipment_type: params.get("equipmentType") || undefined,
    mapping_status: mapping === "MAPPED" || mapping === "UNMAPPED" || mapping === "INVALID" ? mapping : undefined,
    kind: kind === "EQUIPMENT" || kind === "ATTRIBUTE" ? kind : undefined,
  };
  const cursor = params.get(opened ? "memberCursor" : "groupCursor");
  const mayList = !!runId && (!currentOnly || !!selectedPage);
  const query = useQuery({
    queryKey: [...key, opened ? "members" : "groups", runId, groupId, filters, cursor],
    queryFn: async ({ signal }) => opened
      ? { members: await getGroupCandidates(scope, runId!, groupId!, filters, cursor, signal) }
      : { groups: await getGroups(scope, runId!, filters, cursor, signal) },
    enabled: mayList,
    refetchInterval: ({ state }) => jobInterval(isRunning(status?.extraction.latest_attempt?.status), state.fetchFailureCount),
  });
  const registry = useQuery({ queryKey: keys.registry, queryFn: getEngineeringRegistry, enabled: !!runId });
  const groups = query.data?.groups;
  const members = query.data?.members;
  const selected = browser.candidate;
  const items = members?.items ?? [];
  const candidates = selected && !items.some((item) => item.id === selected.id) ? [selected, ...items] : items;
  const identification = members?.identification;
  const filter = (patch: Patch) => update({ ...patch, groupCursor: null, memberCursor: null }, "replace");

  function pick(candidate: Candidate) {
    const nextPage = browser.sources.data?.items.find((item) => item.page_id === candidate.page_id);
    update({
      extractionRun: runId, candidate: browser.candidateId === candidate.id ? null : candidate.id,
      fragment: null, page: nextPage?.page_number ?? page,
    });
  }

  return (
    <div className="space-y-3">
      {opened ? (
        <button type="button" className={docButtonClass("ghost", "tiny")} onClick={() => update({
          equipmentGroup: null, candidate: null, fragment: null, memberCursor: null, page: returnPage, returnPage: null,
        })}><ArrowLeft aria-hidden /> Back to source groups</button>
      ) : <h3 className="text-workspace-label font-bold text-ink">Source groups</h3>}
      {runId && (
        <div className="flex flex-wrap items-center justify-between gap-2 text-workspace-caption text-muted">
          <span title={runId}>Run {runId.slice(0, 8)}</span>
          {browser.explicitRun && <button type="button" className="text-accent hover:underline" onClick={() => update({
            extractionRun: null, equipmentGroup: null, candidate: null, fragment: null, groupCursor: null, memberCursor: null,
          })}>View latest results</button>}
        </div>
      )}
      {statuses.error && <PanelMessage error retry={() => void statuses.refetch()}>{apiErrorOf(statuses.error).detail}</PanelMessage>}
      {!runId && !statuses.isPending && <PanelMessage>No published candidates. Check run history for extraction progress.</PanelMessage>}
      {runId && (
        <div className="grid grid-cols-2 gap-2">
          <GroupSearch key={runId} value={search} onCommit={(value) => filter({ search: value || null })} />
          <Select aria-label="Page scope" presentation="workspace" size="sm" value={currentOnly ? "current" : "all"}
            onValueChange={(value) => filter({ pageScope: value === "current" ? "current" : null })}>
            <option value="all">All pages</option><option value="current">Current page</option>
          </Select>
          <Select aria-label="Equipment type" presentation="workspace" size="sm" value={filters.equipment_type ?? "all"}
            onValueChange={(value) => filter({ equipmentType: value === "all" ? null : value })}>
            <option value="all">All equipment types</option>
            {registry.data?.equipment_types.map((item) => <option key={item.key} value={item.key}>{item.display_name}</option>)}
          </Select>
          <Select aria-label="Mapping status" presentation="workspace" size="sm" value={filters.mapping_status ?? "all"}
            onValueChange={(value) => filter({ mapping: value === "all" ? null : value })}>
            <option value="all">All mapping states</option><option value="MAPPED">Mapped</option>
            <option value="UNMAPPED">Unmapped</option><option value="INVALID">Invalid</option>
          </Select>
          <Select aria-label="Observation type" presentation="workspace" size="sm" value={filters.kind ?? "all"}
            onValueChange={(value) => filter({ kind: value === "all" ? null : value })}>
            <option value="all">All observations</option><option value="EQUIPMENT">Equipment</option>
            <option value="ATTRIBUTE">Attributes</option>
          </Select>
        </div>
      )}
      {currentOnly && !mayList && runId && browser.sources.isSuccess && <PanelMessage>This page is outside the selected run.</PanelMessage>}
      {mayList && query.isPending && <p role="status" className="text-workspace-caption text-muted">Loading candidates…</p>}
      {query.error && <PanelMessage error retry={() => void query.refetch()}>{apiErrorOf(query.error).detail}</PanelMessage>}
      {members && <h3 className="break-words text-workspace-label font-bold text-ink">{members.group.label}</h3>}
      {query.data && !candidates.length && !groups?.items.length && <PanelMessage>No candidates match these filters.</PanelMessage>}
      {groups?.items.map((group) => (
        <button key={group.group_id} type="button" className={cn(card, "flex w-full items-center justify-between gap-2 p-3 text-left hover:bg-soft focus-visible:ring-2 focus-visible:ring-ring")}
          onClick={() => update({ extractionRun: runId, equipmentGroup: group.group_id, returnPage: page, candidate: null, fragment: null, memberCursor: null })}>
          <span className="min-w-0">
            <strong className="block break-words text-workspace-label text-ink">{group.label}</strong>
            <span className="block text-workspace-caption text-muted">
              Page {group.page_numbers.join(", ")} · {group.matching_attribute_count} attributes
            </span>
            {group.source_description && <span className="block truncate text-workspace-caption text-muted" title={group.source_description}>{group.source_description}</span>}
          </span>
          <ChevronRight aria-hidden className="size-4 shrink-0 text-muted" />
        </button>
      ))}
      {browser.selection.error && <PanelMessage error retry={() => void browser.selection.refetch()}>The selected candidate is unavailable.</PanelMessage>}
      {identification && <section aria-label="Equipment identification" className="space-y-2">
        <h3 className="text-workspace-label font-bold text-ink">Equipment identification</h3>
        <CandidateCard candidate={identification} expanded={identification.id === browser.candidateId}
          browser={browser} highlighted={highlighted} onSelect={() => pick(identification)}
          onRelated={(id) => update({ candidate: id, fragment: null })}
          onLocate={(id) => update({ fragment: id, page: browser.binding?.page_number ?? page })} />
      </section>}
      {[false, true].map((unsupported) => {
        const items = candidates.filter((candidate) => candidate.kind === "ATTRIBUTE"
          && candidate.raw_unmapped === unsupported && !candidate.redundant_with_id);
        if (!items.length) return null;
        return (
          <section key={String(unsupported)} aria-label={unsupported ? "Unmapped source attributes" : "Registry attributes"} className="space-y-2">
            <h3 className="text-workspace-label font-bold text-ink">{unsupported ? "Unmapped source attributes" : "Registry attributes"}</h3>
            {items.map((candidate) => (
              <CandidateCard key={candidate.id} candidate={candidate} expanded={candidate.id === browser.candidateId}
                browser={browser} highlighted={highlighted} onSelect={() => pick(candidate)}
                onRelated={(id) => update({ candidate: id, fragment: null })}
                onLocate={(id) => update({ fragment: id, page: browser.binding?.page_number ?? page })} />
            ))}
          </section>
        );
      })}
      {candidates.some((candidate) => candidate.kind === "ATTRIBUTE" && candidate.redundant_with_id) && (
        <details className="space-y-2" open={selected?.kind === "ATTRIBUTE" && !!selected.redundant_with_id}>
          <summary className="cursor-pointer text-workspace-caption text-muted">Possible repeated assertions</summary>
          <p className="text-workspace-caption text-muted">Original assertions are retained in the attribute count and history. Review differing qualifiers and source context.</p>
          {candidates.filter((candidate) => candidate.kind === "ATTRIBUTE" && candidate.redundant_with_id).map((candidate) => (
            <CandidateCard key={candidate.id} candidate={candidate} expanded={candidate.id === browser.candidateId}
              browser={browser} highlighted={highlighted} onSelect={() => pick(candidate)}
              onRelated={(id) => update({ candidate: id, fragment: null })}
              onLocate={(id) => update({ fragment: id, page: browser.binding?.page_number ?? page })} />
          ))}
        </details>
      )}
      {(groups || members) && <EvidencePagination page={(groups ?? members)!} onChange={(next) => update(
        opened ? { extractionRun: runId, memberCursor: next } : { extractionRun: runId, groupCursor: next },
      )} />}
    </div>
  );
}

function GroupSearch({ value, onCommit }: { value: string; onCommit: (value: string) => void }) {
  const [draft, setDraft] = useState(value);
  const last = useRef(value);
  const callback = useRef(onCommit);
  callback.current = onCommit;
  useEffect(() => {
    if (value === last.current) return;
    last.current = value;
    setDraft(value);
  }, [value]);
  useEffect(() => {
    if (draft === last.current) return;
    const delay = setTimeout(() => {
      last.current = draft;
      callback.current(draft);
    }, 240);
    return () => clearTimeout(delay);
  }, [draft]);
  return (
    <input type="search" aria-label="Search source groups" placeholder="Search tag, attribute or value…"
      value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={200}
      className="col-span-2 h-[38px] min-w-0 rounded-[var(--pf-radius-control)] border border-border bg-panel px-3 text-workspace-caption text-ink focus-visible:ring-2 focus-visible:ring-ring" />
  );
}

const mappingTones = { MAPPED: "green", UNMAPPED: "yellow", INVALID: "red" } as const satisfies Record<MappingStatus, string>;

function CandidateCard({ candidate, expanded, browser, highlighted, onSelect, onLocate, onRelated }: {
  candidate: Candidate; expanded: boolean; browser: Browser; highlighted: boolean;
  onSelect: () => void; onLocate: (id: string) => void; onRelated: (id: string) => void;
}) {
  const attribute = candidate.kind === "ATTRIBUTE" ? candidate : null;
  const inferred = attribute?.origin === "INFERRED";
  const title = candidate.kind === "EQUIPMENT"
    ? candidate.display_name
    : candidate.attribute_display_name ?? (candidate.raw_unmapped ? candidate.source_display_label ?? "Unmapped source attribute" : candidate.proposed_attribute_key) ?? "Source attribute";
  const displayedValue = attribute?.normalized?.value ?? (inferred ? attribute?.proposed_value : attribute?.raw_value);
  const displayedUnit = attribute?.normalized ? attribute.normalized.unit : inferred ? attribute?.proposed_unit : attribute?.raw_unit;
  return (
    <article className={card}>
      <button type="button" aria-expanded={expanded} onClick={onSelect}
        className="flex w-full items-start justify-between gap-2 p-3 text-left text-workspace-label text-ink hover:bg-soft">
        <span className="min-w-0 break-words">
          <strong className="block">{title}</strong>
          {attribute && <span className="block text-workspace-caption text-muted">
            {displayedValue != null && `${String(displayedValue)}${displayedUnit ? ` ${displayedUnit}` : ""} · `}
            {inferred ? "Inferred" : "Extracted"}
          </span>}
        </span>
        <StatusChip tone={mappingTones[candidate.mapping_status]}>{readableKey(candidate.mapping_status)}</StatusChip>
      </button>
      {expanded && (
        <div className="space-y-2 border-t border-border p-3 text-workspace-caption text-muted">
          {candidate.kind === "EQUIPMENT" && <>
            <p className="break-words text-ink">{candidate.source_description}</p>
            <p>{candidate.registry_type ? readableKey(candidate.registry_type) : "Unknown equipment type"} · {readableKey(candidate.qualification)}</p>
            <p>Tag {readableKey(candidate.tag_state).toLowerCase()}{candidate.raw_qualification && ` · ${candidate.raw_qualification}`}</p>
          </>}
          {attribute && <>
            {inferred ? <>
              <p className="break-words text-ink">Proposed value <strong>{attribute.proposed_value}{attribute.proposed_unit && ` ${attribute.proposed_unit}`}</strong></p>
              <p className="break-words">Inference explanation <strong>{attribute.inference_explanation}</strong></p>
              <p>Basis <strong>{attribute.inference_basis ? readableKey(attribute.inference_basis) : "Unspecified"}</strong></p>
              {attribute.source_expression && <p>Original source expression <strong>{attribute.source_expression}</strong></p>}
              <p>Inferred value. Supporting references provide context. Review the inference and equipment association.</p>
            </> : <>
              {attribute.raw_label && <p>Original PDF label <strong>{attribute.raw_label}</strong></p>}
              <p className="break-words text-ink">Raw value <strong>{attribute.raw_value}</strong></p>
              {attribute.raw_unit && <p>Source unit <strong>{attribute.raw_unit}</strong></p>}
              {attribute.proposed_unit && <p>Proposed source unit <strong>{attribute.proposed_unit}</strong></p>}
              <p>{valueSourceSupportLabel[attribute.value_source_support]}</p>
              {attribute.value_form && attribute.value_form !== "SINGLE" && <p>Source form: {readableKey(attribute.value_form)}</p>}
              {!!attribute.qualifiers.length && <p className="break-words">Qualifiers: {attribute.qualifiers.join(", ")}</p>}
              <p>Review equipment association and interpretation separately from the cited text.</p>
            </>}
            <p>Equipment association <strong>{readableKey(attribute.association)}</strong></p>
            {attribute.proposed_attribute_key && <p>Registry proposal: {readableKey(attribute.proposed_attribute_key)}</p>}
            {attribute.proposed_enum_value && <p>Proposed enum: {attribute.proposed_enum_value}</p>}
            {attribute.normalized && <p>Normalized: {String(attribute.normalized.value)}{attribute.normalized.unit && ` ${attribute.normalized.unit}`}</p>}
            {attribute.raw_unmapped && <p>Unsupported source attribute</p>}
            {attribute.raw_unmapped && attribute.source_display_label && <p>Title is a presentation label. The original PDF label is preserved above.</p>}
            {attribute.redundant_with_id && <button type="button" className={docButtonClass("ghost", "tiny")}
              onClick={() => onRelated(attribute.redundant_with_id!)}>View related assertion</button>}
          </>}
          {candidate.reason_code && <p>{readableKey(candidate.reason_code)}</p>}
          {candidate.conflict && <p className="text-warning">Conflicting candidate values</p>}
          {!!candidate.evidence_ids.length && <ol className="m-0 list-none space-y-2 p-0" aria-label={inferred ? "Inference context references" : "Evidence fragments"}>
            {candidate.evidence_ids.map((id, index) => {
              const result = browser.fragments[index];
              return (
                <li key={id} className={cn(card, "p-2")}>
                  {result?.data ? <EvidenceFragment fragment={result.data}
                    active={browser.selectedFragment ? browser.selectedFragment === id : index === 0}
                    highlighted={highlighted} locate={() => onLocate(id)} />
                    : result?.error ? <PanelMessage error retry={() => void result.refetch()}>Pinned source unavailable.</PanelMessage>
                    : <p role="status">Loading evidence…</p>}
                </li>
              );
            })}
          </ol>}
        </div>
      )}
    </article>
  );
}

function EvidenceFragment({ fragment, active, highlighted, locate }: {
  fragment: EvidenceDetail; active: boolean; highlighted: boolean; locate: () => void;
}) {
  const label = fragment.localization === "VISUAL_REPORTED" ? "Approximate visual region"
    : fragment.localization === "UNRESOLVED" ? "Unresolved · page context"
    : fragment.regions.length ? `${readableKey(fragment.modality)} · source coordinates` : "Source text · no coordinates";
  return (
    <>
      <strong>{readableKey(fragment.role)} · {label}</strong>
      {fragment.localization === "RESOLVED" && <>
        <p className="break-words text-ink">{fragment.quote}</p>
        {fragment.source_issues.length > 0 && <p>{fragment.source_issues.map(readableKey).join(" · ")}</p>}
      </>}
      {fragment.localization === "VISUAL_REPORTED" && fragment.reported_text && <p>{fragment.reported_text}</p>}
      {fragment.localization === "UNRESOLVED" && <p>{readableKey(fragment.reason_code)}</p>}
      <button type="button" aria-pressed={active} onClick={locate} className={docButtonClass("ghost", "tiny")}>
        {active && highlighted ? "Showing source region" : "Show on pinned page"}
      </button>
    </>
  );
}
