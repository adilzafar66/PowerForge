"use client";

import { Select } from "@/components/ui/select";

import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { Button } from "@/components/ui/button";
import { DropdownMenu } from "@/components/ui/dropdown-menu";
import { fieldClassName } from "@/components/ui/input";
import { SearchField } from "@/components/ui/search-field";
import { SegmentedControl } from "@/components/ui/segmented-control";
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
  { value: "", label: "All processing states" },
  { value: "NONE", label: "Not started" },
  { value: "PENDING", label: "Pending" },
  { value: "RUNNING", label: "Running" },
  { value: "COMPLETED", label: "Completed" },
  { value: "FAILED", label: "Failed" },
];

const CLASSIFICATION_OPTIONS: {
  value: ClassificationAttemptState | "";
  label: string;
}[] = [
  { value: "", label: "All classification states" },
  { value: "disabled", label: "AI classification disabled" },
  { value: "not_classified", label: "Not classified" },
  { value: "pending", label: "Pending" },
  { value: "classifying", label: "Classifying" },
  { value: "ready", label: "Ready" },
  { value: "failed", label: "Failed" },
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

export function AddDocumentsMenu({
  onUpload,
  onReuse,
}: {
  onUpload: () => void;
  onReuse: () => void;
}) {
  return (
    <DropdownMenu
      label="Add Documents"
      triggerLabel="Add Documents"
      items={[
        { id: "upload", label: "Upload files", onSelect: onUpload },
        { id: "reuse", label: "Add from another revision", onSelect: onReuse },
      ]}
    />
  );
}

export function DocumentWorkspaceToolbar({
  documentCount,
  canMutate,
  search,
  onSearchChange,
  filters,
  onFiltersChange,
  onUpload,
  onReuse,
}: {
  documentCount: number | null;
  canMutate: boolean;
  search: string;
  onSearchChange: (value: string) => void;
  filters: AdvancedDocumentFilters;
  onFiltersChange: (filters: AdvancedDocumentFilters) => void;
  onUpload: () => void;
  onReuse: () => void;
}) {
  return (
    <div className="mb-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[15px] font-semibold text-slate-900">
          Documents{documentCount === null ? "" : ` ${documentCount}`}
        </h2>
        {canMutate ? (
          <AddDocumentsMenu onUpload={onUpload} onReuse={onReuse} />
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <SearchField
          value={search}
          onChange={onSearchChange}
          placeholder="Search by file name, number or description…"
        />
        <DocumentFiltersPopover filters={filters} onChange={onFiltersChange} />
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
  return (
    <SegmentedControl
      className="mb-4"
      label="Quick views"
      value={value}
      onChange={onChange}
      options={[
        { value: "all", label: "All", count: counts.all },
        {
          value: "needs_review",
          label: "Needs Review",
          count: counts.needsReview,
        },
        { value: "issues", label: "Issues", count: counts.issues },
        { value: "removed", label: "Removed", count: counts.removed },
      ]}
    />
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
      <Button
        type="button"
        variant="secondary"
        size="sm"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={() => setOpen((current) => !current)}
      >
        {count > 0 ? `Filters (${count})` : "Filters"}
      </Button>
      {open ? (
        <div
          role="dialog"
          aria-label="Filters"
          className="absolute top-full left-0 z-50 mt-1.5 w-72 rounded-xl border border-slate-200 bg-white p-3 shadow-[0_12px_28px_rgba(0,0,0,0.12),0_2px_6px_rgba(0,0,0,0.06)]"
        >
          <div className="flex flex-col gap-3">
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
              label="Processing state"
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
              label="Classification state"
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
            <button
              type="button"
              onClick={() => onChange(EMPTY_ADVANCED_FILTERS)}
              className="cursor-pointer self-start text-[12.5px] text-accent hover:underline"
            >
              Clear filters
            </button>
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
    <label
      htmlFor={id}
      className="flex flex-col gap-1 text-[12px] font-medium text-slate-500"
    >
      {label}
      <Select
        id={id}
        value={value}
        onValueChange={(value) => onChange(value)}
        className={cn(fieldClassName, "py-2 text-[13px]")}
      >
        {children}
      </Select>
    </label>
  );
}
