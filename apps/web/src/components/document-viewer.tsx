"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Suspense,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronLeft,
  ChevronRight,
  Download,
  ExternalLink,
  FileText,
  Minus,
  PanelLeft,
  PanelRight,
  Plus,
  RotateCcw,
} from "lucide-react";

import { AppShell } from "@/components/app-shell";
import {
  ExtractionEvidencePanel,
  useViewerEvidence,
  type UpdateEvidenceRoute,
} from "@/components/extraction-evidence-panel";
import { useOriginalFile } from "@/components/document-actions";
import {
  docButtonClass,
  Overline,
  ProgressBar,
  StatusChip,
} from "@/components/documents-ui";
import { AsyncState } from "@/components/ui/async-state";
import { apiErrorOf } from "@/lib/api";
import {
  canOpenInline,
  documentTypeLabel,
  getDocument,
  getPageArtifactUrl,
  getProcessing,
  listClassificationPages,
  listPages,
  retryProcessing,
  type DocumentPage,
  type PageArtifactType,
  type ProcessingSummary,
  type RevisionDocument,
} from "@/lib/documents";
import { evidenceArtifactUrl, type EvidenceDetail } from "@/lib/extraction";
import { classificationCell } from "@/lib/document-presentation";
import {
  getProject,
  getRevision,
  listRevisions,
  type Project,
  type Revision,
} from "@/lib/projects";
import { isRunning, jobInterval } from "@/lib/query-hooks";
import { keys } from "@/lib/query-keys";
import { cn } from "@/lib/utils";
import {
  documentViewerHref,
  revisionHref,
  type ViewerMode,
} from "@/lib/workspace-navigation";

const ZOOM_MIN = 0.3;
const ZOOM_MAX = 2.8;
const ZOOM_STEP = 0.15;
const FIT_MIN = 0.34;
const FIT_MAX = 1.8;
const DEFAULT_PAGE = { width: 850, height: 1100 };

type Zoom = number | "page" | "width";

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

