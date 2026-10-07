"use client";

import { useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { UploadCloud } from "lucide-react";

import { useUploadQueue, type UploadItem } from "@/components/use-upload-queue";
import { Button } from "@/components/ui/button";
import { fieldClassName } from "@/components/ui/input";
import {
  DOCUMENT_TYPE_OPTIONS,
  MAX_UPLOAD_BYTES,
  UPLOAD_ACCEPT,
  formatFileSize,
  type DocumentType,
  type UploadResult,
} from "@/lib/documents";
import { cn } from "@/lib/utils";

type Props = {
  projectId: string;
  revisionId: string;
  onUploaded?: (result: UploadResult) => void;
  onReadOnly?: (message: string) => void;
};

export function DocumentUpload({ projectId, revisionId, onUploaded, onReadOnly }: Props) {
  const { items, add, retry, remove, clearFinished } = useUploadQueue({
    projectId,
    revisionId,
    onUploaded,
    onReadOnly,
  });
  const [documentType, setDocumentType] = useState<DocumentType>("UNKNOWN");
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

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
    <section aria-label="Upload documents" className="mb-5">
      <div
        data-testid="drop-zone"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-wrap items-center justify-between gap-4 rounded-2xl border-2 border-dashed px-6 py-5 transition-colors",
          dragging ? "border-blue-400 bg-blue-50/60" : "border-slate-200 bg-white",
        )}
      >
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-100 text-slate-400">
            <UploadCloud className="h-5 w-5" strokeWidth={1.5} />
          </div>
          <div>
            <p className="text-[14px] font-semibold text-slate-700">
              Drag files here or choose files
            </p>
            <p className="mt-0.5 text-[12px] text-slate-400">
              PDF, PNG, JPEG or TIFF, up to {formatFileSize(MAX_UPLOAD_BYTES)} each. Files upload
              independently.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2 text-[12.5px] text-slate-500">
            Document type for this batch
            <select
              aria-label="Document type for this batch"
              value={documentType}
              onChange={(event) => setDocumentType(event.target.value as DocumentType)}
              className={cn(fieldClassName, "w-auto py-1.5 text-[12.5px]")}
            >
              {DOCUMENT_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <Button type="button" onClick={() => inputRef.current?.click()}>
            Upload Documents
          </Button>
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
      </div>

      {items.length > 0 ? (
        <div className="mt-3">
          <ul aria-live="polite" className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white">
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
              className="mt-2 cursor-pointer text-[12.5px] text-accent hover:underline"
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
    <li className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-[13px]">
      <div className="min-w-0 flex-1">
        <p className="font-medium break-all text-slate-800">{name}</p>
        <p className="text-[12px] text-slate-400">{formatFileSize(item.file.size)}</p>
        {item.status === "failed" && item.error ? (
          <p className="mt-0.5 text-[12px] text-red-600">{item.error}</p>
        ) : null}
        {item.status === "done" && item.duplicate ? (
          <p className="mt-0.5 text-[12px] text-amber-700">
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
          className="h-1.5 w-32 overflow-hidden rounded-full bg-slate-100"
        >
          <div className="h-full bg-blue-500 transition-all" style={{ width: `${item.progress}%` }} />
        </div>
      ) : null}
      <span
        className={cn(
          "w-20 text-[12px] font-semibold",
          item.status === "done" && "text-emerald-700",
          item.status === "failed" && "text-red-600",
          (item.status === "queued" || item.status === "uploading") && "text-slate-500",
        )}
      >
        {STATUS_LABELS[item.status]}
      </span>
      <div className="flex items-center gap-1">
        {item.status === "failed" && item.retryable ? (
          <Button
            type="button"
            variant="secondary"
            size="sm"
            aria-label={`Retry ${name}`}
            onClick={onRetry}
          >
            Retry
          </Button>
        ) : null}
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-label={`${item.status === "uploading" ? "Cancel" : "Remove"} ${name}`}
          onClick={onRemove}
        >
          {item.status === "uploading" ? "Cancel" : "Remove"}
        </Button>
      </div>
    </li>
  );
}
