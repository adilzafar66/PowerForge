"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";

import { FileIcon } from "@/components/document-list";
import { docButtonClass, DocumentsDialog, StatusChip } from "@/components/documents-ui";
import { AsyncState } from "@/components/ui/async-state";
import { apiErrorOf } from "@/lib/api";
import { families, familyLabel, type RunFamily } from "@/lib/extraction";
import {
  getOperationSources,
  pageRanges,
  parseExtractionPages,
  previewExtractionOperation,
  startExtractionOperation,
  type ExtractionMode,
  type OperationPreview,
  type OperationSelection,
  type RevisionScope,
  type SkippedSource,
  type SourceOption,
} from "@/lib/extraction-operations";
import { keys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";

const panel = "rounded-[var(--pf-radius-lg)] border border-border";
const callout = cn(panel, "bg-selection/45 p-3.5 text-workspace-caption leading-relaxed text-muted");
const field = "h-9 w-full rounded-[var(--pf-radius-control)] border border-border bg-panel px-2.5 text-workspace-label text-ink focus-visible:outline-2 focus-visible:outline-ring";
const labels: Record<RunFamily, string> = {
  engineering: "Extract from engineering text",
  tables: "Extract from tables and schedules",
};

type Draft = { pages?: string; ocr?: string };
type SourceDraft = {
  source: SourceOption;
  pagesText: string;
  ocrText: string;
  pages: number[];
  forceOcrPages: number[];
  sourceError?: string;
  ocrError?: string;
};

export type WizardLaunch = {
  documentIds: string[];
  skipped?: SkippedSource[];
  mode?: ExtractionMode;
  sourceVersion?: string;
  initialPages?: string;
};

export function StartExtractionWizard({
  scope, launch, onClose, onStarted,
}: {
  scope: RevisionScope;
  launch: WizardLaunch;
  onClose: () => void;
  onStarted: (id: string, documentId: string) => void;
}) {
  const instance = useId();
  const title = launch.mode === "reextract" ? "Re-extract" : "Start extraction";
  const [step, setStep] = useState(1);
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const [selectedFamilies, setSelectedFamilies] = useState<RunFamily[]>([...families]);
  const [acceptedHash, setAcceptedHash] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const submission = useRef<{ hash: string; key: string } | null>(null);
  const submitting = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);
  const tooMany = launch.documentIds.length > 50;
  const base = keys.extraction(scope.projectId, scope.revisionId);
  const sources = useQuery({
    queryKey: [...base, "wizard-sources", instance, launch.documentIds],
    queryFn: ({ signal }) => getOperationSources(scope, launch.documentIds, signal),
    enabled: !tooMany,
    refetchOnWindowFocus: false,
    retry: 1,
  });

  const options = sources.data;
  const perDocumentLimit = options?.max_pages_per_document ?? 50;
  const draftRows = (options?.items ?? []).map((source): SourceDraft => {
    const input = drafts[source.revision_document_id] ?? {};
    const defaultPages = source.page_count && source.page_count <= perDocumentLimit
      ? pageRanges(Array.from({ length: source.page_count }, (_, index) => index + 1))
      : "";
    const pagesText = input.pages ?? launch.initialPages ?? defaultPages;
    const ocrText = input.ocr ?? "";
    const pages = parseExtractionPages(pagesText, source.available_pages, perDocumentLimit);
    const ocr = ocrText.trim()
      ? parseExtractionPages(ocrText, pages.pages ?? [], perDocumentLimit)
      : { pages: [] };
    return {
      source, pagesText, ocrText, pages: pages.pages ?? [], forceOcrPages: ocr.pages ?? [],
      sourceError: source.error
        ?? (launch.sourceVersion && source.processing_run_id !== launch.sourceVersion
          ? "This processing version changed. Start a new review from Documents."
          : pages.error),
      ocrError: ocr.error,
    };
  });
  const totalPages = draftRows.reduce((total, row) => total + row.pages.length, 0);
  const limitError = options && (options.read_only ? "This revision is read-only."
    : launch.documentIds.length > options.max_documents ? `Select at most ${options.max_documents} documents per operation.`
      : totalPages > options.max_pages ? `Select at most ${options.max_pages} pages per operation.` : null);
  const validSources = !!options && draftRows.length === launch.documentIds.length
    && draftRows.length > 0 && !limitError && draftRows.every((row) => !row.sourceError);
  const selection: OperationSelection | null = validSources && draftRows.every((row) => !row.ocrError)
    ? {
      documents: draftRows.map((row) => ({
        revision_document_id: row.source.revision_document_id,
        processing_run_id: row.source.processing_run_id!,
        pages: row.pages,
        force_ocr_pages: row.forceOcrPages,
      })),
      families: selectedFamilies,
      mode: launch.mode ?? "ensure",
    } : null;
  const selectionKey = selection ? JSON.stringify(selection) : null;
  const [reviewKey, setReviewKey] = useState<string | null>(null);
  useEffect(() => {
    if (step < 2 || !selectionKey) return;
    const timer = window.setTimeout(() => setReviewKey(selectionKey), 180);
    return () => window.clearTimeout(timer);
  }, [selectionKey, step]);
  const preview = useQuery({
    queryKey: [...base, "wizard-preview", instance, reviewKey],
    queryFn: ({ signal }) => previewExtractionOperation(scope, JSON.parse(reviewKey!), signal),
    enabled: step >= 2 && !!reviewKey && reviewKey === selectionKey,
    refetchOnWindowFocus: false,
    retry: 1,
  });
  const reviewed = reviewKey === selectionKey ? preview.data : undefined;
  const hash = reviewed?.review_hash;
  const canAdvance = step === 1 ? validSources : !!reviewed
    && !preview.isFetching && !preview.isError && reviewed.items.every((item) => !item.error);
  const authorized = !!hash && acceptedHash === hash;

  useEffect(() => {
    if (step > 1) heading.current?.focus();
  }, [step]);

  function changeDraft(id: string, patch: Draft) {
    setAcceptedHash(null);
    setSubmitError(null);
    setDrafts((current) => ({ ...current, [id]: { ...current[id], ...patch } }));
  }

  function go(next: number) {
    setAcceptedHash(null);
    setSubmitError(null);
    setStep(next);
  }

  function toggleFamily(family: RunFamily) {
    setAcceptedHash(null);
    setSubmitError(null);
    setSelectedFamilies((current) => current.includes(family)
      ? current.length > 1 ? current.filter((key) => key !== family) : current
      : families.filter((key) => key === family || current.includes(key)));
  }

  async function submit() {
    if (!hash || !authorized || !selection || preview.isFetching || preview.isError || submitting.current) return;
    submitting.current = true;
    setSending(true);
    setSubmitError(null);
    try {
      if (submission.current?.hash !== hash) submission.current = { hash, key: crypto.randomUUID() };
      const { id } = await startExtractionOperation(scope, selection, hash, submission.current.key);
      onStarted(id, selection.documents[0].revision_document_id);
    } catch (error) {
      const failure = apiErrorOf(error);
      setSubmitError(failure.detail);
      if (failure.status === 409) {
        setAcceptedHash(null);
        void preview.refetch();
      }
    } finally {
      submitting.current = false;
      setSending(false);
    }
  }

  const comprehensive = selectedFamilies.length === 2;
  const processing = selectedFamilies.map((family) =>
    family === "engineering" ? "engineering text" : "tables and schedules").join(" and ");
  const descriptions = ["Choose source pages", "Automatic source preparation plan", "Confirm preparation and OpenAI extraction"];
  return (
    <DocumentsDialog
      title={title}
      description={`${launch.documentIds.length} selected ${launch.documentIds.length === 1 ? "document" : "documents"} · ${totalPages} selected pages · ${descriptions[step - 1]}`}
      closeLabel="Close extraction wizard"
      restoreFocus
      onClose={() => { if (!sending) onClose(); }}
      className="max-w-[760px] max-sm:max-h-[100dvh] max-sm:w-full max-sm:rounded-none"
      headerExtra={<ExtractionSteps step={step} />}
      footer={
        <div className="flex w-full flex-wrap items-center justify-end gap-2 sm:justify-between">
          <span className="mr-auto text-workspace-caption text-muted">Local preparation precedes OpenAI processing.</span>
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className={docButtonClass()} onClick={onClose} disabled={sending}>Cancel</button>
            {step > 1 && <button type="button" className={docButtonClass()} onClick={() => go(step - 1)} disabled={sending}>Back</button>}
            {step < 3 ? (
              <button type="button" className={docButtonClass("primary")} onClick={() => go(step + 1)} disabled={!canAdvance}>
                {step === 1 ? "Continue to enrichment" : "Continue to extraction"}
              </button>
            ) : (
              <button type="button" className={docButtonClass("primary")} disabled={!authorized || preview.isFetching || preview.isError || sending} onClick={() => void submit()}>
                {sending ? "Submitting…" : title}
              </button>
            )}
          </div>
        </div>
      }
    >
      <div className="space-y-3.5">
        <div>
          <h3 ref={heading} tabIndex={-1} className="m-0 text-workspace-subheading font-bold outline-none">
            {["1. Select source pages", "2. Source enrichment — automatic", "3. Extraction"][step - 1]}
          </h3>
          <p className="m-0 mt-1 text-workspace-label leading-relaxed text-muted">
            {step === 1 ? "Choose the page range for each document. PowerForge pins the processing version you review."
              : step === 2 ? "PowerForge reuses compatible source results and prepares missing native text, OCR and page layout locally after confirmation."
                : "Engineering text and tables or schedules are included by default. Each family has its own run, results, and retries."}
          </p>
        </div>
        {step === 1 && (
          <>
            {tooMany && <WizardError>Select at most 50 documents and review the deployment limits in a smaller selection.</WizardError>}
            {!tooMany && <AsyncState pending={sources.isPending} error={sources.error} retry={sources.refetch} />}
            {limitError && <WizardError>{limitError}</WizardError>}
            {!!draftRows.length && (
              <ul className={cn(panel, "m-0 list-none divide-y divide-border p-0")}>
                {draftRows.map((row) => (
                  <li key={row.source.revision_document_id} className="flex flex-wrap items-start gap-3 p-3.5">
                    <FileIcon />
                    <div className="min-w-0 flex-1">
                      <SourceName source={row.source} />
                      {row.sourceError && (
                        <p id={`source-error-${row.source.revision_document_id}`} className="m-0 mt-1 text-workspace-caption text-danger">
                          {row.sourceError}
                        </p>
                      )}
                    </div>
                    {!row.source.error && (
                      <label className="flex items-center gap-2 text-workspace-caption text-muted max-sm:w-full">
                        Pages
                        <input
                          aria-label={`Pages for ${row.source.filename}`}
                          aria-invalid={!!row.sourceError}
                          aria-describedby={row.sourceError ? `source-error-${row.source.revision_document_id}` : undefined}
                          className={cn(field, "w-32 max-sm:w-full")}
                          value={row.pagesText}
                          placeholder="e.g. 1–3, 5"
                          onChange={(event) => changeDraft(row.source.revision_document_id, { pages: event.target.value })}
                        />
                      </label>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {!!launch.skipped?.length && (
              <details className={cn(panel, "px-3 py-2 text-workspace-caption text-muted")}>
                <summary className="cursor-pointer font-semibold">{launch.skipped.length} skipped in the original selection</summary>
                <ul className="mb-0 pl-5">
                  {launch.skipped.map(({ id, name, reason }) => <li key={id}>{name} · {reason}</li>)}
                </ul>
              </details>
            )}
            <p className={cn(callout, "m-0")}>Each selected document creates its own source-scoped runs. Equipment identity remains unresolved across documents.</p>
          </>
        )}
        {step >= 2 && (
          <AsyncState
            pending={!!selection && !reviewed && !preview.error}
            error={reviewKey === selectionKey ? preview.error : null}
            retry={preview.refetch}
          />
        )}
        {step === 2 && (
          <>
            <ul className={cn(panel, "m-0 list-none divide-y divide-border p-0")}>
              {draftRows.map((row) => {
                const item = reviewed?.items.find((entry) => entry.revision_document_id === row.source.revision_document_id);
                return (
                  <li key={row.source.revision_document_id} className="flex gap-3 p-3.5">
                    <FileIcon />
                    <div className="min-w-0 flex-1 space-y-2">
                      <SourceName source={row.source} />
                      {item?.error ? <WizardError>{item.error}</WizardError>
                        : item ? <Readiness pages={item.pages} /> : null}
                      <details className={cn(panel, "bg-soft/65 px-3 py-2 text-workspace-caption")}>
                        <summary className="cursor-pointer font-semibold text-accent">Advanced OCR override (optional)</summary>
                        <label className="mt-2 block text-muted">
                          Force full-page OCR for selected pages
                          <input
                            aria-label={`Force OCR pages for ${row.source.filename}`}
                            aria-invalid={!!row.ocrError}
                            aria-describedby={row.ocrError ? `ocr-error-${row.source.revision_document_id}` : undefined}
                            className={cn(field, "mt-1")}
                            value={row.ocrText}
                            placeholder="e.g. 2, 4–5"
                            onChange={(event) => changeDraft(row.source.revision_document_id, { ocr: event.target.value })}
                          />
                        </label>
                        {row.ocrError && <p id={`ocr-error-${row.source.revision_document_id}`} className="m-0 mt-1 text-danger">{row.ocrError}</p>}
                      </details>
                    </div>
                  </li>
                );
              })}
            </ul>
            <div className={callout}>
              <strong className="block text-ink">After one confirmation</strong>
              OpenAI extraction waits until every selected page for that document has exact preparation and layout results.
            </div>
          </>
        )}
        {step === 3 && (
          <>
            <div className={cn(callout, "flex items-start gap-3")}>
              <Check aria-hidden className="mt-0.5 size-4 shrink-0 text-positive" />
              <div>
                <strong className="block text-workspace-label text-ink">{comprehensive ? "Comprehensive extraction" : "Targeted extraction"}</strong>
                {comprehensive ? "Engineering text and tables or schedules are included." : `The plan includes only ${processing}.`}
              </div>
            </div>
            <details className={cn(panel, "p-3.5 text-workspace-label")}>
              <summary className="cursor-pointer font-semibold text-accent">Advanced extraction settings</summary>
              <div className="mt-3 space-y-2">
                {families.map((family) => (
                  <label key={family} className="flex items-center gap-2">
                    <input type="checkbox" className="size-4 accent-accent" checked={selectedFamilies.includes(family)}
                      disabled={sending || (selectedFamilies.length === 1 && selectedFamilies.includes(family))}
                      onChange={() => toggleFamily(family)} />
                    {labels[family]}
                  </label>
                ))}
                <p className="m-0 text-workspace-caption text-muted">Select at least one extraction family.</p>
              </div>
            </details>
            {reviewed && <FinalPlan preview={reviewed} totalPages={totalPages} mode={launch.mode ?? "ensure"} />}
            <label className="flex items-start gap-2.5 text-workspace-label leading-relaxed text-ink">
              <input type="checkbox" checked={authorized} disabled={!hash || preview.isFetching || preview.isError || sending}
                className="mt-0.5 size-4 shrink-0 accent-accent"
                onChange={(event) => setAcceptedHash(event.target.checked && hash ? hash : null)} />
              <span>
                I authorize sending the selected source content to OpenAI <strong>after automatic preparation</strong> for {processing}.
                {launch.mode === "reextract" ? " I authorize new extraction runs for the reviewed source." : ""}
                {" "}Extracted observations require engineering verification.
              </span>
            </label>
            {submitError && <WizardError>{submitError}</WizardError>}
          </>
        )}
      </div>
    </DocumentsDialog>
  );
}

function ExtractionSteps({ step }: { step: number }) {
  return (
    <ol aria-label="Extraction steps" className="m-0 flex list-none items-center gap-2 p-0 sm:gap-3">
      {["Source", "Enrichment", "Extraction"].map((name, index) => (
        <li key={name} aria-current={step === index + 1 ? "step" : undefined}
          className="flex min-w-0 items-center gap-1.5 text-workspace-caption font-semibold text-muted not-last:flex-1 not-last:after:ml-1 not-last:after:h-px not-last:after:flex-1 not-last:after:bg-border">
          <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full border border-border bg-panel sm:size-7",
            step === index + 1 && "border-accent bg-accent text-white",
            step > index + 1 && "border-positive/20 bg-positive-tint text-positive")}>
            {step > index + 1 ? <Check aria-hidden className="size-3.5" /> : index + 1}
          </span>
          <span className={cn(step === index + 1 && "text-accent")}>{name}</span>
        </li>
      ))}
    </ol>
  );
}

function SourceName({ source }: { source: SourceOption }) {
  return (
    <div>
      <strong className="block break-words text-workspace-label text-ink">{source.filename ?? "Unavailable source"}</strong>
      {source.processing_run_id && (
        <span className="block text-workspace-caption text-muted" title={source.processing_run_id}>
          {source.available_pages.length} available pages · Processing {source.processing_run_id.slice(0, 8)}
        </span>
      )}
    </div>
  );
}

function Readiness({ pages }: { pages: OperationPreview["items"][number]["pages"] }) {
  const ready = pages.filter((page) => page.reuse_layout).map((page) => page.page_number);
  const layoutOnly = pages.filter((page) => page.reuse_preparation && !page.reuse_layout).map((page) => page.page_number);
  const prepare = pages.filter((page) => !page.reuse_preparation).map((page) => page.page_number);
  return (
    <ul className="m-0 list-none space-y-1 p-0 text-workspace-caption text-muted">
      {!!ready.length && <li><StatusChip tone="green">Reuse existing results</StatusChip> · Pages {pageRanges(ready)}</li>}
      {!!layoutOnly.length && <li><StatusChip tone="blue">Will prepare layout automatically</StatusChip> · Pages {pageRanges(layoutOnly)} reuse preparation</li>}
      {!!prepare.length && <li><StatusChip tone="blue">Will prepare automatically</StatusChip> · Pages {pageRanges(prepare)}</li>}
    </ul>
  );
}

function FinalPlan({ preview, totalPages, mode }: { preview: OperationPreview; totalPages: number; mode: ExtractionMode }) {
  const pages = preview.items.flatMap((item) => item.pages);
  const reused = pages.filter((page) => page.reuse_layout).length;
  return (
    <div className={cn(callout, "space-y-2")}>
      <strong className="block text-ink">Execution plan — starts after one approval</strong>
      <div className="flex flex-wrap gap-1.5">
        {[
          `${preview.items.length} ${preview.items.length === 1 ? "document" : "documents"}`,
          `${totalPages} selected ${totalPages === 1 ? "page" : "pages"}`,
          `${reused} reused pages`, `${pages.length - reused} pages need preparation or layout`,
          `${preview.planned_runs} extraction ${preview.planned_runs === 1 ? "run" : "runs"} requested`,
        ].map((label) => <span key={label} className="rounded-md border border-border bg-panel px-2 py-1 text-ink">{label}</span>)}
      </div>
      <details className="text-workspace-caption">
        <summary className="cursor-pointer font-semibold text-accent">Reviewed source pages</summary>
        <ul className="mt-1 mb-0 space-y-1 pl-4">
          {preview.items.filter((item) => item.pages.length > 0).map((item) => (
            <li key={item.revision_document_id} className="break-words">
              {item.filename} · Pages {pageRanges(item.pages.map((page) => page.page_number))}
              {item.pages.some((page) => page.force_ocr) && (
                <> · Force OCR {pageRanges(item.pages.filter((page) => page.force_ocr).map((page) => page.page_number))}</>
              )}
            </li>
          ))}
        </ul>
      </details>
      <ul className="m-0 list-none space-y-1 p-0">
        {preview.profiles.map((profile) => (
          <li key={profile.key} className="break-words">
            <strong>{familyLabel[profile.family]}</strong> · OpenAI · {profile.model} · {profile.key} · {profile.enabled ? "Enabled by deployment" : "Unavailable"}
          </li>
        ))}
      </ul>
      {preview.provider_admissions !== null && (
        <p className="m-0">Maximum {preview.provider_admissions} provider admissions, {preview.ocr_attempts} OCR attempts, and {preview.parallel_documents} documents in parallel.</p>
      )}
      <p className="m-0">Local preparation and layout run first. OpenAI processing may incur charges. <strong>Estimated cost is unknown.</strong>
        {mode === "ensure" ? " Compatible existing extraction runs may be reused." : " Re-extraction can create new provider runs."}
      </p>
      {preview.errors.map((error) => <WizardError key={error}>{error}</WizardError>)}
      {preview.items.filter((item) => item.error).map((item) => (
        <WizardError key={item.revision_document_id}>{item.filename ?? "Source"} · {item.error}</WizardError>
      ))}
    </div>
  );
}

function WizardError({ children }: { children: React.ReactNode }) {
  return <p role="alert" className="m-0 text-workspace-caption text-danger">{children}</p>;
}
