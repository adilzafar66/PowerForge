"use client";

import * as Menu from "@radix-ui/react-dropdown-menu";
import Link from "next/link";
import {
  ChevronDown,
  ChevronRight,
  Copy,
  Info,
  Lock,
  Plus,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Upload,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { docButtonClass } from "@/components/documents-ui";
import { Select } from "@/components/ui/select";
import {
  DOCUMENT_TYPE_OPTIONS,
  type ClassificationAttemptState,
  type ProcessingRunStatus,
} from "@/lib/documents";
import {
  EMPTY_ADVANCED_FILTERS,
  type AdvancedDocumentFilters,
  type DocumentQuickView,
  type QuickViewCounts,
} from "@/lib/document-presentation";
import { cn } from "@/lib/utils";

const PROCESSING_OPTIONS: {
  value: ProcessingRunStatus | "NONE" | "";
  label: string;
}[] = [
  { value: "", label: "Any state" },
  { value: "COMPLETED", label: "Completed" },
  { value: "RUNNING", label: "Running" },
  { value: "PENDING", label: "Pending" },
  { value: "FAILED", label: "Failed" },
  { value: "NONE", label: "Not started" },
];

const CLASSIFICATION_OPTIONS: {
  value: ClassificationAttemptState | "";
  label: string;
}[] = [
  { value: "", label: "Any" },
  { value: "ready", label: "Ready" },
  { value: "pending", label: "Pending" },
  { value: "classifying", label: "Classifying" },
  { value: "failed", label: "Failed" },
  { value: "not_classified", label: "Not classified" },
  { value: "disabled", label: "AI classification disabled" },
];

export function activeAdvancedFilterCount(
  filters: AdvancedDocumentFilters,
): number {
  return [
    filters.type,
    filters.origin,
    filters.processing,
    filters.classification,
  ].filter(Boolean).length;
}

const menuItem =
  "flex w-full cursor-pointer items-center gap-2.5 rounded-[7px] px-[11px] py-2.5 text-left text-workspace-label text-ink outline-none data-[highlighted]:bg-soft [&>svg]:size-[15px] [&>svg]:text-muted";

export function AddDocumentsMenu({
  onUpload,
  onReuse,
  className,
}: {
  onUpload: () => void;
  onReuse: () => void;
  className?: string;
}) {
  return (
    <Menu.Root modal={false}>
      <Menu.Trigger className={cn(docButtonClass("primary"), className)}>
        <Plus aria-hidden strokeWidth={1.9} />
        Add documents
        <ChevronDown aria-hidden strokeWidth={1.9} />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Content
          aria-label="Add documents"
          align="end"
          sideOffset={7}
          collisionPadding={12}
          className="z-[80] w-[226px] max-w-[calc(100vw-24px)] rounded-[10px] border border-border bg-panel p-[5px] shadow-[var(--pf-shadow-documents-menu)]"
        >
          <Menu.Item className={menuItem} onSelect={onUpload}>
            <Upload aria-hidden strokeWidth={1.8} />
            Upload files
          </Menu.Item>
          <Menu.Item className={menuItem} onSelect={onReuse}>
            <Copy aria-hidden strokeWidth={1.8} />
            Add from another revision
          </Menu.Item>
        </Menu.Content>
      </Menu.Portal>
    </Menu.Root>
  );
}

export function DocumentsHeader({
  revisionLabel,
  overviewHref,
  canMutate,
  onUpload,
  onReuse,
}: {
  revisionLabel?: string;
  overviewHref: string;
  canMutate: boolean;
  onUpload: () => void;
  onReuse: () => void;
}) {
  return (
    <header className="border-b border-border bg-panel px-9 pt-[26px] pb-[25px] max-[1250px]:p-6 max-[850px]:px-5">
      <div className="mx-auto flex max-w-[var(--pf-documents-max)] items-center justify-between gap-4 max-[650px]:flex-wrap">
        <div className="min-w-0">
          <h1 className="m-0 text-workspace-title leading-[1.2] font-bold tracking-[-0.75px] text-ink">
            Documents
          </h1>
          <p className="m-0 mt-[7px] text-workspace-caption text-muted">
            Review, classify, and manage source documents for{" "}
            {revisionLabel ? (
              <strong className="font-bold text-ink">{revisionLabel}</strong>
            ) : (
              "this revision"
            )}
            .
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          <Link href={overviewHref} className={docButtonClass()}>
            Revision details
            <ChevronRight aria-hidden strokeWidth={1.9} />
          </Link>
          {canMutate ? (
            <AddDocumentsMenu onUpload={onUpload} onReuse={onReuse} />
          ) : null}
        </div>
      </div>
    </header>
  );
}

export function AttentionBar({
  attention,
  issues,
  readOnlyReason,
  activeRevisionHref,
  onView,
}: {
  attention: number;
  issues: number;
  readOnlyReason: string | null;
  activeRevisionHref: string | null;
  onView: (view: DocumentQuickView) => void;
}) {
  const action =
    "cursor-pointer border-0 bg-transparent p-0 text-workspace-caption font-semibold whitespace-nowrap text-accent hover:underline focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)]";
  if (readOnlyReason) {
    return (
      <div
        role="status"
        className="mb-[18px] flex items-center justify-between gap-2.5 rounded-[9px] border border-[var(--pf-documents-warning-border)] bg-warning-tint px-[15px] py-3"
      >
        <p className="m-0 flex min-w-0 items-center gap-[9px] text-workspace-caption text-muted">
          <Lock aria-hidden className="size-4 shrink-0 text-warning" strokeWidth={1.8} />
          <span>
            <strong className="font-semibold text-ink">Read-only.</strong>{" "}
            {readOnlyReason} Documents can still be viewed, filtered and
            downloaded.
          </span>
        </p>
        {activeRevisionHref ? (
          <Link href={activeRevisionHref} className={action}>
            View active revision
          </Link>
        ) : null}
      </div>
    );
  }
  if (attention === 0) return null;
  return (
    <div
      role="status"
      className="mb-[18px] flex items-center justify-between gap-2.5 rounded-[9px] border border-[var(--pf-documents-notice-border)] bg-[var(--pf-documents-notice)] px-[15px] py-3"
    >
      <p className="m-0 flex min-w-0 items-center gap-[9px] text-workspace-caption text-muted">
        <Info aria-hidden className="size-4 shrink-0 text-accent" strokeWidth={1.8} />
        <span>
          <strong className="font-semibold text-ink">
            {attention} {attention === 1 ? "document needs" : "documents need"}{" "}
            attention.
          </strong>{" "}
          Review suggested types or investigate processing issues.
        </span>
      </p>
      <button
        type="button"
        className={action}
        onClick={() => onView(issues > 0 ? "issues" : "needs_review")}
      >
        {issues > 0 ? "View issues" : "Review documents"}
      </button>
    </div>
  );
}

export function DocumentRegisterToolbar({
  search,
  onSearchChange,
  filters,
  onFiltersChange,
  refreshing,
  onRefresh,
  selection,
}: {
  search: string;
  onSearchChange: (value: string) => void;
  filters: AdvancedDocumentFilters;
  onFiltersChange: (filters: AdvancedDocumentFilters) => void;
  refreshing: boolean;
  onRefresh: () => void;
  selection?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5 border-b border-border px-5 py-[18px] max-[650px]:p-3.5">
      <div className="flex flex-wrap items-center gap-2.5 max-[650px]:w-full">
        <label className="relative block w-[310px] max-w-full max-[650px]:w-full">
          <Search
            aria-hidden
            className="pointer-events-none absolute top-[11px] left-3 size-4 text-[#8494a3]"
            strokeWidth={1.8}
          />
          <input
            type="search"
            aria-label="Search"
            value={search}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="Search file name, number or description…"
            className="h-[38px] w-full rounded-[var(--pf-radius-control)] border border-border bg-panel pr-3 pl-[38px] text-workspace-label text-ink outline-none placeholder:text-[#8a98a6] focus:border-[#8aa9be] focus:shadow-[0_0_0_3px_#24557a18] [&::-webkit-search-cancel-button]:hidden"
          />
        </label>
        <DocumentFiltersPopover filters={filters} onChange={onFiltersChange} />
      </div>
      <div className="flex max-w-full flex-wrap items-center gap-2.5">
        {selection}
        <button
          type="button"
          className={docButtonClass()}
          onClick={onRefresh}
          disabled={refreshing}
        >
          <RefreshCw
            aria-hidden
            strokeWidth={1.8}
            className={cn(refreshing && "animate-spin motion-reduce:animate-none")}
          />
          Refresh
        </button>
      </div>
    </div>
  );
}

export function DocumentQuickViews({
  value,
  counts,
  onChange,
}: {
  value: DocumentQuickView;
  counts: QuickViewCounts;
  onChange: (view: DocumentQuickView) => void;
}) {
  const views: { value: DocumentQuickView; label: string; count: number }[] = [
    { value: "all", label: "All", count: counts.all },
    { value: "needs_review", label: "Needs review", count: counts.needsReview },
    { value: "issues", label: "Issues", count: counts.issues },
    { value: "removed", label: "Removed", count: counts.removed },
  ];
  return (
    <div
      role="group"
      aria-label="Quick views"
      className="flex items-center gap-[5px] overflow-x-auto border-b border-border px-[18px]"
    >
      {views.map((view) => {
        const active = view.value === value;
        return (
          <button
            key={view.value}
            type="button"
            aria-pressed={active}
            onClick={() => onChange(view.value)}
            className={cn(
              "-mb-px flex shrink-0 cursor-pointer items-center gap-[7px] border-0 border-b-2 border-transparent bg-transparent px-3.5 pt-3.5 pb-3 text-workspace-label whitespace-nowrap text-muted transition-colors hover:bg-soft focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-[rgba(36,85,122,0.24)] max-[650px]:px-2.5 max-[650px]:py-3",
              active && "border-accent font-semibold text-accent",
            )}
          >
            {view.label}
            <span
              className={cn(
                "rounded-[5px] bg-soft px-1.5 py-0.5 text-workspace-overline leading-none font-medium",
                active && "bg-selection",
              )}
            >
              {view.count}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function DocumentFiltersPopover({
  filters,
  onChange,
}: {
  filters: AdvancedDocumentFilters;
  onChange: (filters: AdvancedDocumentFilters) => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const insideMouseEvents = useRef(new WeakSet<Event>());
  const typeId = useId();
  const originId = useId();
  const processingId = useId();
  const classificationId = useId();
  const count = activeAdvancedFilterCount(filters);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) {
      return;
    }

    function onPointerDown(event: MouseEvent) {
      if (
        !insideMouseEvents.current.has(event) &&
        !rootRef.current?.contains(event.target as Node)
      ) {
        close();
      }
    }

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !event.defaultPrevented) {
        close();
      }
    }

    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open, close]);

  return (
    <div
      ref={rootRef}
      className="relative"
      // React capture follows portal ownership, unlike DOM contains(). Record
      // the native event so a select option survives through pointer release.
      onMouseDownCapture={(event) =>
        insideMouseEvents.current.add(event.nativeEvent)
      }
    >
      <button
        type="button"
        className={docButtonClass()}
        aria-label={count > 0 ? `Filters (${count})` : "Filters"}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((current) => !current)}
      >
        <SlidersHorizontal aria-hidden strokeWidth={1.8} />
        Filters
        {count > 0 ? (
          <span
            aria-hidden
            className="rounded-[5px] bg-accent px-1.5 py-0.5 text-workspace-overline leading-none font-semibold text-white"
          >
            {count}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          role="dialog"
          aria-label="Filters"
          className="absolute top-[calc(100%+8px)] left-0 z-50 w-[312px] max-w-[calc(100vw-40px)] rounded-[11px] border border-border bg-panel p-[15px] shadow-[var(--pf-shadow-documents-menu)]"
        >
          <div className="mb-3.5 flex items-center justify-between">
            <strong className="text-workspace-label font-semibold text-ink">
              Filter documents
            </strong>
            <button
              type="button"
              onClick={() => onChange(EMPTY_ADVANCED_FILTERS)}
              className="cursor-pointer border-0 bg-transparent p-0 text-workspace-caption text-accent hover:underline"
            >
              Clear all
            </button>
          </div>
          <div className="grid grid-cols-2 gap-3 max-[650px]:grid-cols-1">
            <FilterSelect
              id={typeId}
              label="Document type"
              value={filters.type}
              onChange={(type) =>
                onChange({
                  ...filters,
                  type: type as AdvancedDocumentFilters["type"],
                })
              }
            >
              <option value="">All types</option>
              {DOCUMENT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </FilterSelect>
            <FilterSelect
              id={originId}
              label="Origin"
              value={filters.origin}
              onChange={(origin) =>
                onChange({
                  ...filters,
                  origin: origin as AdvancedDocumentFilters["origin"],
                })
              }
            >
              <option value="">All origins</option>
              <option value="UPLOADED">Uploaded</option>
              <option value="INHERITED">Inherited</option>
            </FilterSelect>
            <FilterSelect
              id={processingId}
              label="Processing"
              value={filters.processing}
              onChange={(processing) =>
                onChange({
                  ...filters,
                  processing:
                    processing as AdvancedDocumentFilters["processing"],
                })
              }
            >
              {PROCESSING_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </FilterSelect>
            <FilterSelect
              id={classificationId}
              label="AI classification"
              value={filters.classification}
              onChange={(classification) =>
                onChange({
                  ...filters,
                  classification:
                    classification as AdvancedDocumentFilters["classification"],
                })
              }
            >
              {CLASSIFICATION_OPTIONS.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </FilterSelect>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function FilterSelect({
  id,
  label,
  value,
  onChange,
  children,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <label
        htmlFor={id}
        className="text-workspace-caption font-semibold text-muted"
      >
        {label}
      </label>
      <Select
        id={id}
        value={value}
        onValueChange={(value) => onChange(value)}
        className="min-h-[38px] rounded-[var(--pf-radius-control)] border-border px-[11px] py-2 text-workspace-label"
      >
        {children}
      </Select>
    </div>
  );
}
