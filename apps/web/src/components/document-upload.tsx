"use client";

import { Select } from "@/components/ui/select";

import { useId, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Upload } from "lucide-react";

import { useUploadQueue, type UploadItem } from "@/components/use-upload-queue";
import { docButtonClass, DocumentsDialog } from "@/components/documents-ui";
import {
  DOCUMENT_TYPE_OPTIONS,
  MAX_UPLOAD_BYTES,
  UPLOAD_ACCEPT,
  formatFileSize,
  type DocumentType,
  type UploadResult,
} from "@/lib/documents";
import { cn } from "@/lib/utils";

export type UploadQueue = ReturnType<typeof useUploadQueue>;

type Props = {
  projectId: string;
  revisionId: string;
  onUploaded?: (result: UploadResult) => void;
  onReadOnly?: (message: string) => void;
};

/** Standalone upload surface that owns its queue. */
export function DocumentUpload({
  projectId,
  revisionId,
  onUploaded,
  onReadOnly,
}: Props) {
  const queue = useUploadQueue({
    projectId,
    revisionId,
    onUploaded,
    onReadOnly,
  });
  return <DocumentUploadPanel queue={queue} />;
}

/** The queue is owned by the caller, so uploads keep running when the dialog closes. */
export function DocumentUploadDialog({
  queue,
  revisionLabel,
  onClose,
}: {
  queue: UploadQueue;
  revisionLabel?: string;
  onClose: () => void;
}) {
  return (
    <DocumentsDialog
      title="Upload documents"
      description={`Add source files to ${revisionLabel ?? "this revision"}`}
      onClose={onClose}
      footer={
        <button type="button" className={docButtonClass()} onClick={onClose}>
          Close
        </button>
      }
    >
      <DocumentUploadPanel queue={queue} />
    </DocumentsDialog>
  );
}

export function DocumentUploadPanel({ queue }: { queue: UploadQueue }) {
  const { items, add, retry, remove, clearFinished } = queue;
  const [documentType, setDocumentType] = useState<DocumentType>("UNKNOWN");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const typeId = useId();

  function addFiles(files: FileList | null) {
    if (files && files.length > 0) {
      add(Array.from(files), documentType);
    }
  }

  function onPick(event: ChangeEvent<HTMLInputElement>) {
    addFiles(event.target.files);
    event.target.value = "";
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(event.dataTransfer.files);
  }

  return (
    <section aria-label="Upload documents">
      <div
        data-testid="drop-zone"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center rounded-[10px] border border-dashed px-5 py-[26px] text-center transition-colors",
          dragging
            ? "border-accent bg-selection"
            : "border-[var(--pf-documents-dropzone-border)] bg-[#fbfcfd]",
        )}
      >
        <Upload aria-hidden className="size-[22px] text-accent" strokeWidth={1.7} />
        <p className="m-0 mt-2.5 text-workspace-body font-semibold text-ink">
          Drag files here or choose files
        </p>
        <p className="m-0 mt-1.5 text-workspace-caption text-muted">
          PDF, PNG, JPEG or TIFF, up to {formatFileSize(MAX_UPLOAD_BYTES)} each.
          Files upload independently.
        </p>
        <button
          type="button"
          className={cn(docButtonClass("primary"), "mt-3.5")}
          onClick={() => inputRef.current?.click()}
        >
          Choose files
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={UPLOAD_ACCEPT}
          aria-label="Choose files"
          className="hidden"
          onChange={onPick}
        />
      </div>
      <div className="mt-4 flex flex-col gap-1.5">
        <label
          htmlFor={typeId}
          className="text-workspace-caption font-semibold text-muted"
        >
          Document type for this batch
        </label>
        <Select
          id={typeId}
          value={documentType}
          onValueChange={(value) => setDocumentType(value as DocumentType)}
          className="min-h-[38px] rounded-[var(--pf-radius-control)] border-border px-[11px] py-2 text-workspace-label"
        >
          {DOCUMENT_TYPE_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.value === "UNKNOWN"
                ? "Unclassified / let AI suggest"
                : option.label}
            </option>
          ))}
        </Select>
      </div>

      {items.length > 0 ? (
        <div className="mt-4">
          <ul
            aria-live="polite"
            className="m-0 list-none divide-y divide-[var(--pf-documents-row-border)] rounded-[10px] border border-border p-0"
          >
            {items.map((item) => (
              <UploadRow
                key={item.id}
                item={item}
                onRetry={() => retry(item.id)}
                onRemove={() => remove(item.id)}
              />
            ))}
          </ul>
          {items.some((item) => item.status === "done") ? (
            <button
              type="button"
              onClick={clearFinished}
              className="mt-2 cursor-pointer border-0 bg-transparent p-0 text-workspace-caption text-accent hover:underline"
            >
              Clear finished
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

const STATUS_LABELS: Record<UploadItem["status"], string> = {
  queued: "Queued",
  uploading: "Uploading",
  done: "Uploaded",
  failed: "Failed",
};

function UploadRow({
  item,
  onRetry,
  onRemove,
}: {
  item: UploadItem;
  onRetry: () => void;
  onRemove: () => void;
}) {
  const name = item.file.name;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="m-0 text-workspace-label font-semibold break-all text-ink">
          {name}
        </p>
        <p className="m-0 mt-0.5 text-workspace-caption text-muted">
          {formatFileSize(item.file.size)}
        </p>
        {item.status === "failed" && item.error ? (
          <p className="m-0 mt-0.5 text-workspace-caption text-danger">{item.error}</p>
        ) : null}
        {item.status === "done" && item.duplicate ? (
          <p className="m-0 mt-0.5 text-workspace-caption text-warning">
            An identical file already exists in this project.
          </p>
        ) : null}
      </div>
      {item.status === "uploading" ? (
        <div
          role="progressbar"
          aria-label={`Upload progress for ${name}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={item.progress}
          className="h-1 w-24 overflow-hidden rounded-full bg-[var(--pf-progress-track)]"
        >
          <div
            className="h-full bg-accent transition-all"
            style={{ width: `${item.progress}%` }}
          />
        </div>
      ) : null}
      <span
        className={cn(
          "w-[72px] text-workspace-caption font-semibold",
          item.status === "done" && "text-positive",
          item.status === "failed" && "text-danger",
          (item.status === "queued" || item.status === "uploading") &&
            "text-muted",
        )}
      >
        {STATUS_LABELS[item.status]}
      </span>
      <div className="flex items-center gap-1">
        {item.status === "failed" && item.retryable ? (
          <button
            type="button"
            className={docButtonClass("tiny")}
            aria-label={`Retry ${name}`}
            onClick={onRetry}
          >
            Retry
          </button>
        ) : null}
        <button
          type="button"
          className={docButtonClass("tiny", "ghost")}
          aria-label={`${item.status === "uploading" ? "Cancel" : "Remove"} ${name}`}
          onClick={onRemove}
        >
          {item.status === "uploading" ? "Cancel" : "Remove"}
        </button>
      </div>
    </li>
  );
}