/** Layout height of the shell top bar; unlike the scroll offset it does not change while scrolling. */
function useShellHeaderHeight() {
  const [height, setHeight] = useState(66);
  useEffect(() => {
    const main = document.getElementById("main-content");
    if (!main) return;
    const measure = () => setHeight(main.offsetTop);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);
  return height;
}

export function DocumentViewerPage({
  initialProject,
  initialRevision,
  initialRevisions,
  documentId,
}: {
  initialProject: Project;
  initialRevision: Revision;
  initialRevisions: Revision[];
  documentId: string;
}) {
  const p = initialProject.id;
  const r = initialRevision.id;
  const pq = useQuery({
    queryKey: keys.project(p),
    queryFn: () => getProject(p),
    initialData: initialProject,
  });
  const rq = useQuery({
    queryKey: keys.revision(p, r),
    queryFn: () => getRevision(p, r),
    initialData: initialRevision,
  });
  const rs = useQuery({
    queryKey: keys.revisions(p),
    queryFn: () => listRevisions(p),
    initialData: initialRevisions,
  });
  const docQuery = useQuery({
    queryKey: [...keys.document(p, r, documentId), "record"],
    queryFn: () => getDocument(p, r, documentId),
    refetchInterval: (query) =>
      jobInterval(
        isRunning(query.state.data?.processing?.status) ||
          isRunning(query.state.data?.classification.attempt?.status),
        query.state.fetchFailureCount,
      ),
  });
  const project = pq.data;
  const revision = rq.data;
  const row = docQuery.data ?? null;
  const filename = row?.document.original_filename;
  const shellDocument = useMemo(
    () => (filename ? { id: documentId, name: filename } : undefined),
    [documentId, filename],
  );
  const headerHeight = useShellHeaderHeight();
  const documentsHref = revisionHref(p, r, r, "", "documents");
  const missing =
    !row && apiErrorOf(docQuery.error).status === 404 && !!docQuery.error;

  return (
    <AppShell
      project={project}
      revision={revision}
      revisions={rs.data}
      document={shellDocument}
    >
      <div
        className="flex min-h-[560px] w-full min-w-0 flex-col text-ink"
        style={{ height: `calc(100dvh - ${headerHeight}px)` }}
      >
        {row ? (
          <Suspense fallback={null}>
            <DocumentViewer
              projectId={p}
              revision={revision}
              row={row}
            />
          </Suspense>
        ) : missing ? (
          <ViewerNotice
            title="Document not found"
            className="m-auto"
            action={
              <Link href={documentsHref} className={docButtonClass()}>
                Back to documents
              </Link>
            }
          >
            This document is not part of revision {revision.identifier}.
          </ViewerNotice>
        ) : (
          <div className="px-[29px] py-6">
            <AsyncState
              pending={docQuery.isPending}
              error={docQuery.error}
              retry={docQuery.refetch}
            />
          </div>
        )}
      </div>
    </AppShell>
  );
}

function processingLabel(processing: ProcessingSummary | null): string {
  switch (processing?.status) {
    case "COMPLETED":
      return "Processed";
    case "RUNNING":
      return "Processing";
    case "PENDING":
      return "Waiting to process";
    case "FAILED":
      return "Processing failed";
    default:
      return "Not processed";
  }
}

function artifact(page: DocumentPage | null, type: PageArtifactType) {
  return page?.artifacts.find((item) => item.artifact_type === type) ?? null;
}

/** Page size in CSS pixels at 100%. The analysis image supplies the aspect ratio when present. */
function pageSize(page: DocumentPage | null) {
  if (!page) return DEFAULT_PAGE;
  const unit = page.source_unit === "POINTS" ? 4 / 3 : 1;
  let width = Number(page.source_width) * unit;
  let height = Number(page.source_height) * unit;
  if (!(width > 0 && height > 0)) return DEFAULT_PAGE;
  if (page.rotation_degrees % 180 !== 0) [width, height] = [height, width];
  const image = artifact(page, "ANALYSIS_IMAGE");
  if (image?.width_px && image.height_px) {
    height = (width * image.height_px) / image.width_px;
  }
  return { width, height };
}

function textSource(page: DocumentPage | null) {
  if (!page) return null;
  return page.native_text_char_count > 0 ? "Native text" : "No text layer";
}

export function DocumentViewer({
  projectId,
  revision,
  row,
}: {
  projectId: string;
  revision: Revision;
  row: RevisionDocument;
}) {
  const router = useRouter();
  const params = useSearchParams();
  const queryClient = useQueryClient();
  const revisionId = revision.id;
  const docKey = keys.document(projectId, revisionId, row.id);
  const mode: ViewerMode =
    params.get("mode") === "evidence" ? "evidence" : "document";
  const requestedPage = Math.max(
    1,
    Number.parseInt(params.get("page") ?? "1", 10) || 1,
  );
  const scope = { projectId, revisionId, documentId: row.id };
  const browser = useViewerEvidence(scope, params, mode === "evidence" && row.status === "INCLUDED");
  const pinned = mode === "evidence" && !browser.history && browser.source.data?.page_number === requestedPage
    ? browser.source.data
    : null;
  const pinnedUrl = evidenceArtifactUrl(pinned?.source_image_url ?? null);
  const pinnedRequired = mode === "evidence" && !browser.history && (
    browser.citation?.source_page_number === requestedPage || !!pinned
  );
  const [loadedPinnedUrl, setLoadedPinnedUrl] = useState<string | null>(null);
  const pinnedRegion = useMemo(() => pinned ? evidenceRegionStyle(pinned) : null, [pinned]);

  const processing = row.processing;
  const complete = processing?.status === "COMPLETED";

  const pagesQuery = useQuery({
    queryKey: [...docKey, "pages"],
    queryFn: () => listPages(projectId, revisionId, row.id),
    enabled: complete,
    retry: (count, error) => apiErrorOf(error).status !== 409 && count < 2,
  });
  const pages = complete ? (pagesQuery.data ?? null) : null;
  const page =
    pages?.find((item) => item.page_number === requestedPage) ??
    (pages && requestedPage > pages.length ? pages[pages.length - 1] : null) ??
    pages?.[0] ??
    null;
  const pageIndex = page && pages ? pages.indexOf(page) : -1;
  const pageCount = pages?.length ?? processing?.pages_total ?? null;

  const mixed =
    row.document_type === "MIXED_DOCUMENT" ||
    row.classification.suggestion?.predicted_type === "MIXED_DOCUMENT";
  const pageTypes = useQuery({
    queryKey: [...docKey, "classification-pages"],
    queryFn: () => listClassificationPages(projectId, revisionId, row.id),
    enabled: mixed && complete,
  });
  const pageType = page
    ? pageTypes.data?.find((item) => item.page_number === page.page_number)
        ?.predicted_type
    : undefined;

  const processingInfo = useQuery({
    queryKey: [...docKey, "processing"],
    queryFn: () => getProcessing(projectId, revisionId, row.id),
    enabled: processing !== null,
  });

  const [thumbsOpen, setThumbsOpen] = useState(true);
  const [panelOpen, setPanelOpen] = useState(true);
  const openEvidenceInitially = useRef(mode === "evidence");
  useEffect(() => {
    if (window.matchMedia?.("(max-width: 800px)").matches && !openEvidenceInitially.current) setPanelOpen(false);
  }, []);

  const [zoom, setZoom] = useState<Zoom>("page");
  const [canvas, setCanvas] = useState({ width: 0, height: 0 });
  const scrollRef = useRef<HTMLDivElement>(null);
  const panelScrollRef = useRef<HTMLDivElement>(null);
  const baseSize = pageSize(page);
  const size = pinnedUrl && pinned?.source_image_width_px && pinned.source_image_height_px
    ? { width: baseSize.width, height: baseSize.width * pinned.source_image_height_px / pinned.source_image_width_px }
    : baseSize;
  const hasPageImage = !!(page || pinnedRequired);
  const fitPage = clamp(
    Math.min((canvas.width - 64) / size.width, (canvas.height - 56) / size.height),
    FIT_MIN,
    FIT_MAX,
  );
  const fitWidth = clamp((canvas.width - 70) / size.width, FIT_MIN, FIT_MAX);
  const scale = zoom === "page" ? fitPage : zoom === "width" ? fitWidth : zoom;

  const updateEvidenceRoute: UpdateEvidenceRoute = (patch, method = "push") => {
    const query = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(patch)) {
      if (value == null || (key === "page" && value === 1) || (key === "mode" && value === "document")) {
        query.delete(key);
      } else {
        query.set(key, String(value));
      }
    }
    const base = documentViewerHref(projectId, revisionId, row.id);
    router[method](query.size ? `${base}?${query}` : base, { scroll: false });
  };
  function go(next: { page?: number; mode?: ViewerMode }) {
    if (next.mode === "evidence") setPanelOpen(true);
    updateEvidenceRoute({
      page: next.page ?? page?.page_number ?? requestedPage,
      mode: next.mode ?? mode,
      ...(next.page && !browser.opened && params.get("pageScope") === "current" ? { groupOffset: null } : {}),
    }, "replace");
  }
  function step(delta: number) {
    if (!pages || pageIndex < 0) return;
    const next = pages[pageIndex + delta];
    if (next) go({ page: next.page_number });
  }
  function zoomBy(direction: 1 | -1) {
    setZoom(
      clamp(
        Math.round((scale + direction * ZOOM_STEP) * 100) / 100,
        ZOOM_MIN,
        ZOOM_MAX,
      ),
    );
  }

  const keyHandler = useRef<(event: KeyboardEvent) => void>(() => {});
  keyHandler.current = (event) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey)
      return;
    const target = event.target as HTMLElement | null;
    if (
      target?.closest?.(
        "input, textarea, select, [contenteditable='true'], [role='menu'], [role='listbox'], [role='dialog']",
      )
    )
      return;
    if (!hasPageImage) return;
    if (event.key === "+" || event.key === "=") {
      event.preventDefault();
      zoomBy(1);
    } else if (event.key === "-" || event.key === "_") {
      event.preventDefault();
      zoomBy(-1);
    } else if (event.key === "ArrowRight") {
      event.preventDefault();
      step(1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      step(-1);
    }
  };
  useEffect(() => {
    const listener = (event: KeyboardEvent) => keyHandler.current(event);
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, []);

  useEffect(() => {
    const element = scrollRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => {
      const { width, height } = entry.contentRect;
      setCanvas({ width, height });
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, [hasPageImage]);

  const pageId = page?.id;
  useEffect(() => {
    scrollRef.current?.scrollTo?.({ top: 0, left: 0 });
  }, [pageId, pinned?.id]);

  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(
    null,
  );
  const [panning, setPanning] = useState(false);
  function startPan(event: ReactPointerEvent<HTMLDivElement>) {
    if (event.pointerType !== "mouse" || event.button !== 0) return;
    const element = event.currentTarget;
    drag.current = {
      x: event.clientX,
      y: event.clientY,
      left: element.scrollLeft,
      top: element.scrollTop,
    };
    element.setPointerCapture?.(event.pointerId);
    setPanning(true);
  }
  function movePan(event: ReactPointerEvent<HTMLDivElement>) {
    const start = drag.current;
    if (!start) return;
    event.currentTarget.scrollLeft = start.left - (event.clientX - start.x);
    event.currentTarget.scrollTop = start.top - (event.clientY - start.y);
  }
  function endPan() {
    drag.current = null;
    setPanning(false);
  }

  const [retryingProcessing, setRetryingProcessing] = useState(false);
  const [processingError, setProcessingError] = useState<string | null>(null);
  async function retry() {
    setRetryingProcessing(true);
    setProcessingError(null);
    try {
      await retryProcessing(projectId, revisionId, row.id);
      await queryClient.invalidateQueries({ queryKey: docKey });
    } catch (error) {
      setProcessingError(apiErrorOf(error).detail);
    } finally {
      setRetryingProcessing(false);
    }
  }

  const file = row.document;
  const title = row.document_number
    ? `${row.document_number} — ${file.original_filename}`
    : file.original_filename;
  const subtitle = [
    pageCount != null
      ? `${pageCount} ${pageCount === 1 ? "page" : "pages"}`
      : null,
    file.file_extension.replace(/^\./, "").toUpperCase(),
    processingLabel(processing),
  ]
    .filter(Boolean)
    .join(" · ");
  const pageLabel = pinnedUrl && pinned
    ? `Page ${pinned.page_number} · Pinned source`
    : page
    ? [`Page ${page.page_number}`, pageType ? documentTypeLabel(pageType) : null, textSource(page)]
        .filter(Boolean)
        .join(" · ")
    : null;

  return (
    <>
      <header className="shrink-0 border-b border-border bg-panel px-[29px] pt-[21px] pb-[18px] max-[1250px]:px-5 max-[1250px]:py-4 max-[800px]:p-[13px]">
        <Overline as="p" className="mb-1.5">
          Revision documents / Document viewer
        </Overline>
        <div className="flex items-center justify-between gap-4 max-[1250px]:flex-col max-[1250px]:items-start max-[1250px]:gap-3">
          <div className="min-w-0">
            <h1 className="m-0 mb-[5px] text-workspace-title leading-[1.2] font-bold tracking-[-0.75px] break-words max-[800px]:text-workspace-editor">
              {title}
            </h1>
            <p className="m-0 flex flex-wrap items-center gap-x-2 gap-y-1 text-workspace-caption leading-[1.4] text-muted">
              {subtitle}
              {row.status === "REMOVED" ? (
                <StatusChip tone="gray">Removed from revision</StatusChip>
              ) : null}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-[9px] max-[1050px]:gap-1">
            <div
              role="group"
              aria-label="Viewer mode"
              className="flex w-max gap-[3px] rounded-[var(--pf-radius-control)] bg-soft p-[3px]"
            >
              {(
                [
                  ["document", "Document"],
                  ["evidence", "Extraction Evidence"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={mode === value}
                  onClick={() => go({ mode: value })}
                  className={cn(
                    "cursor-pointer rounded-[6px] border-0 bg-transparent px-[13px] py-[7px] text-workspace-caption font-semibold text-muted focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)]",
                    mode === value &&
                      "bg-panel text-ink shadow-[0_1px_2px_rgba(24,38,56,0.06)]",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              type="button"
              aria-pressed={panelOpen}
              onClick={() => setPanelOpen((open) => !open)}
              className={cn(
                docButtonClass(),
                "max-[1050px]:px-[9px] max-[800px]:hidden",
              )}
            >
              Details
            </button>
            <button
              type="button"
              disabled
              aria-describedby="viewer-extraction-unavailable"
              title="Extraction scheduling is pending"
              className={cn(
                docButtonClass(),
                "max-[1050px]:px-[9px] max-[800px]:h-8",
              )}
            >
              Run extraction
            </button>
            <span id="viewer-extraction-unavailable" className="sr-only">
              Extraction scheduling is pending
            </span>
          </div>
        </div>
      </header>

      <div
        role="toolbar"
        aria-label="Page tools"
        className="flex h-[var(--pf-viewer-toolbar)] shrink-0 items-center justify-between gap-3 overflow-x-auto border-b border-border bg-panel px-5 max-[800px]:px-3"
      >
        <div className="flex items-center gap-1.5">
          <ToolButton
            label="Page thumbnails"
            pressed={thumbsOpen}
            onClick={() => setThumbsOpen((open) => !open)}
            className="max-[800px]:hidden"
          >
            <PanelLeft />
          </ToolButton>
          <span className="mx-1 h-[23px] w-px bg-border max-[800px]:hidden" />
          <ToolButton
            label="Previous page"
            disabled={pageIndex <= 0}
            onClick={() => step(-1)}
          >
            <ChevronLeft />
          </ToolButton>
          <span
            aria-live="polite"
            className="min-w-[52px] text-center text-workspace-caption tabular-nums"
          >
            {page && pages ? `${pageIndex + 1} / ${pages.length}` : "– / –"}
          </span>
          <ToolButton
            label="Next page"
            disabled={!pages || pageIndex < 0 || pageIndex >= pages.length - 1}
            onClick={() => step(1)}
          >
            <ChevronRight />
          </ToolButton>
        </div>
        <div className="flex items-center gap-1.5">
          <ToolButton
            label="Zoom out"
            disabled={!page || scale <= ZOOM_MIN}
            onClick={() => zoomBy(-1)}
          >
            <Minus />
          </ToolButton>
          <span
            aria-label="Zoom level"
            className="min-w-[47px] text-center text-workspace-caption tabular-nums"
          >
            {page ? `${Math.round(scale * 100)}%` : "–"}
          </span>
          <ToolButton
            label="Zoom in"
            disabled={!page || scale >= ZOOM_MAX}
            onClick={() => zoomBy(1)}
          >
            <Plus />
          </ToolButton>
          <span className="mx-1 h-[23px] w-px bg-border max-[800px]:hidden" />
          <button
            type="button"
            aria-pressed={zoom === "page"}
            disabled={!page}
            onClick={() => setZoom("page")}
            className={cn(docButtonClass(), "max-[800px]:hidden")}
          >
            Fit page
          </button>
          <button
            type="button"
            aria-pressed={zoom === "width"}
            disabled={!page}
            onClick={() => setZoom("width")}
            className={cn(docButtonClass(), "max-[800px]:hidden")}
          >
            Fit width
          </button>
        </div>
        <div className="flex items-center gap-1.5">
          {pageLabel ? (
            <span className="rounded-full bg-soft px-[9px] py-[5px] text-workspace-overline font-semibold whitespace-nowrap text-muted max-[1050px]:hidden">
              {pageLabel}
            </span>
          ) : null}
          <ToolButton
            label={mode === "evidence" ? "Evidence panel" : "Details panel"}
            pressed={panelOpen}
            onClick={() => setPanelOpen((open) => !open)}
          >
            <PanelRight />
          </ToolButton>
        </div>
      </div>

      <div className="relative flex min-h-0 flex-1 overflow-hidden">
        {pages && pages.length > 0 ? (
          <nav
            aria-label="Pages"
            className={cn(
              "w-[var(--pf-viewer-thumbs)] shrink-0 overflow-auto border-r border-border bg-panel px-[15px] pt-[17px] pb-5 max-[1250px]:w-[var(--pf-viewer-thumbs-compact)] max-[1250px]:px-[9px] max-[1250px]:py-[13px] max-[800px]:hidden",
              !thumbsOpen && "hidden",
            )}
          >
            <Overline as="h2" className="mb-3.5">
              Pages
            </Overline>
            <ol className="m-0 list-none p-0">
              {pages.map((item) => (
                <li key={item.id}>
                  <Thumbnail
                    projectId={projectId}
                    revisionId={revisionId}
                    documentId={row.id}
                    page={item}
                    active={item.id === page?.id}
                    typeLabel={
                      pageTypes.data?.find(
                        (prediction) =>
                          prediction.page_number === item.page_number,
                      )?.predicted_type
                    }
                    onSelect={() => go({ page: item.page_number })}
                  />
                </li>
              ))}
            </ol>
          </nav>
        ) : null}

        <div className="relative flex min-w-0 flex-1 flex-col bg-[var(--pf-viewer-canvas)]">
          {hasPageImage ? (
            <>
              <div
                ref={scrollRef}
                data-testid="viewer-canvas"
                onPointerDown={startPan}
                onPointerMove={movePan}
                onPointerUp={endPan}
                onPointerCancel={endPan}
                className={cn(
                  "relative min-h-0 flex-1 cursor-grab overflow-auto",
                  panning && "cursor-grabbing select-none",
                )}
              >
                <div
                  className="relative mx-auto mt-7 mb-[70px] transition-[width,height] duration-100 motion-reduce:transition-none"
                  style={{
                    width: Math.round(size.width * scale),
                    height: Math.round(size.height * scale),
                  }}
                >
                  {pinnedUrl && pinned ? (
                    <PinnedPageImage
                      key={pinned.id}
                      url={pinnedUrl}
                      pageNumber={pinned.page_number}
                      region={pinnedRegion}
                      onLoad={() => setLoadedPinnedUrl(pinnedUrl)}
                      onFailure={() => setLoadedPinnedUrl(null)}
                      refresh={() => void browser.source.refetch()}
                    />
                  ) : pinnedRequired ? (
                    <div className="flex size-full flex-col items-center justify-center gap-2 bg-panel p-4 text-center text-workspace-caption text-muted">
                      {browser.source.isFetching ? <p role="status">Loading pinned source page…</p> : (
                        <>
                          <p role="alert">The pinned source page is unavailable.</p>
                          <button type="button" className={docButtonClass("tiny")} onClick={() => void browser.source.refetch()}>Retry source image</button>
                        </>
                      )}
                    </div>
                  ) : page ? (
                    <PageImage
                      key={page.id}
                      projectId={projectId}
                      revisionId={revisionId}
                      documentId={row.id}
                      page={page}
                    />
                  ) : null}
                </div>
              </div>
              <p className="pointer-events-none absolute bottom-[15px] left-[18px] m-0 rounded-[var(--pf-radius-control)] border border-border bg-white/95 px-3 py-2 text-workspace-caption text-muted max-[800px]:hidden">
                Drag to pan · Scroll to navigate
              </p>
            </>
          ) : (
            <div className="flex min-h-0 flex-1 overflow-auto p-6">
              <CanvasState
                row={row}
                complete={complete}
                pagesQuery={pagesQuery}
                retrying={retryingProcessing}
                error={processingError}
                onRetry={() => void retry()}
              />
            </div>
          )}
        </div>

        <aside
          aria-label={mode === "evidence" ? "Extraction evidence" : "Document details"}
          className={cn(
            "flex w-[var(--pf-viewer-panel)] shrink-0 flex-col border-l border-border bg-panel max-[1250px]:w-[var(--pf-viewer-panel-compact)] max-[1050px]:w-[var(--pf-viewer-panel-narrow)] max-[800px]:absolute max-[800px]:inset-y-0 max-[800px]:right-0 max-[800px]:z-[3] max-[800px]:max-w-[calc(100%-40px)] max-[800px]:shadow-[-8px_0_30px_rgba(0,0,0,0.12)]",
            !panelOpen && "hidden",
          )}
        >
          <div className="shrink-0 border-b border-border px-5 pt-[19px] pb-[17px]">
            <h2 className="m-0 mb-[5px] text-workspace-subheading leading-[1.3] font-bold tracking-[-0.3px]">
              {mode === "evidence" ? "Extraction evidence" : "Document details"}
            </h2>
            <p className="m-0 text-workspace-caption text-muted">
              {mode === "evidence"
                ? "Source-grounded candidates · Run history"
                : "Source, classification, and processing"}
            </p>
          </div>
          <div ref={panelScrollRef} className="min-h-0 flex-1 overflow-auto px-5 pt-[18px] pb-7">
            {mode === "evidence" ? (
              row.status === "REMOVED" ? (
                <Hint>This document has been removed from the revision. Extraction evidence is unavailable.</Hint>
              ) : (
                <ExtractionEvidencePanel
                  scope={scope}
                  params={params}
                  browser={browser}
                  update={updateEvidenceRoute}
                  page={pinned?.page_number ?? page?.page_number ?? requestedPage}
                  scrollRef={panelScrollRef}
                  highlighted={!!(pinnedRegion && pinnedUrl && loadedPinnedUrl === pinnedUrl)}
                  canMutate={!!browser.status && browser.status.ineligible_reason !== "READ_ONLY"}
                />
              )
            ) : (
              <DetailsPanel
                projectId={projectId}
                revision={revision}
                row={row}
                page={page}
                processorVersion={processingInfo.data?.processor_version ?? null}
                profileVersion={processingInfo.data?.profile_version ?? null}
              />
            )}
          </div>
        </aside>
      </div>
    </>
  );
}

function ToolButton({
  label,
  pressed,
  disabled,
  onClick,
  className,
  children,
}: {
  label: string;
  pressed?: boolean;
  disabled?: boolean;
  onClick: () => void;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "inline-flex size-[33px] shrink-0 cursor-pointer items-center justify-center rounded-[7px] border-0 bg-transparent text-muted transition-colors hover:bg-selection hover:text-accent focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)] disabled:pointer-events-none disabled:opacity-40 [&>svg]:size-[17px]",
        pressed && "bg-selection text-accent",
        className,
      )}
    >
      {children}
    </button>
  );
}

/** Signed artifact URL that is requested again once when the image fails, since the URL may have expired. */
function useArtifactUrl(
  projectId: string,
  revisionId: string,
  documentId: string,
  page: DocumentPage,
  type: PageArtifactType,
  enabled: boolean,
) {
  const query = useQuery({
    queryKey: [...keys.document(projectId, revisionId, documentId), "artifact", page.id, type],
    queryFn: () =>
      getPageArtifactUrl(projectId, revisionId, documentId, page.id, type),
    enabled,
    staleTime: 0,
    gcTime: 0,
    refetchOnWindowFocus: false,
  });
  const [failures, setFailures] = useState(0);
  function onError() {
    setFailures((count) => count + 1);
    if (failures === 0) void query.refetch();
  }
  function retry() {
    setFailures(0);
    void query.refetch();
  }
  return {
    url: query.data?.url ?? null,
    attempt: failures,
    pending: enabled && query.isPending,
    error: query.error ?? (failures > 1 ? new Error("expired") : null),
    onError,
    retry,
  };
}

function PageImage({
  projectId,
  revisionId,
  documentId,
  page,
}: {
  projectId: string;
  revisionId: string;
  documentId: string;
  page: DocumentPage;
}) {
  const available = artifact(page, "ANALYSIS_IMAGE") !== null;
  const image = useArtifactUrl(
    projectId,
    revisionId,
    documentId,
    page,
    "ANALYSIS_IMAGE",
    available,
  );
  return (
    <div className="absolute inset-0 overflow-hidden bg-white shadow-[var(--pf-shadow-viewer-page)]">
      {image.url && !image.error ? (
        // Signed artifact URLs are short-lived and must not be optimized or cached.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={image.attempt}
          src={image.url}
          alt={`Page ${page.page_number}`}
          draggable={false}
          onError={image.onError}
          className="pointer-events-none block size-full select-none"
        />
      ) : (
        <div className="flex size-full flex-col items-center justify-center gap-3 p-6 text-center text-workspace-caption text-muted">
          {!available ? (
            <p className="m-0">No page image was produced for this page.</p>
          ) : image.error ? (
            <>
              <p role="alert" className="m-0">
                The page image could not be loaded.
              </p>
              <button
                type="button"
                className={docButtonClass("tiny")}
                onClick={image.retry}
              >
                <RotateCcw aria-hidden />
                Try again
              </button>
            </>
          ) : (
            <p role="status" className="m-0">
              Loading page {page.page_number}…
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Thumbnail({
  projectId,
  revisionId,
  documentId,
  page,
  active,
  typeLabel,
  onSelect,
}: {
  projectId: string;
  revisionId: string;
  documentId: string;
  page: DocumentPage;
  active: boolean;
  typeLabel?: RevisionDocument["document_type"];
  onSelect: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const [visible, setVisible] = useState(
    () => typeof IntersectionObserver === "undefined",
  );
  useEffect(() => {
    const element = ref.current;
    if (visible || !element) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [visible]);
  const available = artifact(page, "THUMBNAIL") !== null;
  const thumb = useArtifactUrl(
    projectId,
    revisionId,
    documentId,
    page,
    "THUMBNAIL",
    visible && available,
  );
  const caption = typeLabel
    ? `${page.page_number} · ${documentTypeLabel(typeLabel)}`
    : String(page.page_number);
  return (
    <button
      ref={ref}
      type="button"
      aria-label={`Page ${page.page_number}`}
      aria-current={active ? "page" : undefined}
      onClick={onSelect}
      className={cn(
        "mb-2.5 flex w-full cursor-pointer flex-col items-center gap-[7px] rounded-[var(--pf-radius-control)] border border-transparent bg-transparent p-[7px] hover:bg-soft focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)]",
        active &&
          "border-[var(--pf-viewer-thumb-active)] bg-selection hover:bg-selection",
      )}
    >
      <span className="flex h-[122px] w-[88px] items-center justify-center overflow-hidden border border-[#dce3e9] bg-white shadow-[0_1px_3px_rgba(24,38,56,0.09)] max-[1250px]:h-[100px] max-[1250px]:w-[72px]">
        {thumb.url && !thumb.error ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            key={thumb.attempt}
            src={thumb.url}
            alt=""
            draggable={false}
            onError={thumb.onError}
            className="size-full object-contain"
          />
        ) : (
          <FileText aria-hidden className="size-5 text-[#a3b1bd]" />
        )}
      </span>
      <span className="max-w-full truncate text-workspace-overline font-semibold text-muted">
        {caption}
      </span>
    </button>
  );
}

function CanvasState({
  row,
  complete,
  pagesQuery,
  retrying,
  error,
  onRetry,
}: {
  row: RevisionDocument;
  complete: boolean;
  pagesQuery: { isPending: boolean; error: unknown; data?: DocumentPage[]; refetch: () => unknown };
  retrying: boolean;
  error: string | null;
  onRetry: () => void;
}) {
  const processing = row.processing;
  const retryAction = (
    <button
      type="button"
      disabled={retrying}
      onClick={onRetry}
      className={docButtonClass("primary")}
    >
      <RotateCcw aria-hidden />
      {retrying ? "Retrying…" : "Retry processing"}
    </button>
  );
  if (complete) {
    const pagesError = pagesQuery.error;
    if (pagesError) {
      const notReady = apiErrorOf(pagesError).status === 409;
      return (
        <ViewerNotice
          title={notReady ? "Pages are not ready yet" : "Pages could not be loaded"}
          action={
            <button
              type="button"
              className={docButtonClass()}
              onClick={() => void pagesQuery.refetch()}
            >
              <RotateCcw aria-hidden />
              Try again
            </button>
          }
        >
          {apiErrorOf(pagesError).detail}
        </ViewerNotice>
      );
    }
    if (pagesQuery.isPending) {
      return (
        <ViewerNotice title="Loading pages…" role="status">
          Page images load from the processed document.
        </ViewerNotice>
      );
    }
    return (
      <ViewerNotice title="No pages">
        Processing finished without producing any pages.
      </ViewerNotice>
    );
  }
  if (processing?.status === "RUNNING") {
    const total = processing.pages_total;
    return (
      <ViewerNotice title="Pages are still processing" role="status">
        {total
          ? `${processing.pages_processed} of ${total} pages processed. The viewer updates when processing finishes.`
          : "The viewer updates when processing finishes."}
        {total ? (
          <ProgressBar
            value={(processing.pages_processed / total) * 100}
            label="Processing progress"
            className="mx-auto mt-3"
          />
        ) : null}
      </ViewerNotice>
    );
  }
  if (processing?.status === "PENDING") {
    return (
      <ViewerNotice title="Waiting to start processing" role="status">
        Pages appear here once processing finishes.
      </ViewerNotice>
    );
  }
  if (processing?.status === "FAILED") {
    return (
      <ViewerNotice title="Processing failed" action={retryAction}>
        {processing.error_message ?? "The document could not be processed."}
        {error ? (
          <span role="alert" className="mt-2 block text-danger">
            {error}
          </span>
        ) : null}
      </ViewerNotice>
    );
  }
  return (
    <ViewerNotice title="Not processed">
      Page images are created when the document is processed.
    </ViewerNotice>
  );
}

function ViewerNotice({
  title,
  children,
  action,
  role,
  className,
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  role?: "status";
  className?: string;
}) {
  return (
    <div
      role={role}
      className={cn(
        "m-auto w-full max-w-[420px] rounded-[var(--pf-radius-lg)] border border-border bg-panel px-6 py-7 text-center",
        className,
      )}
    >
      <span className="mx-auto mb-3.5 flex size-11 items-center justify-center rounded-[11px] border border-[var(--pf-documents-file-border)] bg-[var(--pf-documents-file-surface)] text-accent">
        <FileText aria-hidden className="size-5" />
      </span>
      <h2 className="m-0 text-workspace-section font-semibold">{title}</h2>
      <div className="m-0 mt-1.5 text-workspace-caption leading-[1.55] text-muted">
        {children}
      </div>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}

function PanelGroup({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="mb-[23px] last:mb-0">
      <Overline className="mb-2.5">{title}</Overline>
      {children}
    </section>
  );
}

function Facts({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="m-0">
      {items.map(([label, value]) => (
        <div
          key={label}
          className="flex items-start justify-between gap-3.5 border-b border-[#eff2f5] py-[9px] last:border-b-0"
        >
          <dt className="text-workspace-caption text-muted">{label}</dt>
          <dd className="m-0 max-w-[190px] text-right text-workspace-caption font-semibold [overflow-wrap:anywhere]">
            {value}
          </dd>
        </div>
      ))}
    </dl>
  );
}

function Hint({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[var(--pf-radius-control)] bg-canvas px-[13px] py-3 text-workspace-caption leading-[1.6] text-muted [&_strong]:text-ink">
      {children}
    </div>
  );
}

const STATUS_DOT: Record<string, string> = {
  COMPLETED: "bg-positive",
  RUNNING: "bg-accent",
  PENDING: "bg-[#a3b1bd]",
  FAILED: "bg-danger",
};

function DetailsPanel({
  projectId,
  revision,
  row,
  page,
  processorVersion,
  profileVersion,
}: {
  projectId: string;
  revision: Revision;
  row: RevisionDocument;
  page: DocumentPage | null;
  processorVersion: string | null;
  profileVersion: string | null;
}) {
  const file = row.document;
  const original = useOriginalFile(projectId, revision.id, row.id);
  const [textBusy, setTextBusy] = useState(false);
  const [textError, setTextError] = useState<string | null>(null);
  const hasText = artifact(page, "NATIVE_TEXT") !== null;
  const classification = classificationCell(row);
  const status = row.processing?.status;

  async function downloadText() {
    if (!page) return;
    setTextBusy(true);
    setTextError(null);
    try {
      const { url } = await getPageArtifactUrl(
        projectId,
        revision.id,
        row.id,
        page.id,
        "NATIVE_TEXT",
      );
      window.location.assign(url);
    } catch (error) {
      setTextError(apiErrorOf(error).detail);
    } finally {
      setTextBusy(false);
    }
  }

  return (
    <>
      <PanelGroup title="Source classification">
        <p className="m-0 mb-1 flex items-center gap-2 text-workspace-caption text-muted">
          <span
            aria-hidden
            className={cn(
              "size-[7px] rounded-full",
              STATUS_DOT[status ?? ""] ?? "bg-[#a3b1bd]",
            )}
          />
          {row.status === "REMOVED" ? "Removed · " : "Included · "}
          {processingLabel(row.processing)}
        </p>
        <Facts
          items={[
            ["Confirmed type", documentTypeLabel(row.document_type)],
            [
              "Classification",
              classification.detail
                ? `${classification.label} · ${classification.detail}`
                : classification.label,
            ],
            [
              "Pages",
              row.processing?.pages_total != null
                ? `${row.processing.pages_total} ${row.processing.pages_total === 1 ? "page" : "pages"}`
                : "—",
            ],
          ]}
        />
      </PanelGroup>
      <PanelGroup title="Document metadata">
        <Facts
          items={[
            ...(row.document_number
              ? ([["Document no.", row.document_number]] as [string, ReactNode][])
              : []),
            ["File", file.original_filename],
            ["Format", file.mime_type],
            ["Revision", revision.identifier],
            ["Processing", processingLabel(row.processing)],
            ["Text source", textSource(page) ?? "—"],
          ]}
        />
      </PanelGroup>
      <PanelGroup title="Viewer actions">
        <div className="flex flex-wrap gap-2">
          {canOpenInline(file) ? (
            <button
              type="button"
              disabled={original.busy !== null}
              onClick={() => void original.run("inline")}
              className={docButtonClass("tiny")}
            >
              <ExternalLink aria-hidden />
              {original.busy === "inline" ? "Opening…" : "Open original"}
            </button>
          ) : null}
          <button
            type="button"
            disabled={original.busy !== null}
            onClick={() => void original.run("attachment")}
            className={docButtonClass("tiny")}
          >
            <Download aria-hidden />
            {original.busy === "attachment" ? "Preparing…" : "Download"}
          </button>
          {hasText ? (
            <button
              type="button"
              disabled={textBusy}
              onClick={() => void downloadText()}
              className={docButtonClass("tiny")}
            >
              <FileText aria-hidden />
              {textBusy ? "Preparing…" : "Download page text"}
            </button>
          ) : null}
        </div>
        {original.error || textError ? (
          <p role="alert" className="m-0 mt-2 text-workspace-caption text-danger">
            {original.error ?? textError}
          </p>
        ) : null}
        <div className="mt-3">
          <Hint>
            Page images and text come straight from processing and stay
            separate from AI interpretations.
          </Hint>
        </div>
      </PanelGroup>
      <PanelGroup title="Source version">
        {processorVersion || profileVersion ? (
          <Facts
            items={[
              ["Processor", processorVersion ?? "—"],
              ["Profile", profileVersion ?? "—"],
            ]}
          />
        ) : (
          <Hint>No processing version is recorded for this document yet.</Hint>
        )}
      </PanelGroup>
    </>
  );
}

// Evidence regions are normalized to the upright frame of the signed analysis image.
function evidenceRegionStyle(evidence: EvidenceDetail) {
  const region = evidence.region;
  if (!region || evidence.source_locator?.geometry_basis === "NONE") return null;
  const x = Number(region.x);
  const y = Number(region.y);
  const width = Number(region.width);
  const height = Number(region.height);
  if (![x, y, width, height].every(Number.isFinite) || x < 0 || y < 0 ||
      width <= 0 || height <= 0 || x + width > 1.000001 || y + height > 1.000001) return null;
  return {
    left: `${x * 100}%`,
    top: `${y * 100}%`,
    width: `${width * 100}%`,
    height: `${height * 100}%`,
  };
}

function PinnedPageImage({
  url, pageNumber, region, onLoad, onFailure, refresh,
}: {
  url: string;
  pageNumber: number;
  region: ReturnType<typeof evidenceRegionStyle>;
  onLoad: () => void;
  onFailure: () => void;
  refresh: () => void;
}) {
  const [attempt, setAttempt] = useState(0);
  const [loadedUrl, setLoadedUrl] = useState<string | null>(null);
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [retried, setRetried] = useState(false);
  const regionRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (region && loadedUrl === url) {
      regionRef.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    }
  }, [region, loadedUrl, url]);

  function retry() {
    setFailedUrl(null);
    setAttempt((value) => value + 1);
    refresh();
  }
  return (
    <div className="absolute inset-0 overflow-hidden bg-white shadow-[var(--pf-shadow-viewer-page)]">
      {failedUrl === url ? (
        <div className="flex size-full flex-col items-center justify-center gap-2 p-4 text-center text-workspace-caption text-muted">
          <p role="alert" className="m-0">The pinned source page could not be loaded.</p>
          <button type="button" className={docButtonClass("tiny")} onClick={retry}>Retry source image</button>
        </div>
      ) : (
        <>
          {/* Signed historical images use the same upright canvas as Document mode. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            key={attempt}
            src={url}
            alt={`Pinned source page ${pageNumber}`}
            draggable={false}
            onLoad={() => { setLoadedUrl(url); onLoad(); }}
            onError={() => {
              setLoadedUrl(null);
              onFailure();
              if (!retried) {
                setRetried(true);
                retry();
              } else {
                setFailedUrl(url);
              }
            }}
            className="pointer-events-none block size-full select-none"
          />
          {region && loadedUrl === url && (
            <div
              ref={regionRef}
              aria-label="Grounded source region"
              role="img"
              className="pointer-events-none absolute rounded-[2px] border-2 border-amber-600 bg-amber-300/25 shadow-[0_0_0_4px_#fbbf2450]"
              style={region}
            />
          )}
        </>
      )}
    </div>
  );
}
